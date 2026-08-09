"""AHIA — chiavi API cifrate e invio del quesito a un modello di frontiera.

La chiave API e' l'unico segreto che, se usato, esce dalla macchina insieme ai
dati. Viene cifrata con una chiave derivata dalla password dell'utente: chi
apre il file del database non la legge senza la password. Il prezzo di questa
scelta e' che reimpostando la password la chiave API va reinserita — corretto,
perche' una reimpostazione non deve regalare a un terzo l'accesso ai segreti.

L'invio non e' mai automatico: l'app prepara il quesito, l'utente lo legge, e
solo un secondo gesto esplicito lo spedisce. Nulla parte senza quel gesto.
"""

# AHIA — archivio e lettura dei referti medici, in locale.
# Copyright (C) 2026  vonausterliz
#
# Questo programma e' software libero: puoi ridistribuirlo e/o modificarlo
# secondo i termini della GNU Affero General Public License, versione 3, come
# pubblicata dalla Free Software Foundation.
#
# Distribuito nella speranza che sia utile, ma SENZA ALCUNA GARANZIA, neppure
# quella implicita di commerciabilita' o idoneita' a uno scopo particolare.
# Vedi la GNU Affero General Public License per i dettagli:
# https://www.gnu.org/licenses/agpl-3.0.html

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

from cryptography.exceptions import InvalidKey
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

TIMEOUT_API = 120

# Fornitori supportati: endpoint, modello predefinito, intestazioni.
FORNITORI = {
    "openrouter": {
        "nome": "OpenRouter (instradamento controllato)",
        "url": "https://eu.openrouter.ai/api/v1/chat/completions",
        "modello": "anthropic/claude-sonnet-4.5",
        "dove_chiave": "https://openrouter.ai/settings/keys",
        "prefisso": "sk-or-",
    },
    "anthropic": {
        "nome": "Claude (Anthropic)",
        "url": "https://api.anthropic.com/v1/messages",
        "modello": "claude-sonnet-4-5",
        "dove_chiave": "https://console.anthropic.com/settings/keys",
        "prefisso": "sk-ant-",
    },
    "openai": {
        "nome": "ChatGPT (OpenAI)",
        "url": "https://api.openai.com/v1/chat/completions",
        "modello": "gpt-4o",
        "dove_chiave": "https://platform.openai.com/api-keys",
        "prefisso": "sk-",
    },
}


# --- Cifratura -------------------------------------------------------------


def _chiave_cifratura(password: str, sale: bytes) -> bytes:
    """Deriva una chiave Fernet dalla password. Parametri scrypt piu' leggeri
    di quelli d'autenticazione: qui si sblocca a ogni accesso ai segreti."""
    grezza = Scrypt(salt=sale, length=32, n=2 ** 14, r=8, p=1).derive(
        password.encode("utf-8"))
    return base64.urlsafe_b64encode(grezza)


def cifra(password: str, sale: bytes, testo: str) -> bytes:
    return Fernet(_chiave_cifratura(password, sale)).encrypt(testo.encode("utf-8"))


def decifra(password: str, sale: bytes, blob: bytes) -> str | None:
    """Testo in chiaro, o None se la password e' cambiata dopo la cifratura."""
    try:
        return Fernet(_chiave_cifratura(password, sale)).decrypt(blob).decode("utf-8")
    except (InvalidToken, InvalidKey, ValueError):
        return None


# --- Persistenza dei segreti ------------------------------------------------

DDL = """
CREATE TABLE IF NOT EXISTS segreti (
    utente_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    valore BLOB NOT NULL,
    sale BLOB NOT NULL,
    PRIMARY KEY (utente_id, nome)
);
"""


def prepara(conn) -> None:
    conn.executescript(DDL)
    conn.commit()


def salva_segreto(conn, utente_id: int, password: str, nome: str,
                   valore: str) -> None:
    """Salva un valore cifrato associato all'utente.

    ``nome`` non deve contenere dati sensibili: resta in chiaro per consentire
    di individuare il record da decifrare. Il contenuto viene sempre cifrato
    con un sale nuovo, anche quando sostituisce un valore esistente.
    """
    import secrets

    sale = secrets.token_bytes(16)
    conn.execute(
        "INSERT INTO segreti (utente_id, nome, valore, sale) VALUES (?,?,?,?) "
        "ON CONFLICT(utente_id, nome) DO UPDATE SET valore=excluded.valore, "
        "sale=excluded.sale",
        (utente_id, nome, cifra(password, sale, valore), sale))
    conn.commit()


def leggi_segreto(conn, utente_id: int, password: str,
                   nome: str) -> str | None:
    """Restituisce il valore in chiaro, o ``None`` se manca o non si decifra."""
    riga = conn.execute(
        "SELECT valore, sale FROM segreti WHERE utente_id=? AND nome=?",
        (utente_id, nome)).fetchone()
    if not riga:
        return None
    return decifra(password, riga["sale"], riga["valore"])


def esiste_segreto(conn, utente_id: int, nome: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM segreti WHERE utente_id=? AND nome=?",
        (utente_id, nome)).fetchone() is not None


def elimina_segreto(conn, utente_id: int, nome: str) -> None:
    conn.execute("DELETE FROM segreti WHERE utente_id=? AND nome=?",
                 (utente_id, nome))
    conn.commit()


def salva_chiave(conn, utente_id: int, password: str, fornitore: str,
                 chiave_api: str) -> None:
    salva_segreto(conn, utente_id, password, f"api.{fornitore}", chiave_api)


def leggi_chiave(conn, utente_id: int, password: str,
                 fornitore: str) -> str | None:
    return leggi_segreto(conn, utente_id, password, f"api.{fornitore}")


def elimina_chiave(conn, utente_id: int, fornitore: str) -> None:
    elimina_segreto(conn, utente_id, f"api.{fornitore}")


def fornitori_configurati(conn, utente_id: int) -> list[str]:
    righe = conn.execute(
        "SELECT nome FROM segreti WHERE utente_id=? AND nome LIKE 'api.%'",
        (utente_id,)).fetchall()
    return [r["nome"].split(".", 1)[1] for r in righe]


# --- Invio al modello di frontiera -----------------------------------------


class ErroreAPI(Exception):
    pass


def _chiama(url: str, intestazioni: dict, payload: dict) -> dict:
    dati = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=dati, headers=intestazioni,
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_API) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", "replace")
        try:
            messaggio = json.loads(corpo).get("error", {}).get("message", corpo)
        except json.JSONDecodeError:
            messaggio = corpo
        if e.code in (401, 403):
            raise ErroreAPI("Chiave API rifiutata: controlla che sia corretta e "
                            "attiva.") from e
        if e.code == 429:
            raise ErroreAPI("Limite di richieste o credito esaurito presso il "
                            "fornitore.") from e
        raise ErroreAPI(f"Errore {e.code}: {messaggio[:200]}") from e
    except urllib.error.URLError as e:
        raise ErroreAPI(f"Connessione non riuscita: {e.reason}. Questo invio "
                        "richiede internet.") from e


def invia(fornitore: str, chiave_api: str, quesito: str,
          modello: str | None = None) -> str:
    """Invia il quesito e restituisce la risposta testuale del modello."""
    cfg = FORNITORI[fornitore]
    modello = modello or cfg["modello"]

    if fornitore == "anthropic":
        risposta = _chiama(
            cfg["url"],
            {"x-api-key": chiave_api, "anthropic-version": "2023-06-01",
             "content-type": "application/json"},
            {"model": modello, "max_tokens": 2048,
             "messages": [{"role": "user", "content": quesito}]})
        blocchi = [b.get("text", "") for b in risposta.get("content", [])
                   if b.get("type") == "text"]
        return "\n".join(blocchi).strip() or "(risposta vuota)"

    payload = {"model": modello, "max_tokens": 2048,
               "messages": [{"role": "user", "content": quesito}]}
    if fornitore == "openrouter":
        payload["provider"] = {
            "zdr": True,
            "data_collection": "deny",
            "allow_fallbacks": False,
        }
    risposta = _chiama(
        cfg["url"],
        {"Authorization": f"Bearer {chiave_api}",
         "Content-Type": "application/json"},
        payload)
    scelte = risposta.get("choices", [])
    if scelte:
        return scelte[0].get("message", {}).get("content", "").strip() \
            or "(risposta vuota)"
    return "(risposta vuota)"


def convalida_formato(fornitore: str, chiave_api: str) -> str:
    """Controllo di forma prima di salvare. Vuoto se la chiave e' plausibile."""
    chiave_api = (chiave_api or "").strip()
    prefisso = FORNITORI[fornitore]["prefisso"]
    if not chiave_api:
        return "Inserisci la chiave."
    if not chiave_api.startswith(prefisso):
        return f"Una chiave {FORNITORI[fornitore]['nome']} inizia con «{prefisso}»."
    if len(chiave_api) < 20:
        return "La chiave sembra troppo corta."
    return ""
