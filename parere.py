"""AHIA — preparazione di un quesito anonimizzato per un modello esterno.

Il testo prodotto non viene inviato da nessuna parte: viene mostrato all'utente,
che lo verifica e decide se copiarlo altrove. Qui si costruisce il minimo
indispensabile perche' la domanda sia clinicamente sensata, e nulla di piu'.
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
                   includi_note: bool = False,
                   tipi: list[str] | None = None,
                   sha_singolo: str | None = None) -> str:
    """Tabella degli esami senza dati identificativi.

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
    """Testo anonimizzato dei referti descrittivi selezionati.

    Ogni referto passa da oscura_testo, che toglie i dati identificativi
    strutturati. Le date assolute diventano l'anno soltanto, per non fissare il
    momento pur mantenendo l'ordine. Struttura e laboratorio sono esclusi.
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

    p = core.leggi_profilo(conn)
    from config import TIPI
    blocchi = []
    for r in righe:
        anno = (r["data_documento"] or "")[:4] or "anno ignoto"
        etichetta = TIPI.get(r["tipo"], {}).get("label", "Referto")
        corpo = (r["testo"] or r["sintesi"] or "").strip()
        if not corpo:
            continue
        corpo = oscura_testo(corpo, p)
        blocchi.append(f"— {etichetta} ({anno})\n{corpo}")
    if not blocchi:
        return ""
    return "**Referti descrittivi** (anonimizzati)\n\n" + "\n\n".join(blocchi)


# --- Costruzione del quesito -----------------------------------------------

INTESTAZIONE = {
    "it": """Agisci come un medico di medicina interna che commenta esami di
laboratorio per un collega, non per il paziente. Ti sottopongo i risultati di
una persona in forma anonima: non ho la storia clinica completa, non ho l'esame
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
a colleague, not for the patient. Below are one person's results, anonymised: I
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


# --- Controllo prima dell'invio --------------------------------------------

_CONTROLLI = [
    (re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b"), "un codice fiscale"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "un indirizzo email"),
    (re.compile(r"(?<!\d)(?:\+39\s?)?3\d{2}[\s.-]?\d{6,7}(?!\d)"), "un numero di telefono"),
    (re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"), "una data in chiaro"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "una data in chiaro"),
    (re.compile(r"\b(?:via|viale|piazza|corso)\s+\w+", re.I), "un indirizzo"),
    (re.compile(r"\b\d{10,}\b"), "un identificativo numerico lungo"),
    (re.compile(r"\b[A-Z]{1,3}\d{5,}\b"), "un codice alfanumerico"),
    (re.compile(r"\b(?:referto|prot|accettazione|pratica|cartella|nosologic|"
                r"episodio|prestazion)\w*\.?\s*[:n°.\\/i]*\s*[A-Z]{0,3}\d", re.I),
     "un numero di referto o episodio"),
]

# Sostituzioni attive per i testi liberi dei referti descrittivi: dove la tabella
# dei valori è già anonima per costruzione, il testo di una visita può contenere
# dati identificativi. Qui li oscuriamo prima di comporre il quesito.
_OSCURA = [
    (re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b"), "[codice fiscale]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[email]"),
    (re.compile(r"(?<!\d)(?:\+39\s?)?3\d{2}[\s.-]?\d{6,7}(?!\d)"), "[telefono]"),
    (re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"), "[data]"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "[data]"),
    (re.compile(r"\b(?:via|viale|piazza|corso|largo|vicolo)\s+[\w' ]+?\d*\b",
                re.I), "[indirizzo]"),
    # numeri di referto, pratica, accettazione, cartella, nosologico, episodio
    (re.compile(r"\b(?:referto|refert[oi]|nr|n[°.]?|prot(?:ocollo)?|"
                r"accettazione|acc|pratica|cartella|nosologic[oa]|id|codice|"
                r"episodio|prestazion[ei]|ricovero|impegnativa)\.?\s*"
                r"[:n°.\\/i]*\s*[A-Z]{0,3}\d[\w/./-]*", re.I),
     "[numero di referto]"),
    # codice alfanumerico lungo (1-3 lettere + 5+ cifre): es. EP2300018443
    (re.compile(r"\b[A-Z]{1,3}\d{5,}\b"), "[identificativo]"),
    # tessera sanitaria / codice a barre lungo (10+ cifre consecutive)
    (re.compile(r"\b\d{10,}\b"), "[identificativo]"),
    # date scritte a parole: 15 giugno 2024
    (re.compile(r"\b\d{1,2}\s+(?:gennaio|febbraio|marzo|aprile|maggio|giugno|"
                r"luglio|agosto|settembre|ottobre|novembre|dicembre)\s+\d{4}\b",
                re.I), "[data]"),
    # nomi di struttura sanitaria: la riga con la parola-chiave viene oscurata
    (re.compile(r"\b(?:poliambulatorio|ambulatorio|ospedale|ospedaliera?|"
                r"clinica|casa\s+di\s+cura|presidio|policlinico|istituto|"
                r"fondazione|A\.?S\.?S\.?T\.?|A\.?S\.?L\.?|A\.?O\.?|IRCCS|"
                r"centro\s+medico|laboratorio\s+analisi|studio\s+medico)"
                r"[^\n]*", re.I), "[struttura sanitaria]"),
    # valore dopo un'etichetta anagrafica: "Cognome: ROSSI", "Nome: Mario".
    # Richiede i due punti per non catturare intestazioni come "DATI ASSISTITO".
    (re.compile(r"\b(cognome|nome|paziente|assistito|paz\.?)\s*:\s*"
                r"[A-ZÀ-Ù][\wà-ù']+(?:\s+[A-ZÀ-Ù][\wà-ù']+){0,2}", re.I),
     r"\1: [nome]"),
    (re.compile(r"\b(nat[oa]\s+(?:il\s+\[data\]\s+)?a|luogo\s+di\s+nascita|"
                r"residente\s+(?:a|in)|domiciliat[oa]\s+(?:a|in)|comune)\s*:?\s*"
                r"[A-ZÀ-Ù][\wà-ù' ]+?(?=\s+in\b|\s*$|\s*\n|,)", re.I | re.M),
     r"\1 [luogo]"),
    # nome isolato in maiuscolo seguito da un codice numerico: "BRUNO 445566"
    (re.compile(r"^\s*[A-ZÀ-Ù][A-ZÀ-Ù']{2,}(?:\s+[A-ZÀ-Ù']+){0,2}\s+\d{3,}\s*$",
                re.M), "[nome] [identificativo]"),
    # medico firmatario: "FIRMATO DA Rossi Dott.ssa Anna", "a cura del Dr. Bianchi".
    # Gli spazi interni sono [ \t] (non \s) per non attraversare i ritorni a capo
    # e sconfinare sulla riga successiva, che può contenere dati clinici.
    (re.compile(r"\b(firmato[ \t]+da|refertato[ \t]+da|a[ \t]+cura[ \t]+d[ei]l?|"
                r"dott(?:\.ssa|oressa|ore|\.)?|dr(?:\.ssa|\.)?|prof(?:\.ssa|\.)?)"
                r"[ \t]*:?[ \t]*[A-ZÀ-Ù][\wà-ù'.]+"
                r"(?:[ \t]+(?:dott\.ssa|dott\.|dr\.|[A-ZÀ-Ù][\wà-ù'.]+)){0,3}",
                re.I), "[medico]"),
    # numero R.E.A. e simili sigle camerali: "R.E.A.: MI-1040877"
    (re.compile(r"\bR\.?E\.?A\.?\s*:?\s*[A-Z]{0,2}[-\s]?\d{4,}", re.I),
     "[numero REA]"),
    # sito web / URL
    (re.compile(r"\b(?:https?://)?(?:www\.)[\w.-]+\.[a-z]{2,}(?:/\S*)?", re.I),
     "[sito web]"),
    (re.compile(r"\[?(?:https?://)[\w.-]+\.[a-z]{2,}[^\s\])]*\]?", re.I),
     "[sito web]"),
    # telefono/fax fisso italiano: "02. 8350.0010", "+39 02 8350 0010"
    (re.compile(r"(?:tel|fax|telefono)\.?\s*:?\s*(?:\+39\s?)?0\d[\d.\s/-]{5,}",
                re.I), "[telefono]"),
]

# Titoli e cortesie che precedono un cognome: aiutano a beccare il nome anche
# quando nel referto compare in forma diversa dal profilo.
_TITOLI = re.compile(
    r"\b(?:sig\.?(?:ra)?|signor[ae]?|gent\.?(?:mo|ma)?|egr\.?|"
    r"paziente|assistito|nato\s+a|nata\s+a)\b[:\s]*"
    r"([A-Z][a-zà-ù']+(?:\s+[A-Z][a-zà-ù']+){0,2})", re.I)


def oscura_testo(testo: str, profilo: dict | None = None) -> str:
    """Sostituisce nel testo libero i dati identificativi riconoscibili.

    Non è garanzia assoluta — un nome di medico o una struttura scritti in chiaro
    possono sfuggire — ma toglie di mezzo i pattern strutturati (codici fiscali,
    email, telefoni, date, indirizzi, numeri di referto) e il nome del profilo,
    incluse le singole parti (solo il cognome, ordine invertito). La verifica
    finale resta a valle come ultima rete.
    """
    for schema, rimpiazzo in _OSCURA:
        testo = schema.sub(rimpiazzo, testo)

    # Nome del profilo: prima la stringa intera, poi ogni parola lunga (>=3),
    # così "Rossi" da solo o "ROSSI MARIO" invertito vengono comunque oscurati.
    if profilo:
        nome = (profilo.get("nome") or "").strip()
        if len(nome) > 2:
            testo = re.sub(rf"\b{re.escape(nome)}\b", "[nome]", testo, flags=re.I)
            for parte in nome.split():
                if len(parte) >= 3:
                    testo = re.sub(rf"\b{re.escape(parte)}\b", "[nome]",
                                   testo, flags=re.I)

    # Cognome dopo un titolo di cortesia, anche se non è nel profilo
    testo = _TITOLI.sub(lambda m: m.group(0).replace(m.group(1), "[nome]"), testo)
    return testo


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
