"""AHIA — ricerca semantica sui referti narrativi.

Gli embedding servono al testo discorsivo, non ai valori di laboratorio: su
quelli la ricerca vettoriale sarebbe peggiore di una query SQL, perche' non
ordina, non calcola differenze e non garantisce di aver trovato tutto.

L'archivio di una persona sta nell'ordine delle migliaia di frammenti: il
confronto a forza bruta con numpy costa millisecondi e non serve un database
vettoriale.
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
import re
import sqlite3

import numpy as np

import core
from config import (DIM_FRAMMENTO, MODELLO_EMBEDDING, OLLAMA_EMBED_URL,
                    OLLAMA_EMBED_URL_LEGACY, SOVRAPPOSIZIONE, TIMEOUT_LLM)


# --- Frammentazione --------------------------------------------------------


def frammenta(testo: str, dimensione: int = DIM_FRAMMENTO,
              sovrapposizione: int = SOVRAPPOSIZIONE) -> list[str]:
    """Spezza il testo su confini di frase, con un po' di sovrapposizione.

    La sovrapposizione evita che un reperto a cavallo di due frammenti venga
    perso da entrambi.
    """
    testo = re.sub(r"\s+", " ", (testo or "").strip())
    if not testo:
        return []
    if len(testo) <= dimensione:
        return [testo]

    frasi = re.split(r"(?<=[.;:!?])\s+", testo)
    pezzi, corrente = [], ""
    for frase in frasi:
        if len(corrente) + len(frase) + 1 <= dimensione:
            corrente = f"{corrente} {frase}".strip()
        else:
            if corrente:
                pezzi.append(corrente)
            # riparto includendo la coda del frammento precedente
            coda = corrente[-sovrapposizione:] if corrente else ""
            corrente = f"{coda} {frase}".strip() if coda else frase
            while len(corrente) > dimensione:  # frase piu' lunga del frammento
                pezzi.append(corrente[:dimensione])
                corrente = corrente[dimensione - sovrapposizione:]
    if corrente:
        pezzi.append(corrente)
    return pezzi


# --- Embedding -------------------------------------------------------------


def _chiedi_embedding(model: str, testi: list[str]) -> list[list[float]]:
    """Chiama Ollama, con ripiego sull'endpoint vecchio se serve."""
    payload = {"model": model, "input": testi}
    try:
        with core.post_ollama(payload, OLLAMA_EMBED_URL, TIMEOUT_LLM) as resp:
            dati = json.loads(resp.read().decode())
        if dati.get("embeddings"):
            return dati["embeddings"]
    except core.ErroreOllama:
        pass  # installazioni precedenti: /api/embeddings, un testo per volta

    vettori = []
    for t in testi:
        with core.post_ollama({"model": model, "prompt": t},
                              OLLAMA_EMBED_URL_LEGACY, TIMEOUT_LLM) as resp:
            vettori.append(json.loads(resp.read().decode())["embedding"])
    return vettori


def _normalizza(v: np.ndarray) -> np.ndarray:
    norma = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(norma == 0, 1, norma)


def vettorizza(model: str, testi: list[str]) -> np.ndarray:
    """Vettori normalizzati: cosi' la similarita' coseno e' un prodotto scalare."""
    grezzi = np.array(_chiedi_embedding(model, testi), dtype=np.float32)
    return _normalizza(grezzi)


# --- Indicizzazione --------------------------------------------------------


def indicizza(conn: sqlite3.Connection, sha: str, testo: str,
              model: str = MODELLO_EMBEDDING) -> int:
    """Sostituisce i frammenti di un documento. Restituisce quanti ne ha scritti."""
    pezzi = frammenta(testo)
    if not pezzi:
        return 0
    vettori = vettorizza(model, pezzi)
    conn.execute("DELETE FROM frammenti WHERE sha256 = ?", (sha,))
    conn.executemany(
        "INSERT INTO frammenti (sha256, ordine, testo, modello, vettore) "
        "VALUES (?,?,?,?,?)",
        [(sha, i, p, model, v.tobytes()) for i, (p, v) in enumerate(zip(pezzi, vettori, strict=True))])
    conn.commit()
    return len(pezzi)


def da_indicizzare(conn: sqlite3.Connection,
                   model: str = MODELLO_EMBEDDING) -> list[sqlite3.Row]:
    """Documenti con testo ma senza frammenti aggiornati per questo modello."""
    return conn.execute(
        """SELECT t.sha256, t.testo, f.nome_file FROM testi t
           JOIN file_processati f ON f.sha256 = t.sha256
           WHERE NOT EXISTS (SELECT 1 FROM frammenti fr
                             WHERE fr.sha256 = t.sha256 AND fr.modello = ?)""",
        (model,)).fetchall()


def stato(conn: sqlite3.Connection, model: str = MODELLO_EMBEDDING) -> tuple[int, int]:
    """(documenti indicizzati, frammenti totali) per il modello indicato."""
    r = conn.execute(
        "SELECT COUNT(DISTINCT sha256), COUNT(*) FROM frammenti WHERE modello = ?",
        (model,)).fetchone()
    return r[0], r[1]


# --- Ricerca ---------------------------------------------------------------


def cerca(conn: sqlite3.Connection, domanda: str, quanti: int = 5,
          model: str = MODELLO_EMBEDDING) -> list[dict]:
    """Frammenti piu' vicini alla domanda, dal piu' pertinente."""
    righe = conn.execute(
        """SELECT fr.id, fr.sha256, fr.testo, fr.vettore,
                  d.tipo, d.data_documento, d.titolo, fp.nome_file
           FROM frammenti fr
           JOIN file_processati fp ON fp.sha256 = fr.sha256
           LEFT JOIN documenti d ON d.sha256 = fr.sha256
           WHERE fr.modello = ?""", (model,)).fetchall()
    if not righe or not domanda.strip():
        return []

    matrice = np.vstack([np.frombuffer(r["vettore"], dtype=np.float32) for r in righe])
    q = vettorizza(model, [domanda])[0]
    if q.shape[0] != matrice.shape[1]:
        return []  # indice creato con un modello di dimensione diversa
    punteggi = matrice @ q

    migliori = np.argsort(-punteggi)[:quanti]
    return [{"testo": righe[i]["testo"], "tipo": righe[i]["tipo"],
             "data": righe[i]["data_documento"], "titolo": righe[i]["titolo"],
             "nome_file": righe[i]["nome_file"],
             "punteggio": float(punteggi[i])} for i in migliori]


def brani_per_contesto(brani: list[dict], soglia: float = 0.35) -> str:
    """Passaggi in Markdown, pronti da inserire nel contesto del modello."""
    utili = [b for b in brani if b["punteggio"] >= soglia]
    if not utili:
        return ""
    righe = ["## Passaggi pertinenti dai referti narrativi"]
    for b in utili:
        testa = core.etichetta_tipo(b["tipo"]) if b["tipo"] else "Documento"
        if b["data"]:
            testa += f" — {b['data']}"
        righe.append(f"\n**{testa}**"
                     + (f" · _{b['titolo']}_" if b["titolo"] else "")
                     + f"\n{b['testo']}")
    return "\n".join(righe)
