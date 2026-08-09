"""AHIA — preparazione di un quesito pseudonimizzato per un modello esterno.

Questo modulo non effettua invii: costruisce il minimo indispensabile perche'
la domanda sia clinicamente sensata. Revisione, pseudonimizzazione e invio sono
gestiti dal flusso Secondo parere.
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

import datetime as dt
import sqlite3

import core

# --- Minimizzazione strutturale --------------------------------------------


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


def quadro_minimizzato(conn: sqlite3.Connection, n_referti: int, *,
                       eta: str = "fascia", includi_bmi: bool = True,
                       includi_note: bool = False,
                       tipi: list[str] | None = None,
                       sha_singolo: str | None = None) -> str:
    """Tabella degli esami minimizzata prima della pseudonimizzazione.

    Escluso sempre: nome, laboratorio, nomi dei file, date assolute.
    Le date diventano intervalli relativi al primo prelievo incluso.

    Ambito selezionabile:
    - `sha_singolo`: solo i valori di quel referto;
    - `tipi`: solo i prelievi dei referti di quei tipi;
    - altrimenti: gli ultimi `n_referti` prelievi, come prima.
    """
    if sha_singolo:
        date = [r[0] for r in conn.execute(
            "SELECT DISTINCT data_prelievo FROM risultati WHERE sha256 = ? "
            "ORDER BY data_prelievo DESC", (sha_singolo,))]
    elif tipi:
        segna = ",".join("?" * len(tipi))
        date = [r[0] for r in conn.execute(
            f"""SELECT DISTINCT r.data_prelievo FROM risultati r
                JOIN documenti d ON d.sha256 = r.sha256
                WHERE d.tipo IN ({segna})
                ORDER BY r.data_prelievo DESC""", tipi)]
    else:
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


def quadro_descrittivi(conn: sqlite3.Connection, *,
                       tipi: list[str] | None = None,
                       sha_singolo: str | None = None) -> str:
    """Testo dei referti descrittivi selezionati per la nuova pipeline.

    Il testo resta integro: rilevazione e pseudonimizzazione vengono applicate
    una sola volta al quesito completo. La data del documento nell'intestazione
    resta limitata all'anno. Struttura e laboratorio sono esclusi.
    """
    if sha_singolo:
        righe = conn.execute(
            """SELECT d.tipo, d.data_documento, t.testo, d.sintesi
               FROM documenti d LEFT JOIN testi t ON t.sha256 = d.sha256
               WHERE d.sha256 = ?""", (sha_singolo,)).fetchall()
    elif tipi:
        segna = ",".join("?" * len(tipi))
        righe = conn.execute(
            f"""SELECT d.tipo, d.data_documento, t.testo, d.sintesi
                FROM documenti d LEFT JOIN testi t ON t.sha256 = d.sha256
                WHERE d.tipo IN ({segna})
                ORDER BY d.data_documento DESC""", tipi).fetchall()
    else:
        return ""
    if not righe:
        return ""

    from config import TIPI
    blocchi = []
    for r in righe:
        anno = (r["data_documento"] or "")[:4] or "anno ignoto"
        etichetta = TIPI.get(r["tipo"], {}).get("label", "Referto")
        corpo = (r["testo"] or r["sintesi"] or "").strip()
        if not corpo:
            continue
        blocchi.append(f"— {etichetta} ({anno})\n{corpo}")
    if not blocchi:
        return ""
    return "**Referti descrittivi** (da pseudonimizzare)\n\n" + "\n\n".join(blocchi)


# --- Costruzione del quesito -----------------------------------------------

INTESTAZIONE = {
    "it": """Agisci come un medico di medicina interna che commenta esami di
laboratorio per un collega, non per il paziente. Ti sottopongo i risultati di
una persona in forma pseudonimizzata: non ho la storia clinica completa, non ho l'esame
obiettivo e NON ti sto chiedendo una diagnosi.

Vorrei, in questo ordine:
1. una lettura d'insieme: cosa raccontano questi valori letti insieme, non uno
   per uno, e come si muovono nel tempo;
2. quali alterazioni meritano attenzione e quali sono verosimilmente irrilevanti
   o borderline, distinguendo le due cose;
3. i collegamenti tra esami che un occhio esperto noterebbe (per esempio pattern
   epatici, marziali, tiroidei, metabolici) e che a me potrebbero sfuggire;
4. quali approfondimenti o esami di conferma avrebbero senso, e perche';
5. quali domande converrebbe che io ponessi al medico curante alla prossima
   visita;
6. eventuali incongruenze nei dati che ti fanno sospettare un errore di lettura
   del referto piu' che un problema clinico.

Vincoli, importanti:
- Non formulare una diagnosi e non proporre terapie o dosaggi: quello spetta a
  chi ha in cura la persona e ne conosce il quadro completo.
- Distingui sempre cio' che i dati mostrano da cio' che ipotizzi: se stai
  supponendo, dillo.
- Se un'informazione ti manca per rispondere, indica quale invece di darla per
  scontata.
- Non drammatizzare ne' rassicurare oltre quello che i numeri consentono: un
  valore lievemente fuori norma spesso non significa nulla di per se'.
- Ragiona su intervalli di riferimento generali per adulti; dove il sesso o
  l'eta' cambiano l'interpretazione, tienine conto.

Struttura la risposta con: un riepilogo in tre-quattro righe, poi i punti sopra,
poi in chiusura le domande per il medico. Scrivi in italiano piano, spiegando i
termini tecnici la prima volta che li usi.""",
    "en": """Act as an internal medicine physician commenting on lab results for
a colleague, not for the patient. Below are one person's results, pseudonymised: I
do not have the full clinical history, I have no physical examination, and I am
NOT asking for a diagnosis.

I would like, in this order:
1. an overall reading: what these values say taken together, not one by one, and
   how they move over time;
2. which abnormalities deserve attention and which are likely irrelevant or
   borderline, keeping the two apart;
3. the links between tests that an expert eye would catch (e.g. hepatic, iron,
   thyroid, metabolic patterns) and that I might miss;
4. what follow-up or confirmatory tests would make sense, and why;
5. what questions I should put to the treating physician at the next visit;
6. any inconsistencies in the data that point to a report-reading error rather
   than a clinical problem.

Constraints, important:
- Do not give a diagnosis and do not suggest treatments or dosages: that is for
  whoever is treating the person and knows the full picture.
- Always separate what the data shows from what you are inferring; if you are
  speculating, say so.
- If something is missing for you to answer, name it rather than assume it.
- Do not over-dramatise or over-reassure beyond what the numbers support: a
  mildly out-of-range value often means nothing on its own.
- Reason on general adult reference ranges; where sex or age change the reading,
  take that into account.

Structure the answer as: a three-to-four line summary, then the points above,
then the questions for the physician at the end. Write in plain language,
explaining technical terms the first time you use them.""",
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
