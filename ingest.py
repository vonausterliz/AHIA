"""AHIA — estrazione strutturata da referti PDF (nativi o scansionati)."""

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
import re
import unicodedata
from pathlib import Path

import core
from config import (
    ALIAS_BASE, CONVERSIONI, DPI_RASTER, FUNZIONI, MIN_CHARS_PAGINA,
    RITENTATIVI_ESTRAZIONE, TIPI,
)

SCHEMA = {
    "type": "object",
    "properties": {
        "laboratorio": {"type": "string"},
        "data_prelievo": {"type": "string"},
        "esami": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nome_referto": {"type": "string"},
                    "valore": {"type": "string"},
                    "unita": {"type": "string"},
                    "range_min": {"type": ["number", "null"]},
                    "range_max": {"type": ["number", "null"]},
                    "flag": {"type": "string", "enum": ["N", "L", "H", ""]},
                },
                "required": ["nome_referto", "valore", "unita"],
            },
        },
    },
    "required": ["laboratorio", "data_prelievo", "esami"],
}

PROMPT = """Sei un estrattore di dati da referti di laboratorio italiani.
Estrai TUTTI gli esami presenti, uno per riga della tabella.

Regole tassative:
- nome_referto: la dicitura ESATTA del referto, non tradotta ne' normalizzata.
- valore: stringa nella forma originale ("12,4", "<0.01", "negativo").
  NON convertire la virgola decimale.
- unita: come appare ("mg/dL", "10^3/uL", ""). Vuota se assente.
- range_min / range_max: numeri dall'intervallo di riferimento della RIGA stessa,
  con il punto come separatore decimale; null se assenti o non numerici.
  Per "< 200": range_min null, range_max 200.
- flag: "L" basso, "H" alto, "N" normale, "" se non indicato.
- data_prelievo in formato YYYY-MM-DD: quella del prelievo o dell'accettazione,
  non quella di stampa.
- Non inventare valori: se un campo non e' leggibile, ometti l'esame.

Rispondi SOLO con il JSON conforme allo schema."""


# --- Utilita' --------------------------------------------------------------


def slug(testo: str) -> str:
    """Chiave di confronto: minuscolo, senza accenti ne' punteggiatura."""
    t = unicodedata.normalize("NFKD", testo)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", t)).strip()


def parse_valore(raw: str) -> tuple[float | None, str, str]:
    """(valore_numerico, operatore, testo_originale)."""
    testo = (raw or "").strip()
    m = re.match(r"^\s*(<=|>=|<|>)?\s*"
                 r"([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]+|[0-9]*[.,]?[0-9]+)", testo)
    if not m:
        return None, "", testo
    numero = m.group(2)
    if "," in numero:  # formato italiano: il punto separa le migliaia
        numero = numero.replace(".", "").replace(",", ".")
    try:
        return float(numero), m.group(1) or "", testo
    except ValueError:
        return None, m.group(1) or "", testo


def carica_alias(path: Path) -> dict[str, str]:
    alias = dict(ALIAS_BASE)
    if path.exists():
        alias.update(json.loads(path.read_text(encoding="utf-8")))
    return alias


# --- Lettura ed estrazione -------------------------------------------------


def _metriche(risposta: dict, model: str, etichetta: str) -> dict:
    """Metriche della chiamata, dai contatori che Ollama restituisce."""
    def secondi(ns):
        return round((risposta.get(ns) or 0) / 1e9, 2)

    prompt_tok = risposta.get("prompt_eval_count") or 0
    out_tok = risposta.get("eval_count") or 0
    gen_s = secondi("eval_duration")
    return {
        "fase": etichetta,
        "modello": model,
        "totale_s": secondi("total_duration"),
        "caricamento_s": secondi("load_duration"),
        "token_in": prompt_tok,
        "token_out": out_tok,
        "tok_s": round(out_tok / gen_s, 1) if gen_s else None,
    }


def _chiama(model: str, funzione: str, contenuto: str,
            immagini: list[str] | None = None,
            etichetta: str = "", istruzione_layout: str = "") -> tuple[dict, dict]:
    messaggio = {"role": "user", "content": contenuto}
    if immagini:
        messaggio["images"] = immagini
    sistema = PROMPT
    if istruzione_layout:
        sistema += ("\n\nISTRUZIONI SPECIFICHE PER QUESTO LAYOUT (scoperte da "
                    "un'analisi precedente, seguile con attenzione):\n"
                    + istruzione_layout)
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": sistema}, messaggio],
        "format": SCHEMA,
        "stream": False,
        "think": FUNZIONI[funzione]["think"],
        "options": {"temperature": FUNZIONI[funzione]["temperature"],
                    "num_ctx": FUNZIONI[funzione]["num_ctx"]},
    }
    with core.post_ollama(payload) as resp:
        risposta = json.loads(resp.read().decode())
    testo = risposta["message"]["content"]
    dati = json.loads(re.sub(r"^```(?:json)?|```$", "", testo.strip(),
                             flags=re.MULTILINE).strip())
    return dati, _metriche(risposta, model, etichetta or funzione)


def _pagine_testo(path: Path, progress=None) -> str | None:
    """Testo del PDF, oppure None se e' una scansione."""
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        if progress:
            progress(f"{len(pdf.pages)} pagine da leggere")
        pagine = [p.extract_text(layout=True) or "" for p in pdf.pages]
    utile = sum(len(p.strip()) for p in pagine) >= MIN_CHARS_PAGINA * max(1, len(pagine))
    return "\n\n--- pagina ---\n\n".join(pagine) if utile else None


def _pagine_immagini(path: Path) -> list[str]:
    """Pagine rasterizzate in PNG base64."""
    import fitz  # PyMuPDF

    doc = fitz.open(path)
    try:
        zoom = fitz.Matrix(DPI_RASTER / 72, DPI_RASTER / 72)
        return [base64.b64encode(p.get_pixmap(matrix=zoom).tobytes("png")).decode()
                for p in doc]
    finally:
        doc.close()


def elabora_documento(path: Path, modelli: dict, tipo_forzato: str | None = None,
                      progress=None, istruzione_layout: str = "",
                      scheda_per_lab=None) -> dict:
    """Legge un documento sanitario, lo classifica ed estrae cio' che serve.

    Se `scheda_per_lab` e' una funzione, viene chiamata col laboratorio dedotto
    dalla classificazione: se restituisce una scheda di lettura, questa viene
    usata gia' alla prima (e unica) estrazione, senza doppioni.

    Restituisce:
      tipo, data_documento, titolo, struttura, origine ("nativo"/"scansione"),
      esami (solo per i referti tabellari), narrativa (solo per gli altri),
      log (metriche di ogni chiamata al modello).
    """
    log: list[dict] = []
    if progress:
        progress(f"Apertura di {path.name} ({path.stat().st_size / 1024:.0f} KB)")
    testo = _pagine_testo(path, progress)
    if testo is not None:
        immagini = []
        if progress:
            progress(f"PDF nativo: {len(testo)} caratteri di testo estratti")
    else:
        if progress:
            progress(f"Nessuno strato di testo: rasterizzazione a {DPI_RASTER} DPI…")
        immagini = _pagine_immagini(path)
        if progress:
            progress(f"{len(immagini)} pagine convertite in immagine")
    origine = "nativo" if testo is not None else "scansione"

    def chiama(model, funzione, contenuto, imgs=None, etichetta="", layout=None):
        istr = layout if layout is not None else istruzione_layout
        dati, metrica = core.con_battito(
            lambda: _chiama(model, funzione, contenuto, imgs, etichetta,
                            istruzione_layout=istr),
            progress=progress, etichetta=f"{model} · {etichetta or funzione}")
        log.append(metrica)
        if progress:
            progress(_riassunto(metrica))
        return dati

    if istruzione_layout and progress:
        progress("Uso la scheda di lettura nota per questo laboratorio.")

    # 1. tipologia: basta la prima pagina
    if tipo_forzato:
        doc = {"tipo": tipo_forzato, "data_documento": "", "titolo": "",
               "struttura": ""}
        if progress:
            progress(f"Tipologia forzata: {TIPI[tipo_forzato]['label']}")
    else:
        # Per una scansione la classificazione deve usare il modello vision:
        # quello testuale non accetta immagini e fallirebbe.
        mod_classe = (modelli["classificazione"] if testo is not None
                      else modelli["estrazione_vision"])
        if progress:
            progress(f"Riconoscimento del tipo con {mod_classe}…")
        anteprima = (testo[:6000] if testo is not None
                     else "Prima pagina del documento (immagine).")
        doc = classifica(mod_classe, anteprima,
                         immagini[0] if immagini else None)
    tipo = doc.get("tipo", "altro")
    if progress and not tipo_forzato:
        dettagli = [TIPI.get(tipo, TIPI["altro"])["label"]]
        if doc.get("data_documento"):
            dettagli.append(doc["data_documento"])
        if doc.get("struttura"):
            dettagli.append(doc["struttura"])
        progress("Riconosciuto: " + " · ".join(dettagli)
                 + (f" — {doc['motivazione']}" if doc.get("motivazione") else ""))

    # Se conosco il laboratorio dalla classificazione e ho una sua scheda di
    # lettura, la applico gia' a questa estrazione: una sola volta, non due.
    scheda_attiva = istruzione_layout
    if scheda_per_lab and not scheda_attiva:
        lab_dedotto = doc.get("struttura", "")
        if lab_dedotto:
            trovata = scheda_per_lab(lab_dedotto)
            if trovata:
                scheda_attiva = trovata
                if progress:
                    progress(f"Uso la scheda di lettura nota per «{lab_dedotto}».")

    risultato = {"tipo": tipo, "origine": origine,
                 "testo": testo or "",
                 "data_documento": core.normalizza_data(doc.get("data_documento")),
                 "titolo": doc.get("titolo", ""),
                 "struttura": doc.get("struttura", ""),
                 "esami": [], "narrativa": {}, "log": log}

    # 2. estrazione, diversa a seconda della natura del documento
    if TIPI.get(tipo, TIPI["altro"])["tabellare"]:
        if testo is not None:
            if progress:
                progress(f"{TIPI[tipo]['label']}, PDF nativo: estrazione valori…")
            dati = chiama(modelli["estrazione_testo"], "estrazione_testo",
                          "Referto:\n\n" + testo, etichetta="valori",
                          layout=scheda_attiva)
            risultato["esami"] = dati.get("esami", [])
            if progress:
                progress(f"{len(risultato['esami'])} valori letti dalla tabella")
            # l'estrazione legge data e laboratorio dalla tabella: piu' affidabili
            # di quelli dedotti dalla sola prima pagina in fase di classificazione
            risultato["data_documento"] = (core.normalizza_data(
                dati.get("data_prelievo")) or risultato["data_documento"])
            risultato["struttura"] = (dati.get("laboratorio")
                                      or risultato["struttura"])
        else:
            unione = []
            for i, img in enumerate(immagini, 1):
                if progress:
                    progress(f"Scansione: valori dalla pagina {i}/{len(immagini)}…")
                dati = chiama(modelli["estrazione_vision"], "estrazione_vision",
                              f"Referto, pagina {i}. Estrai gli esami.", [img],
                              etichetta=f"valori p.{i}", layout=scheda_attiva)
                unione += dati.get("esami", [])
                risultato["data_documento"] = (
                    risultato["data_documento"]
                    or core.normalizza_data(dati.get("data_prelievo")))
                risultato["struttura"] = (risultato["struttura"]
                                          or dati.get("laboratorio", ""))
            risultato["esami"] = unione
        if not risultato["data_documento"]:
            risultato["data_documento"] = doc.get("data_documento", "")
    else:
        if progress:
            progress(f"{TIPI[tipo]['label']}: sintesi del referto…")
        if testo is not None:
            narrativa = riassumi(modelli["analisi"], "analisi", "Referto:\n\n" + testo)
        else:
            narrativa = riassumi(modelli["estrazione_vision"], "estrazione_vision",
                                 "Referto sanitario, pagine allegate.", immagini)
        risultato["narrativa"] = narrativa
        if progress:
            reperti = narrativa.get("reperti_rilevanti") or []
            progress(f"Sintesi di {len(narrativa.get('sintesi', ''))} caratteri"
                     + (f", {len(reperti)} reperti rilevanti" if reperti else "")
                     + (", conclusioni presenti"
                        if narrativa.get("conclusioni") else ""))

    return risultato


def _riassunto(m: dict) -> str:
    """Riga leggibile da mostrare durante l'elaborazione."""
    return (f"{m['fase']} · {m['modello']} · {m['totale_s']}s · "
            f"{m['token_in']}→{m['token_out']} token"
            + (f" · {m['tok_s']} tok/s" if m["tok_s"] else ""))


# --- Classificazione del documento -----------------------------------------

SCHEMA_TIPO = {
    "type": "object",
    "properties": {
        "tipo": {"type": "string", "enum": list(TIPI)},
        "data_documento": {"type": "string"},
        "titolo": {"type": "string"},
        "struttura": {"type": "string"},
        "motivazione": {"type": "string"},
    },
    "required": ["tipo", "data_documento", "titolo"],
}

PROMPT_TIPO = ("Classifica il documento sanitario italiano che ti viene mostrato.\n\n"
               "Tipologie ammesse:\n"
               + "\n".join(f"- {k}: {v['label']}" for k, v in TIPI.items())
               + """

Regole:
- Scegli la tipologia in base al contenuto, non al nome del file.
- Un referto con una tabella di valori numerici e intervalli di riferimento e'
  un esame di laboratorio: distingui sangue, urine e altro (tampone,
  microbiologia, istologia).
- Un documento descrittivo con un testo discorsivo su un esame per immagini o
  una visita NON e' un esame di laboratorio.
- data_documento in formato YYYY-MM-DD: prelievo, esecuzione dell'esame o
  visita, non la data di stampa.
- titolo: una riga breve che dica di che documento si tratta
  (es. "Ecografia addome completo", "Visita cardiologica di controllo").
- struttura: nome dell'ospedale, laboratorio o ambulatorio, se leggibile.
- motivazione: una riga sul perche' hai scelto quella tipologia.

Rispondi SOLO con il JSON conforme allo schema.""")

SCHEMA_NARRATIVO = {
    "type": "object",
    "properties": {
        "sintesi": {"type": "string"},
        "conclusioni": {"type": "string"},
        "reperti_rilevanti": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["sintesi"],
}

PROMPT_NARRATIVO = """Riassumi il referto sanitario che ti viene mostrato.

- sintesi: da tre a sei righe su cosa e' stato esaminato e cosa e' emerso.
- conclusioni: la conclusione diagnostica riportata nel documento, con le parole
  del documento stesso, sintetizzata se molto lunga. Stringa vuota se assente.
- reperti_rilevanti: elenco breve dei reperti degni di nota, uno per voce; solo
  quelli scritti nel referto.

Non aggiungere interpretazioni tue, non formulare diagnosi e non dedurre nulla
che non sia scritto. Se il documento e' illeggibile, dillo nella sintesi.

Rispondi SOLO con il JSON conforme allo schema."""


def classifica(model: str, contenuto: str, immagine: str | None = None) -> dict:
    """Tipologia, data, titolo e struttura del documento."""
    messaggio = {"role": "user", "content": contenuto}
    if immagine:
        messaggio["images"] = [immagine]
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": PROMPT_TIPO}, messaggio],
        "format": SCHEMA_TIPO, "stream": False,
        "think": FUNZIONI["classificazione"]["think"],
        "options": {"temperature": FUNZIONI["classificazione"]["temperature"],
                    "num_ctx": FUNZIONI["classificazione"]["num_ctx"]},
    }
    with core.post_ollama(payload) as resp:
        testo = json.loads(resp.read().decode())["message"]["content"]
    dati = json.loads(re.sub(r"^```(?:json)?|```$", "", testo.strip(),
                             flags=re.MULTILINE).strip())
    if dati.get("tipo") not in TIPI:
        dati["tipo"] = "altro"
    return dati


def riassumi(model: str, funzione: str, contenuto: str,
             immagini: list[str] | None = None) -> dict:
    """Sintesi di un referto narrativo (ecografia, visita, radiologia)."""
    messaggio: dict = {"role": "user", "content": contenuto}
    if immagini:
        messaggio["images"] = immagini
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": PROMPT_NARRATIVO}, messaggio],
        "format": SCHEMA_NARRATIVO, "stream": False,
        "think": FUNZIONI[funzione]["think"],
        "options": {"temperature": FUNZIONI[funzione]["temperature"],
                    "num_ctx": FUNZIONI[funzione]["num_ctx"]},
    }
    with core.post_ollama(payload) as resp:
        testo = json.loads(resp.read().decode())["message"]["content"]
    return json.loads(re.sub(r"^```(?:json)?|```$", "", testo.strip(),
                             flags=re.MULTILINE).strip())


# --- Proposte di mappatura -------------------------------------------------

SCHEMA_ALIAS = {
    "type": "object",
    "properties": {
        "mappature": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "dicitura": {"type": "string"},
                    "canonico": {"type": "string"},
                    "nota": {"type": "string"},
                },
                "required": ["dicitura", "canonico"],
            },
        },
    },
    "required": ["mappature"],
}

PROMPT_ALIAS = """Sei un esperto di esami di laboratorio italiani. Devi ricondurre
le diciture usate dai laboratori a un nome canonico unico, per poter confrontare
nel tempo referti di laboratori diversi.

Regole tassative:
- Se la dicitura indica LO STESSO esame di un nome canonico gia' esistente, usa
  esattamente quel nome, senza modificarlo.
- Se e' un esame nuovo, proponi un nome canonico in MAIUSCOLO, esteso e senza
  prefissi di matrice (S-, P-, B-) ne' sigle del laboratorio.
- NON unire mai esami diversi: colesterolo HDL e LDL sono distinti, come
  emoglobina ed emoglobina glicata, calcio totale e calcio ionizzato,
  bilirubina totale e diretta.
- La matrice conta quando cambia l'esame: le analisi sulle urine restano
  distinte da quelle sul sangue e vanno prefissate con "URINE ".
- Se non sei ragionevolmente sicuro, riporta la dicitura in maiuscolo cosi'
  com'e' e spiega il dubbio nel campo nota.
- La nota e' una riga breve, solo dove serve.

Rispondi SOLO con il JSON conforme allo schema."""


def proponi_alias(model: str, diciture: list[str],
                  canonici: list[str]) -> dict[str, dict]:
    """{dicitura: {"canonico": ..., "nota": ..., "esistente": bool}}."""
    if not diciture:
        return {}
    richiesta = ("Nomi canonici gia' in uso:\n" + "\n".join(f"- {c}" for c in canonici)
                 + "\n\nDiciture da ricondurre:\n"
                 + "\n".join(f"- {d}" for d in diciture))
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": PROMPT_ALIAS},
                     {"role": "user", "content": richiesta}],
        "format": SCHEMA_ALIAS,
        "stream": False,
        "think": FUNZIONI["dizionario"]["think"],
        "options": {"temperature": FUNZIONI["dizionario"]["temperature"],
                    "num_ctx": FUNZIONI["dizionario"]["num_ctx"]},
    }
    with core.post_ollama(payload) as resp:
        testo = json.loads(resp.read().decode())["message"]["content"]
    dati = json.loads(re.sub(r"^```(?:json)?|```$", "", testo.strip(),
                             flags=re.MULTILINE).strip())

    noti = {c.upper() for c in canonici}
    proposte = {}
    for m in dati.get("mappature", []):
        dicitura = (m.get("dicitura") or "").strip()
        canonico = (m.get("canonico") or "").strip().upper()
        if dicitura in diciture and canonico:
            proposte[dicitura] = {"canonico": canonico,
                                  "nota": (m.get("nota") or "").strip(),
                                  "esistente": canonico in noti}
    return proposte


# --- Normalizzazione -------------------------------------------------------


# Prefissi di matrice usati da molti laboratori: S- siero, P- plasma,
# B- sangue intero, U- urine. Per siero, plasma e sangue l'analita e' lo
# stesso; per le urine no, quindi si cerca la voce "URINE ..." dedicata.
_PREFISSI = {"s": "", "p": "", "b": "", "sr": "", "u": "urine ", "du": "urine "}


def canonico_di(nome: str, alias: dict[str, str]) -> str | None:
    """Cerca il nome canonico, gestendo i prefissi di matrice (S-, U-, ...)."""
    chiave = slug(nome)
    if chiave in alias:
        return alias[chiave]
    prefisso, _, resto = chiave.partition(" ")
    if resto and prefisso in _PREFISSI:
        return alias.get(_PREFISSI[prefisso] + resto)
    return None


def calcola_flag(valore, rmin, rmax) -> str:
    """N/L/H dai limiti numerici. Stringa vuota se non ci sono riferimenti."""
    if valore is None:
        return ""
    ha_min = isinstance(rmin, (int, float))
    ha_max = isinstance(rmax, (int, float))
    if not ha_min and not ha_max:
        return ""
    if ha_min and valore < rmin:
        return "L"
    if ha_max and valore > rmax:
        return "H"
    return "N"


def normalizza(esame: dict, alias: dict[str, str], sconosciuti: set[str]) -> dict | None:
    nome = (esame.get("nome_referto") or "").strip()
    if not nome:
        return None

    canonico = canonico_di(nome, alias)
    if canonico is None:
        sconosciuti.add(nome)
        canonico = nome.upper()  # provvisorio, da mappare nella scheda Dizionario

    valore, operatore, testo = parse_valore(str(esame.get("valore", "")))
    unita = (esame.get("unita") or "").strip()
    rmin, rmax = esame.get("range_min"), esame.get("range_max")

    conv = CONVERSIONI.get((canonico, unita.lower().replace("µ", "u")))
    if conv and valore is not None:
        fattore, unita = conv

        def scala(x):
            return round(x * fattore, 4) if isinstance(x, (int, float)) else x

        valore, rmin, rmax = scala(valore), scala(rmin), scala(rmax)

    # Il flag lo calcoliamo noi ogni volta che abbiamo valore e limiti: e'
    # deterministico. Quello dichiarato dal modello si usa solo in mancanza di
    # riferimenti numerici, perche' su questo campo sbaglia spesso (tipicamente
    # segnala "alto" un HDL elevato, che invece e' desiderabile).
    flag = calcola_flag(valore, rmin, rmax)
    if not flag:
        dichiarato = (esame.get("flag") or "").upper()
        flag = dichiarato if dichiarato in ("N", "L", "H") else ""

    return {"analita": canonico, "nome_referto": nome, "valore": valore,
            "operatore": operatore, "valore_testo": testo, "unita": unita,
            "range_min": rmin, "range_max": rmax, "flag": flag}


# --- Analisi preventiva della struttura ------------------------------------

PROMPT_STRUTTURA = """Sei un esperto di referti di laboratorio italiani. Ti do il
testo grezzo di un referto di un laboratorio che non abbiamo mai visto. NON
estrarre i valori: studia solo COM'E' FATTO, per guidare un modello piu' piccolo
che estrarra' i dati dai referti di questo stesso laboratorio.

Osserva e descrivi:
- come sono disposti i valori (una colonna? piu' colonne affiancate? il valore
  e' vicino o lontano dal nome dell'esame?);
- dove si trova l'intervallo di riferimento rispetto al valore;
- dove sono l'unita' di misura e le eventuali marcature (alto/basso, asterischi);
- quali righe sono intestazioni, sezioni o totali da NON confondere con i dati;
- qualsiasi insidia di impaginazione (valori su due colonne da leggere
  separatamente, numeri con la virgola decimale, note a pie' di pagina).

Produci una scheda di lettura: istruzioni operative, concrete e specifiche per
QUESTO layout, che dicano al modello di estrazione dove guardare e cosa evitare.
Non descrivere in astratto: scrivi istruzioni azionabili. Rispondi con la sola
scheda, in italiano, senza preamboli."""


def analizza_struttura(model: str, testo: str,
                       immagini: list[str] | None = None) -> str:
    """Scheda di lettura del layout, da iniettare nel prompt di estrazione."""
    messaggio = {"role": "user", "content": f"Referto:\n\n{testo[:6000]}"}
    if immagini:
        messaggio["images"] = immagini
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": PROMPT_STRUTTURA}, messaggio],
        "stream": False, "think": FUNZIONI["analisi_struttura"]["think"],
        "options": {"temperature": FUNZIONI["analisi_struttura"]["temperature"],
                    "num_ctx": FUNZIONI["analisi_struttura"]["num_ctx"]},
    }
    with core.post_ollama(payload) as resp:
        return json.loads(resp.read().decode())["message"]["content"].strip()



# --- Diagnosi delle estrazioni difficili -----------------------------------

SCHEMA_DIAGNOSI = {
    "type": "object",
    "properties": {
        "problema": {"type": "string"},
        "istruzione_layout": {"type": "string"},
        "gravita": {"type": "string", "enum": ["lieve", "media", "grave"]},
    },
    "required": ["problema", "istruzione_layout"],
}

PROMPT_DIAGNOSI = """Sei un esperto di estrazione dati da referti di laboratorio
italiani. Un modello piu' piccolo ha estratto male i valori da questo referto.
Ti do il testo grezzo del referto e cio' che il modello ha prodotto.

Confronta le due cose e capisci COSA e' andato storto nella lettura. Cause
tipiche: valori su piu' colonne affiancate letti in fila; virgola decimale
scambiata per separatore di migliaia; intervallo di riferimento su una riga
diversa dal valore e attribuito all'esame sbagliato; unita' di misura staccata
dal numero; intestazioni ripetute lette come dati; valori multipli per lo
stesso esame (es. prima e dopo).

Produci:
- problema: una spiegazione in una o due frasi, leggibile, di cosa e' andato
  storto. Se l'estrazione ti sembra invece corretta, dillo chiaramente qui.
- istruzione_layout: un'istruzione operativa e specifica, da aggiungere al
  prompt di estrazione, che aiuti a leggere correttamente QUESTO tipo di
  impaginazione. Concreta ("i valori sono in due colonne: estrai prima tutti
  quelli della colonna sinistra, poi quelli della destra"), non generica
  ("presta attenzione"). Stringa vuota se l'estrazione era gia' corretta.
- gravita: quanto e' compromessa l'estrazione.

Rispondi SOLO con il JSON conforme allo schema."""


def diagnostica(model: str, testo_grezzo: str, esami_estratti: list[dict]) -> dict:
    """Analizza un'estrazione fallita e propone un'istruzione per il layout."""
    riepilogo = json.dumps(esami_estratti, ensure_ascii=False, indent=1)[:4000]
    contenuto = (f"TESTO GREZZO DEL REFERTO:\n{testo_grezzo[:6000]}\n\n"
                 f"ESTRAZIONE PRODOTTA DAL MODELLO PICCOLO:\n{riepilogo}")
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": PROMPT_DIAGNOSI},
                     {"role": "user", "content": contenuto}],
        "format": SCHEMA_DIAGNOSI, "stream": False,
        "think": FUNZIONI["diagnosi_estrazione"]["think"],
        "options": {"temperature": FUNZIONI["diagnosi_estrazione"]["temperature"],
                    "num_ctx": FUNZIONI["diagnosi_estrazione"]["num_ctx"]},
    }
    with core.post_ollama(payload) as resp:
        testo = json.loads(resp.read().decode())["message"]["content"]
    return json.loads(re.sub(r"^```(?:json)?|```$", "", testo.strip(),
                             flags=re.MULTILINE).strip())


def riestrai(model: str, funzione: str, testo: str,
             istruzione_layout: str = "") -> list[dict]:
    """Riesegue l'estrazione dei valori, con l'eventuale istruzione di layout."""
    dati, _ = _chiama(model, funzione, "Referto:\n\n" + testo,
                      etichetta="riestrazione",
                      istruzione_layout=istruzione_layout)
    return dati.get("esami", [])


def riestrai_se_migliora(path, doc: dict, scheda: str, modelli: dict,
                         progress=None) -> dict:
    """Ri-estrae i valori con la scheda di layout e li tiene solo se migliorano.

    A differenza di rifare elabora_documento, NON riclassifica il documento:
    riusa tipo, data e struttura gia' noti, e ri-lancia solo l'estrazione dei
    valori. Cosi' la scheda costa una chiamata sola, non due. Se il nuovo esito
    non e' migliore del precedente, si tiene quello originale.
    """
    testo = doc.get("testo", "")
    if not testo.strip():
        return doc  # senza testo grezzo non si puo' ri-estrarre
    nuovi = core.con_battito(
        lambda: riestrai(modelli["estrazione_testo"], "estrazione_testo",
                         testo, scheda),
        progress=progress, etichetta=f"{modelli['estrazione_testo']} · con scheda")
    if _estrazione_migliore(nuovi, doc.get("esami", [])):
        if progress:
            progress(f"Migliorata con la scheda: {len(nuovi)} valori "
                     f"(erano {len(doc.get('esami', []))}).")
        doc = {**doc, "esami": nuovi}
    elif progress:
        progress("La scheda non migliora l'estrazione: tengo quella iniziale.")
    return doc


def recupera_estrazione(conn, sha: str, testo: str, esami_attuali: list[dict],
                        laboratorio: str, modelli: dict,
                        progress=None) -> dict:
    """Pipeline per un referto estratto male: diagnosi, ritentativi, presa in carico.

    1. il modello grosso diagnostica cosa e' andato storto e propone
       un'istruzione per il layout;
    2. il modello normale ritenta con quell'istruzione, fino a
       RITENTATIVI_ESTRAZIONE volte;
    3. se ancora non basta, il modello grosso estrae lui.

    Tutto in locale: nulla lascia la macchina. Restituisce esami, quale fase ha
    prodotto il risultato, la diagnosi e l'istruzione (da salvare a parte).
    """
    def nota(m):
        if progress:
            progress(m)

    # 1. diagnosi
    nota(f"Diagnosi con {modelli['diagnosi_estrazione']}…")
    diag = diagnostica(modelli["diagnosi_estrazione"], testo, esami_attuali)
    istruzione = (diag.get("istruzione_layout") or "").strip()
    nota(f"Problema rilevato: {diag.get('problema', 'n/d')}")

    esiti = {"diagnosi": diag, "istruzione": istruzione,
             "esami": esami_attuali, "fase": "nessun cambiamento",
             "laboratorio": laboratorio}

    if not istruzione:
        nota("La diagnosi non ha prodotto un'istruzione: l'estrazione "
             "sembra gia' corretta, oppure il problema non e' di layout.")
        return esiti

    # 2. ritentativi con il modello normale
    for tentativo in range(1, RITENTATIVI_ESTRAZIONE + 1):
        nota(f"Nuovo tentativo {tentativo}/{RITENTATIVI_ESTRAZIONE} "
             f"con {modelli['estrazione_testo']} e l'istruzione trovata…")
        nuovi = riestrai(modelli["estrazione_testo"], "estrazione_testo",
                         testo, istruzione)
        if _estrazione_migliore(nuovi, esiti["esami"]):
            nota(f"Migliorata: {len(nuovi)} valori estratti.")
            esiti.update(esami=nuovi, fase=f"ritentativo {tentativo}")
            return esiti

    # 3. presa in carico dal modello grosso
    nota(f"Presa in carico da {modelli['estrazione_accurata']}…")
    grossi = riestrai(modelli["estrazione_accurata"], "estrazione_accurata",
                      testo, istruzione)
    if _estrazione_migliore(grossi, esiti["esami"]):
        nota(f"Il modello grosso ha estratto {len(grossi)} valori.")
        esiti.update(esami=grossi, fase="modello grosso")
    else:
        nota("Nemmeno il modello grosso ha fatto meglio: l'estrazione "
             "originale resta invariata.")
    return esiti


def _estrazione_migliore(nuova: list[dict], vecchia: list[dict]) -> bool:
    """Euristica prudente: la nuova estrazione e' preferibile?

    Conta i valori numerici plausibili: piu' valori validi, meno righe vuote o
    palesemente rotte. Non decide da sola cosa e' giusto — quella scelta resta
    all'utente, che vede entrambe — ma evita di proporre un cambiamento che
    peggiora.
    """
    def validi(righe):
        n = 0
        for e in righe:
            v = parse_valore(str(e.get("valore", "")))[0]
            if v is not None and abs(v) < 1e6:
                n += 1
        return n
    return validi(nuova) > validi(vecchia)
