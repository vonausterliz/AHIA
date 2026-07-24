"""AHIA — strumenti che il modello puo' invocare per interrogare l'archivio.

Principio: il modello sceglie *quale* domanda porre ai dati, non calcola nulla.
Ogni funzione qui esegue una query e restituisce numeri gia' pronti. Nessuno
strumento accetta SQL libero, e i nomi degli analiti vengono sempre validati
contro quelli realmente presenti in archivio.
"""

# AHIA — archivio e lettura dei referti medici, in locale.
# Copyright (C) 2026  {AUTORE}
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

import json
import sqlite3

import core
import ingest
from config import ALIAS_PATH

MAX_GIRI = 3  # oltre, il modello sta girando a vuoto


# --- Definizioni ------------------------------------------------------------

def _fn(nome: str, descrizione: str, proprieta: dict, obbligatori: list[str]) -> dict:
    return {"type": "function", "function": {
        "name": nome, "description": descrizione,
        "parameters": {"type": "object", "properties": proprieta,
                       "required": obbligatori}}}


DEFINIZIONI = [
    _fn("serie_analita",
        "Tutte le misurazioni di un esame di laboratorio nel tempo, con le "
        "statistiche gia' calcolate. Usalo per domande su andamento, valore "
        "massimo o minimo, prima o ultima misurazione.",
        {"analita": {"type": "string",
                     "description": "Nome dell'esame, es. 'GLUCOSIO', 'GGT'"}},
        ["analita"]),
    _fn("confronta_date",
        "Confronta il valore di un esame tra due date, con differenza assoluta "
        "e percentuale gia' calcolate.",
        {"analita": {"type": "string", "description": "Nome dell'esame"},
         "data_a": {"type": "string", "description": "Prima data, YYYY-MM-DD"},
         "data_b": {"type": "string", "description": "Seconda data, YYYY-MM-DD"}},
        ["analita", "data_a", "data_b"]),
    _fn("conta_fuori_range",
        "Quante volte un esame e' risultato fuori dall'intervallo di "
        "riferimento, con l'elenco delle date. Senza analita, riepiloga tutti.",
        {"analita": {"type": "string", "description": "Nome dell'esame, opzionale"},
         "da": {"type": "string", "description": "Data iniziale YYYY-MM-DD, opzionale"},
         "a": {"type": "string", "description": "Data finale YYYY-MM-DD, opzionale"}},
        []),
    _fn("cerca_nei_referti",
        "Cerca parole nei referti narrativi (ecografie, visite, radiologia) e "
        "restituisce i passaggi che le contengono.",
        {"testo": {"type": "string", "description": "Parole da cercare"}},
        ["testo"]),
]


# --- Esecuzione -------------------------------------------------------------


def _risolvi_analita(conn: sqlite3.Connection, nome: str) -> str | None:
    """Il modello scrive il nome a modo suo: lo si riporta a uno esistente.

    Si passa dal dizionario degli alias, che conosce gia' le equivalenze d'uso
    comune ("glicemia" e' GLUCOSIO), poi si tenta la corrispondenza parziale.
    """
    cercato = (nome or "").strip()
    if not cercato:
        return None
    disponibili = core.elenco_analiti(conn)

    canonico = ingest.canonico_di(cercato, ingest.carica_alias(ALIAS_PATH))
    if canonico in disponibili:
        return canonico
    if cercato.upper() in disponibili:
        return cercato.upper()
    parziali = [a for a in disponibili
                if cercato.upper() in a or a in cercato.upper()]
    return parziali[0] if len(parziali) == 1 else None


def _serie_analita(conn, analita: str = "", **_) -> dict:
    nome = _risolvi_analita(conn, analita)
    if not nome:
        return {"errore": f"'{analita}' non e' in archivio",
                "disponibili": core.elenco_analiti(conn)}
    misure = conn.execute(
        """SELECT data_prelievo, valore_testo, unita, flag FROM risultati
           WHERE analita = ? AND valore IS NOT NULL ORDER BY data_prelievo""",
        (nome,)).fetchall()
    stat = core.statistiche_analiti(conn).get(nome, {})
    return {"analita": nome, "statistiche": stat,
            "misurazioni": [{"data": m["data_prelievo"], "valore": m["valore_testo"],
                             "unita": m["unita"], "stato": m["flag"]} for m in misure]}


def _confronta_date(conn, analita: str = "", data_a: str = "", data_b: str = "",
                    **_) -> dict:
    nome = _risolvi_analita(conn, analita)
    if not nome:
        return {"errore": f"'{analita}' non e' in archivio"}

    def piu_vicina(data):
        iso = core.normalizza_data(data)
        if not iso:
            return None
        return conn.execute(
            """SELECT data_prelievo, valore, valore_testo, unita FROM risultati
               WHERE analita = ? AND valore IS NOT NULL
               ORDER BY ABS(julianday(data_prelievo) - julianday(?)) LIMIT 1""",
            (nome, iso)).fetchone()

    a, b = piu_vicina(data_a), piu_vicina(data_b)
    if not a or not b:
        return {"errore": "una delle due date non e' interpretabile o non ci sono "
                          "misurazioni", "analita": nome}
    delta = b["valore"] - a["valore"]
    return {"analita": nome, "unita": b["unita"],
            "a": {"data": a["data_prelievo"], "valore": a["valore_testo"]},
            "b": {"data": b["data_prelievo"], "valore": b["valore_testo"]},
            "differenza": round(delta, 3),
            "differenza_percentuale": (round(delta / a["valore"] * 100, 1)
                                       if a["valore"] else None),
            "nota": "sono state usate le misurazioni piu' vicine alle date richieste"}


def _conta_fuori_range(conn, analita: str = "", da: str = "", a: str = "", **_) -> dict:
    condizioni, parametri = ["flag IN ('H','L')"], []
    nome = _risolvi_analita(conn, analita) if analita else None
    if analita and not nome:
        return {"errore": f"'{analita}' non e' in archivio"}
    if nome:
        condizioni.append("analita = ?")
        parametri.append(nome)
    for campo, valore in (("data_prelievo >= ?", da), ("data_prelievo <= ?", a)):
        iso = core.normalizza_data(valore)
        if iso:
            condizioni.append(campo)
            parametri.append(iso)
    righe = conn.execute(
        f"""SELECT analita, data_prelievo, valore_testo, unita, flag FROM risultati
            WHERE {' AND '.join(condizioni)} ORDER BY analita, data_prelievo""",
        parametri).fetchall()
    per_analita: dict[str, list] = {}
    for r in righe:
        per_analita.setdefault(r["analita"], []).append(
            {"data": r["data_prelievo"], "valore": r["valore_testo"],
             "unita": r["unita"], "stato": "alto" if r["flag"] == "H" else "basso"})
    return {"totale": len(righe),
            "per_analita": {k: {"volte": len(v), "occorrenze": v}
                            for k, v in per_analita.items()}}


def _cerca_nei_referti(conn, testo: str = "", **_) -> dict:
    esiti = core.cerca_testo(conn, testo, 6)
    return {"trovati": len(esiti),
            "passaggi": [{"tipo": r["tipo"], "data": r["data_documento"],
                          "titolo": r["titolo"] or r["nome_file"],
                          "estratto": r["estratto"]} for r in esiti]}


ESECUTORI = {
    "serie_analita": _serie_analita,
    "confronta_date": _confronta_date,
    "conta_fuori_range": _conta_fuori_range,
    "cerca_nei_referti": _cerca_nei_referti,
}


def esegui(conn: sqlite3.Connection, nome: str, argomenti: dict) -> str:
    """Esegue uno strumento e restituisce il risultato in JSON."""
    funzione = ESECUTORI.get(nome)
    if not funzione:
        return json.dumps({"errore": f"strumento '{nome}' inesistente"},
                          ensure_ascii=False)
    if not isinstance(argomenti, dict):
        argomenti = {}
    try:
        return json.dumps(funzione(conn, **argomenti), ensure_ascii=False,
                          default=str)
    except (sqlite3.Error, TypeError, ValueError) as e:
        return json.dumps({"errore": f"{type(e).__name__}: {e}"}, ensure_ascii=False)


# --- Promemoria nel prompt di sistema ---------------------------------------
# Su alcuni modelli (Qwen3) le definizioni passate nel parametro `tools` vengono
# serializzate male dal template di Ollama: ripeterle qui in chiaro le rende
# comunque visibili al modello.

def promemoria() -> str:
    elenco = "\n".join(
        f"- `{d['function']['name']}({', '.join(d['function']['parameters']['properties'])})`"
        f": {d['function']['description']}"
        for d in DEFINIZIONI)
    return (
        "Hai a disposizione questi strumenti per interrogare l'archivio:\n"
        f"{elenco}\n\n"
        "Usali quando la domanda riguarda dati che non vedi gia' nel contesto, "
        "per esempio l'intera storia di un esame o conteggi su piu' anni. "
        "Non calcolare mai differenze o percentuali a mente: chiedile agli "
        "strumenti o usa i numeri gia' calcolati nel contesto. Quando hai i "
        "dati che ti servono, rispondi in italiano senza altre chiamate."
    )
