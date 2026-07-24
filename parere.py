"""AHIA — preparazione di un quesito anonimizzato per un modello esterno.

Il testo prodotto non viene inviato da nessuna parte: viene mostrato all'utente,
che lo verifica e decide se copiarlo altrove. Qui si costruisce il minimo
indispensabile perche' la domanda sia clinicamente sensata, e nulla di piu'.
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

import datetime as dt
import re
import sqlite3

import core

# --- Anonimizzazione -------------------------------------------------------


def fascia_eta(anno_nascita: int | None, ampiezza: int = 5) -> str:
    """Fascia d'eta' invece dell'eta' esatta: meno identificante, ugualmente utile."""
    if not anno_nascita:
        return "non indicata"
    eta = dt.date.today().year - int(anno_nascita)
    base = (eta // ampiezza) * ampiezza
    return f"{base}-{base + ampiezza - 1} anni"


def _scaletta_tempi(date: list[str]) -> dict[str, str]:
    """Date reali -> etichette relative (T0, +6 mesi, +14 mesi...).

    Una data illeggibile non deve far cadere la pagina: viene etichettata
    come tale e il resto della scaletta resta valido.
    """
    valide = {}
    for d in date:
        try:
            valide[d] = dt.date.fromisoformat(core.normalizza_data(d))
        except ValueError:
            continue
    if not valide:
        return {d: "data non disponibile" for d in date}
    prima = min(valide.values())
    scala = {d: "data non disponibile" for d in date}
    for d, quando in valide.items():
        mesi = round((quando - prima).days / 30.44)
        scala[d] = "T0" if mesi == 0 else f"+{mesi} mesi"
    return scala


def quadro_anonimo(conn: sqlite3.Connection, n_referti: int, *,
                   eta: str = "fascia", includi_bmi: bool = True,
                   includi_note: bool = False) -> str:
    """Tabella degli esami senza dati identificativi.

    Escluso sempre: nome, laboratorio, nomi dei file, date assolute.
    Le date diventano intervalli relativi al primo prelievo incluso.
    """
    date = [r[0] for r in conn.execute(
        "SELECT DISTINCT data_prelievo FROM risultati "
        "ORDER BY data_prelievo DESC LIMIT ?", (n_referti,))]
    if not date:
        return ""
    scala = _scaletta_tempi(date)

    p = core.leggi_profilo(conn)
    righe_profilo = []
    if eta == "esatta" and p.get("anno_nascita"):
        righe_profilo.append(
            f"- Eta': {dt.date.today().year - int(p['anno_nascita'])} anni")
    elif eta == "fascia":
        righe_profilo.append(f"- Fascia d'eta': {fascia_eta(p.get('anno_nascita'))}")
    if p.get("sesso"):
        righe_profilo.append(f"- Sesso biologico: {p['sesso']}")
    if includi_bmi:
        bmi = core.calcola_bmi(p.get("altezza_cm"), p.get("peso_kg"))
        if bmi:
            righe_profilo.append(f"- BMI: {bmi}")
    if includi_note:
        if p.get("terapie"):
            righe_profilo.append(f"- Terapie in corso: {p['terapie']}")
        if p.get("note"):
            righe_profilo.append(f"- Note: {p['note']}")

    storico: dict[str, list] = {}
    for r in conn.execute(
        f"""SELECT data_prelievo, analita, valore_testo, unita, range_min,
                   range_max, flag FROM risultati
            WHERE data_prelievo IN ({','.join('?' * len(date))})
            ORDER BY analita, data_prelievo""", date):
        storico.setdefault(r["analita"], []).append(r)

    tabella = ["| Esame | Valore | Unita' | Riferimento | Stato | Precedenti |",
               "|---|---|---|---|---|---|"]
    for analita, valori in sorted(storico.items()):
        u = valori[-1]
        prec = " → ".join(f"{v['valore_testo']} ({scala[v['data_prelievo']]})"
                          for v in valori[:-1]) or "-"
        rif = "-"
        if u["range_min"] is not None or u["range_max"] is not None:
            rif = (f"{u['range_min'] if u['range_min'] is not None else ''}–"
                   f"{u['range_max'] if u['range_max'] is not None else ''}")
        stato = {"L": "BASSO", "H": "ALTO", "N": "norma"}.get(u["flag"] or "", "?")
        tabella.append(f"| {analita} | {u['valore_testo']} | {u['unita']} | "
                       f"{rif} | {stato} | {prec} |")

    intervallo = f"{len(date)} prelievi distribuiti su {scala[max(date)]}"
    return ("**Soggetto**\n" + "\n".join(righe_profilo)
            + f"\n\n**Esami** ({intervallo}, l'ultimo indicato per primo nei valori)\n\n"
            + "\n".join(tabella))


# --- Costruzione del quesito -----------------------------------------------

INTESTAZIONE = {
    "it": """Ti sottopongo esami di laboratorio di una persona, in forma anonima.
Non ho la storia clinica completa e non sto chiedendo una diagnosi.

Vorrei:
1. la tua lettura d'insieme dei valori e del loro andamento nel tempo;
2. quali alterazioni meritano attenzione e quali sono verosimilmente irrilevanti;
3. quali approfondimenti o esami di conferma avrebbero senso;
4. quali domande converrebbe porre al medico curante;
5. eventuali incongruenze nei dati che ti fanno sospettare un errore di
   trascrizione.

Se un'informazione ti manca per rispondere, dimmi quale invece di supporla.""",
    "en": """Below are laboratory results for one anonymous individual.
I do not have the full clinical history and I am not asking for a diagnosis.

I would like:
1. your overall reading of the values and of how they move over time;
2. which abnormalities deserve attention and which are likely irrelevant;
3. what follow-up or confirmatory tests would make sense;
4. what questions would be worth putting to the treating physician;
5. any inconsistencies in the data that suggest a transcription error.

If something is missing for you to answer, say what it is rather than assume
it.""",
}

CHIUSURA = {
    "it": "\n\nI dati provengono da un'estrazione automatica di referti PDF e "
          "potrebbero contenere errori di lettura.",
    "en": "\n\nThe data comes from automated extraction of PDF reports and may "
          "contain reading errors.",
}


def componi(quadro: str, sintesi: str = "", lingua: str = "it") -> str:
    parti = [INTESTAZIONE.get(lingua, INTESTAZIONE["it"]), quadro]
    if sintesi.strip():
        titolo = ("**Sintesi prodotta da un modello locale** (da verificare, "
                  "non darla per buona)" if lingua == "it" else
                  "**Summary produced by a local model** (unverified, treat with "
                  "caution)")
        parti.append(f"{titolo}\n\n{sintesi.strip()}")
    return "\n\n".join(parti) + CHIUSURA.get(lingua, CHIUSURA["it"])


# --- Controllo prima dell'invio --------------------------------------------

_CONTROLLI = [
    (re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b"), "un codice fiscale"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "un indirizzo email"),
    (re.compile(r"(?<!\d)(?:\+39\s?)?3\d{2}[\s.-]?\d{6,7}(?!\d)"), "un numero di telefono"),
    (re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"), "una data in chiaro"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "una data in chiaro"),
    (re.compile(r"\b(?:via|viale|piazza|corso)\s+\w+", re.I), "un indirizzo"),
]


def verifica(testo: str, profilo: dict) -> list[str]:
    """Segnalazioni su possibili dati identificativi rimasti nel testo."""
    avvisi = []
    for schema, descrizione in _CONTROLLI:
        if schema.search(testo):
            avvisi.append(f"Il testo sembra contenere {descrizione}.")
    nome = (profilo.get("nome") or "").strip()
    if len(nome) > 2 and re.search(rf"\b{re.escape(nome)}\b", testo, re.I):
        avvisi.append("Compare il nome indicato nel profilo.")
    return sorted(set(avvisi))
