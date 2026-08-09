"""Regole PII personali cifrate e casi di miglioramento sanitizzati.

Le regole sono conservate come un singolo documento JSON cifrato nel database
dell'utente. Il modulo non usa Streamlit e non conserva valori in cache.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import datetime as dt
import json
import re
import secrets
import unicodedata
from typing import Iterable

import pseudonimizzazione as pseudo
import segreti


NOME_SEGRETO = "pii.regole.v1"
VERSIONE_DOCUMENTO = 1
LUNGHEZZA_MINIMA = 3
LUNGHEZZA_MASSIMA = 120
TIPI_AMMESSI = (
    "ALTRO_PII", "PAZIENTE", "PERSONA", "MEDICO", "STRUTTURA",
    "LOCALITA", "INDIRIZZO", "CONTATTO", "CODICE_FISCALE",
    "IDENTIFICATIVO_SANITARIO", "IDENTIFICATIVO_DOCUMENTO", "DATA_CLINICA",
)


class ErroreRegole(Exception):
    """Errore sicuro da mostrare all'utente senza includere valori PII."""


class RegoleNonDecifrabili(ErroreRegole):
    pass


@dataclass(frozen=True)
class RegolaPII:
    id: str
    valore: str
    tipo: str
    attiva: bool
    creata_il: str
    aggiornata_il: str


def _ora() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _normalizza(valore: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", valore).split()).casefold()


def convalida(valore: str, tipo: str) -> str:
    valore = (valore or "").strip()
    if len(valore) < LUNGHEZZA_MINIMA:
        return (f"Una regola ricordata deve contenere almeno "
                f"{LUNGHEZZA_MINIMA} caratteri.")
    if len(valore) > LUNGHEZZA_MASSIMA:
        return (f"Una regola ricordata non può superare "
                f"{LUNGHEZZA_MASSIMA} caratteri.")
    if "\n" in valore or "\r" in valore:
        return "Una regola ricordata deve stare su una sola riga."
    if pseudo.TOKEN_SIMILE_RE.search(valore):
        return "Un token riservato non può diventare una regola personale."
    if tipo not in TIPI_AMMESSI:
        return "Categoria PII non riconosciuta."
    return ""


def _serializza(regole: Iterable[RegolaPII]) -> str:
    return json.dumps(
        {"versione": VERSIONE_DOCUMENTO,
         "regole": [asdict(regola) for regola in regole]},
        ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    )


def _deserializza(testo: str) -> list[RegolaPII]:
    try:
        documento = json.loads(testo)
        if documento.get("versione") != VERSIONE_DOCUMENTO:
            raise ValueError("versione")
        regole = []
        for voce in documento.get("regole", []):
            regola = RegolaPII(
                id=str(voce["id"]), valore=str(voce["valore"]),
                tipo=str(voce["tipo"]), attiva=bool(voce["attiva"]),
                creata_il=str(voce["creata_il"]),
                aggiornata_il=str(voce["aggiornata_il"]),
            )
            if convalida(regola.valore, regola.tipo):
                raise ValueError("regola")
            regole.append(regola)
        return regole
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ErroreRegole("L'archivio delle regole PII non è valido.") from exc


def carica(conn, utente_id: int, password: str) -> list[RegolaPII]:
    if not segreti.esiste_segreto(conn, utente_id, NOME_SEGRETO):
        return []
    testo = segreti.leggi_segreto(conn, utente_id, password, NOME_SEGRETO)
    if testo is None:
        raise RegoleNonDecifrabili(
            "Le regole PII non sono decifrabili con la password corrente.")
    return _deserializza(testo)


def _salva_tutte(conn, utente_id: int, password: str,
                  regole: Iterable[RegolaPII]) -> None:
    segreti.salva_segreto(conn, utente_id, password, NOME_SEGRETO,
                          _serializza(regole))


def salva(conn, utente_id: int, password: str, valore: str,
          tipo: str) -> RegolaPII:
    valore = (valore or "").strip()
    if errore := convalida(valore, tipo):
        raise ErroreRegole(errore)
    regole = carica(conn, utente_id, password)
    normalizzato = _normalizza(valore)
    adesso = _ora()
    esistenti = [r for r in regole if _normalizza(r.valore) == normalizzato]
    if esistenti:
        corrente = esistenti[0]
        aggiornata = RegolaPII(corrente.id, valore, tipo, True,
                               corrente.creata_il, adesso)
        regole = [aggiornata if r.id == corrente.id else r for r in regole]
    else:
        aggiornata = RegolaPII(secrets.token_hex(8), valore, tipo, True,
                               adesso, adesso)
        regole.append(aggiornata)
    _salva_tutte(conn, utente_id, password, regole)
    return aggiornata


def aggiorna(conn, utente_id: int, password: str, regola_id: str, *,
             valore: str, tipo: str, attiva: bool) -> RegolaPII:
    valore = (valore or "").strip()
    if errore := convalida(valore, tipo):
        raise ErroreRegole(errore)
    regole = carica(conn, utente_id, password)
    corrente = next((r for r in regole if r.id == regola_id), None)
    if corrente is None:
        raise ErroreRegole("Regola PII inesistente.")
    normalizzato = _normalizza(valore)
    if any(r.id != regola_id and _normalizza(r.valore) == normalizzato
           for r in regole):
        raise ErroreRegole("Esiste già una regola per questo valore.")
    aggiornata = RegolaPII(corrente.id, valore, tipo, bool(attiva),
                           corrente.creata_il, _ora())
    _salva_tutte(conn, utente_id, password,
                 [aggiornata if r.id == regola_id else r for r in regole])
    return aggiornata


def elimina(conn, utente_id: int, password: str, regola_id: str) -> bool:
    regole = carica(conn, utente_id, password)
    mantenute = [r for r in regole if r.id != regola_id]
    if len(mantenute) == len(regole):
        return False
    if mantenute:
        _salva_tutte(conn, utente_id, password, mantenute)
    else:
        segreti.elimina_segreto(conn, utente_id, NOME_SEGRETO)
    return True


def elimina_tutte(conn, utente_id: int) -> None:
    """Rimuove il blob anche quando la vecchia password non è disponibile."""
    segreti.elimina_segreto(conn, utente_id, NOME_SEGRETO)


def attive(regole: Iterable[RegolaPII]) -> list[tuple[str, str]]:
    return [(regola.valore, regola.tipo) for regola in regole if regola.attiva]


def _contiene(testo: str, valore: str) -> bool:
    return _normalizza(valore) in _normalizza(testo)


def crea_caso_miglioramento(testo: str, valore: str, tipo: str,
                            occorrenze: Iterable[tuple[int, int]], *,
                            raggio: int = 90) -> dict:
    """Crea un piccolo caso locale che non contiene il valore segnalato.

    Gli altri token opachi vengono normalizzati. Il contesto residuo può essere
    sanitario e deve quindi essere mostrato e approvato prima del download.
    """
    if tipo not in TIPI_AMMESSI:
        raise ErroreRegole("Categoria PII non riconosciuta.")
    valore = (valore or "").strip()
    if not valore:
        raise ErroreRegole("Il valore segnalato è vuoto.")
    occorrenze = list(occorrenze)
    if not occorrenze:
        raise ErroreRegole("Seleziona almeno un'occorrenza da esportare.")
    contesti: list[str] = []
    schema = re.compile(re.escape(valore), re.IGNORECASE)
    finestre: list[tuple[int, int]] = []
    for inizio, fine in sorted(occorrenze):
        if inizio < 0 or fine <= inizio or fine > len(testo):
            raise ErroreRegole("Occorrenza non valida.")
        finestra = (max(0, inizio - raggio), min(len(testo), fine + raggio))
        if finestre and finestra[0] <= finestre[-1][1]:
            finestre[-1] = (finestre[-1][0],
                            max(finestre[-1][1], finestra[1]))
        else:
            finestre.append(finestra)
    for inizio, fine in finestre:
        frammento = testo[inizio:fine]
        frammento = schema.sub("[[PII_SEGNALATA]]", frammento)
        frammento = pseudo.TOKEN_RE.sub("[[TOKEN_OPACO]]", frammento)
        contesti.append(frammento.strip())
    caso = {
        "formato": "ahia-pii-improvement-v1",
        "generato_il": _ora(),
        "categoria_attesa": tipo,
        "marcatore": "[[PII_SEGNALATA]]",
        "contesti": contesti,
        "pii_segnalata_inclusa": False,
        "revisione_privacy_richiesta": True,
    }
    serializzato = json.dumps(caso, ensure_ascii=False)
    if _contiene(serializzato, valore):
        raise ErroreRegole(
            "Non è stato possibile rimuovere il valore dal caso esportabile.")
    return caso
