"""AHIA — dati di riferimento sugli analiti: intervalli e collegamenti esterni.

Intervalli di riferimento, usati solo come ripiego.

Regole non negoziabili:
  1. L'intervallo stampato sul referto ha SEMPRE la precedenza. Il catalogo
     interviene solo dove il laboratorio non ne ha indicato uno.
  2. Si applica solo se l'unita' di misura coincide. Senza questo controllo la
     PCR in mg/L verrebbe confrontata con una soglia in mg/dL, sbagliando di
     un fattore dieci.
  3. L'origine dell'intervallo viene registrata e mostrata: chi legge deve
     sapere se una soglia viene dal suo laboratorio o da qui.

I valori sono intervalli indicativi per adulti, dove esistono distinti per
sesso. Non sono validi per bambini, gravidanza, o metodi analitici particolari,
e alcune voci non sono intervalli di riferimento ma soglie decisionali
(colesterolo, vitamina D): la nota lo segnala.

Il file riferimenti_personali.json nella cartella dati estende o sovrascrive
questo catalogo, con la stessa struttura.
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

import functools
import json
import re
from urllib.parse import quote_plus

from pathlib import Path

from config import DATA_DIR

RIFERIMENTI_UTENTE = DATA_DIR / "riferimenti_personali.json"  # solo come default

# analita: {unita, M: [min, max], F: [min, max], nota}
# None come estremo significa "aperto da quel lato".
CATALOGO: dict[str, dict] = {
    # Metabolismo glucidico
    "GLUCOSIO": {"unita": "mg/dL", "M": [70, 99], "F": [70, 99],
                 "nota": "a digiuno; 100-125 indica alterata glicemia a digiuno"},
    "HBA1C": {"unita": "%", "M": [4.0, 5.6], "F": [4.0, 5.6],
              "nota": "scala DCCT; in mmol/mol (IFCC) i valori sono diversi"},
    # Lipidi — soglie decisionali, non intervalli di riferimento
    "COLESTEROLO TOTALE": {"unita": "mg/dL", "M": [None, 200], "F": [None, 200],
                           "nota": "soglia desiderabile, non un intervallo di "
                                   "riferimento"},
    "COLESTEROLO HDL": {"unita": "mg/dL", "M": [40, None], "F": [50, None],
                        "nota": "valori piu' alti sono favorevoli"},
    "COLESTEROLO LDL": {"unita": "mg/dL", "M": [None, 100], "F": [None, 100],
                        "nota": "obiettivo che dipende dal rischio cardiovascolare "
                                "individuale: puo' essere molto piu' basso"},
    "TRIGLICERIDI": {"unita": "mg/dL", "M": [None, 150], "F": [None, 150],
                     "nota": "a digiuno"},
    # Rene
    "CREATININA": {"unita": "mg/dL", "M": [0.7, 1.2], "F": [0.5, 1.0],
                   "nota": "dipende dalla massa muscolare"},
    "UREA": {"unita": "mg/dL", "M": [15, 45], "F": [15, 45], "nota": ""},
    "ACIDO URICO": {"unita": "mg/dL", "M": [3.4, 7.0], "F": [2.4, 6.0], "nota": ""},
    # Fegato
    "AST": {"unita": "U/L", "M": [10, 40], "F": [10, 35], "nota": ""},
    "ALT": {"unita": "U/L", "M": [10, 50], "F": [10, 35], "nota": ""},
    "GGT": {"unita": "U/L", "M": [10, 71], "F": [6, 42], "nota": ""},
    "ALP": {"unita": "U/L", "M": [40, 130], "F": [40, 130],
            "nota": "piu' alta in crescita e in gravidanza"},
    "BILIRUBINA TOTALE": {"unita": "mg/dL", "M": [0.2, 1.2], "F": [0.2, 1.2],
                          "nota": ""},
    "BILIRUBINA DIRETTA": {"unita": "mg/dL", "M": [0, 0.3], "F": [0, 0.3], "nota": ""},
    "PROTEINE TOTALI": {"unita": "g/dL", "M": [6.0, 8.0], "F": [6.0, 8.0], "nota": ""},
    "ALBUMINA": {"unita": "g/dL", "M": [3.5, 5.0], "F": [3.5, 5.0], "nota": ""},
    # Emocromo
    "EMOGLOBINA": {"unita": "g/dL", "M": [13.5, 17.5], "F": [12.0, 15.5], "nota": ""},
    "EMATOCRITO": {"unita": "%", "M": [40, 52], "F": [36, 48], "nota": ""},
    "LEUCOCITI": {"unita": "10^3/uL", "M": [4.0, 10.0], "F": [4.0, 10.0], "nota": ""},
    "PIASTRINE": {"unita": "10^3/uL", "M": [150, 400], "F": [150, 400], "nota": ""},
    # Ferro
    "FERRITINA": {"unita": "ng/mL", "M": [30, 400], "F": [15, 150], "nota": ""},
    "FERRO": {"unita": "ug/dL", "M": [65, 175], "F": [50, 170],
              "nota": "variabile nell'arco della giornata"},
    "TRANSFERRINA": {"unita": "mg/dL", "M": [200, 360], "F": [200, 360], "nota": ""},
    # Tiroide
    "TSH": {"unita": "uU/mL", "M": [0.4, 4.0], "F": [0.4, 4.0],
            "nota": "intervallo variabile tra laboratori e in gravidanza"},
    "FT3": {"unita": "pg/mL", "M": [2.3, 4.2], "F": [2.3, 4.2], "nota": ""},
    "FT4": {"unita": "ng/dL", "M": [0.8, 1.8], "F": [0.8, 1.8], "nota": ""},
    # Vitamine
    "VITAMINA D": {"unita": "ng/mL", "M": [30, 100], "F": [30, 100],
                   "nota": "soglia di sufficienza, oggetto di dibattito"},
    "VITAMINA B12": {"unita": "pg/mL", "M": [200, 900], "F": [200, 900], "nota": ""},
    "FOLATI": {"unita": "ng/mL", "M": [3, 17], "F": [3, 17], "nota": ""},
    # Elettroliti e minerali
    "SODIO": {"unita": "mmol/L", "M": [136, 145], "F": [136, 145], "nota": ""},
    "POTASSIO": {"unita": "mmol/L", "M": [3.5, 5.1], "F": [3.5, 5.1], "nota": ""},
    "CLORO": {"unita": "mmol/L", "M": [98, 107], "F": [98, 107], "nota": ""},
    "CALCIO": {"unita": "mg/dL", "M": [8.6, 10.2], "F": [8.6, 10.2], "nota": ""},
    "FOSFORO": {"unita": "mg/dL", "M": [2.5, 4.5], "F": [2.5, 4.5], "nota": ""},
    "MAGNESIO": {"unita": "mg/dL", "M": [1.7, 2.2], "F": [1.7, 2.2], "nota": ""},
    # Infiammazione
    "PCR": {"unita": "mg/L", "M": [None, 5], "F": [None, 5],
            "nota": "spesso refertata in mg/dL, dove la soglia e' 0.5"},
    "VES": {"unita": "mm/h", "M": [None, 15], "F": [None, 20],
            "nota": "aumenta fisiologicamente con l'eta'"},
}

# Grafie equivalenti della stessa unita'
_EQUIVALENTI = {
    "ui/l": "u/l", "iu/l": "u/l", "u/i": "u/l",
    "µu/ml": "uu/ml", "uui/ml": "uu/ml", "miu/l": "uu/ml", "µui/ml": "uu/ml",
    "µg/dl": "ug/dl", "mcg/dl": "ug/dl",
    "10e3/ul": "10^3/ul", "10^3/µl": "10^3/ul", "x10^3/ul": "10^3/ul",
    "10^9/l": "10^3/ul", "migliaia/ul": "10^3/ul", "k/ul": "10^3/ul",
    "µl": "ul", "mmol/l": "mmol/l",
}


def _norm_unita(unita: str) -> str:
    u = re.sub(r"\s+", "", (unita or "").lower()).replace("µ", "u")
    return _EQUIVALENTI.get(u, u)


@functools.lru_cache(maxsize=16)
def _catalogo(firma: tuple) -> dict[str, dict]:
    completo = {k: dict(v) for k, v in CATALOGO.items()}
    if firma[0]:
        try:
            personali = json.loads(Path(firma[0]).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return completo
        for analita, voce in personali.items():
            completo[analita.upper()] = voce
    return completo


def catalogo_completo(percorso=None) -> dict[str, dict]:
    """Catalogo di base piu' le voci personali dell'utente indicato.

    Il percorso arriva come parametro invece di stare in una variabile di
    modulo: Streamlit serve piu' sessioni nello stesso processo, e uno stato
    globale mutabile farebbe leggere a un utente il file di un altro.
    """
    percorso = percorso or RIFERIMENTI_UTENTE
    try:
        firma = (str(percorso), percorso.stat().st_mtime_ns)
    except OSError:
        firma = ("", 0)
    return _catalogo(firma)


def intervallo(analita: str, unita: str, sesso: str = "",
               percorso=None) -> tuple | None:
    """(min, max, nota) dal catalogo, oppure None se non applicabile.

    Restituisce None se l'analita non e' in catalogo o se l'unita' di misura
    del referto non coincide con quella del catalogo: meglio nessun intervallo
    che uno riferito a un'altra scala.
    """
    voce = catalogo_completo(percorso).get((analita or "").upper())
    if not voce:
        return None
    if _norm_unita(unita) != _norm_unita(voce.get("unita", "")):
        return None
    limiti = voce.get(sesso.upper() if sesso.upper() in ("M", "F") else "M")
    if not limiti:
        return None
    return limiti[0], limiti[1], voce.get("nota", "")


def elenco(percorso=None) -> list[dict]:
    """Catalogo in forma tabellare, per mostrarlo e modificarlo."""
    righe = []
    for analita, v in sorted(catalogo_completo(percorso).items()):
        def testo(sesso, v=v):
            lo, hi = v.get(sesso, [None, None])
            if lo is None and hi is None:
                return "-"
            if lo is None:
                return f"< {hi:g}"
            if hi is None:
                return f"> {lo:g}"
            return f"{lo:g} – {hi:g}"
        righe.append({"Analita": analita, "Unita'": v.get("unita", ""),
                      "Uomini": testo("M"), "Donne": testo("F"),
                      "Nota": v.get("nota", "")})
    return righe


# --- Collegamenti alle schede di Lab Tests Online ---------------------------
# labtestsonline.it e' il portale divulgativo di SIBioC (Societa' Italiana di
# Biochimica Clinica). Qui teniamo SOLO gli indirizzi: i contenuti sono coperti
# da licenza e non vanno copiati. Il collegamento porta l'utente sulla pagina,
# che resta aggiornata alla fonte.

LTO_BASE = "https://labtestsonline.it/lto-tests/"
LTO_INDICE = "https://labtestsonline.it/tests"
# Il sito non espone una ricerca interna utilizzabile: per gli esami non
# mappati si usa una ricerca esterna ristretta al dominio, che porta alla
# scheda in un clic invece che all'indice per lettera. Viene inviato solo il
# nome dell'esame, nessun valore.
LTO_RICERCA = "https://duckduckgo.com/?q=site%3Alabtestsonline.it+"

LTO_PAGINE: dict[str, str] = {
    "GLUCOSIO": "glucosio",
    "HBA1C": "emoglobina-glicata-hba1c",
    "COLESTEROLO TOTALE": "colesterolo-totale",
    "COLESTEROLO HDL": "colesterolo-hdl",
    "COLESTEROLO LDL": "colesterolo-ldl",
    "TRIGLICERIDI": "trigliceridi",
    "CREATININA": "creatinina",
    "UREA": "urea",
    "ACIDO URICO": "acido-urico",
    "AST": "aspartato-aminotransferasi-ast-got",
    "ALT": "alanina-aminotransferasi-alt-gpt",
    "GGT": "gamma-gt-ggt",
    "ALP": "fosfatasi-alcalina-alp",
    "BILIRUBINA TOTALE": "bilirubina-totale",
    "BILIRUBINA DIRETTA": "bilirubina-diretta",
    "PROTEINE TOTALI": "proteine-totali",
    "ALBUMINA": "albumina-sierica",
    "GAMMA GLOBULINE": "protidogramma",
    "ALFA1 GLOBULINE": "protidogramma",
    "ALFA2 GLOBULINE": "protidogramma",
    "BETA GLOBULINE": "protidogramma",
    "EMOGLOBINA": "emoglobina-2",
    "EMATOCRITO": "ematocrito",
    "LEUCOCITI": "conta-dei-leucociti",
    "ERITROCITI": "conta-eritrocitaria",
    "PIASTRINE": "piastrine-2",
    "EMOCROMO": "emocromo",
    "FORMULA LEUCOCITARIA": "emocromo",
    "NEUTROFILI": "emocromo",
    "LINFOCITI": "emocromo",
    "MONOCITI": "emocromo",
    "EOSINOFILI": "emocromo",
    "BASOFILI": "emocromo",
    "MCV": "emocromo",
    "VOLUME CORPUSCOLARE MEDIO": "emocromo",
    "MCH": "emocromo",
    "CONTENUTO EMOGLOBINICO CORPUSCOLARE MEDIO": "emocromo",
    "MCHC": "emocromo",
    "CONCENTRAZIONE EMOGLOBINICA CORPUSCOLARE MEDIA": "emocromo",
    "RDW": "emocromo",
    "AMPIEZZA DI DISTRIBUZIONE ERITROCITARIA": "emocromo",
    "FERRITINA": "ferritina",
    "FERRO": "ferro-sideremia",
    "TRANSFERRINA": "tibc-uibc-e-transferrina-2",
    "TSH": "tsh",
    "FT3": "ft3",
    "FT4": "ft4",
    "VITAMINA D": "25-oh-vitamina-d-e-1-25-oh-vitamina-d",
    "VITAMINA B12": "vitamina-b12-e-folati",
    "VES": "velocita-di-eritrosedimentazione-ves",
    "FOLATI": "folati",
    "PCR": "proteina-c-reattiva-pcr",
    "SODIO": "sodio-na",
    "POTASSIO": "potassio",
    "CLORO": "cloro",
    "CALCIO": "calcio",
    "CALCIO IONIZZATO": "calcio-ione",
    "FOSFORO": "fosforo",
    "MAGNESIO": "magnesio-mg",
    "URINE PESO SPECIFICO": "esame-chimico-fisico-e-microscopico-delle-urine",
    "URINE PH": "esame-chimico-fisico-e-microscopico-delle-urine",
    "URINE PROTEINE": "proteine-urinarie",
    "URINE GLUCOSIO": "glucosio-nellurina",
    "URINE CHETONI": "esame-chimico-fisico-e-microscopico-delle-urine",
    "URINE NITRITI": "esame-chimico-fisico-e-microscopico-delle-urine",
    "URINE SANGUE": "esame-chimico-fisico-e-microscopico-delle-urine",
    "URINE LEUCOCITI": "esame-chimico-fisico-e-microscopico-delle-urine",
}


def scheda(analita: str, alias: dict[str, str] | None = None) -> str:
    """Indirizzo della scheda esterna che descrive l'esame.

    Il nome che arriva puo' essere la dicitura grezza del laboratorio
    ("S-COLESTEROLO TOTALE", "Glicemia", "Azotemia"): prima si prova la
    corrispondenza diretta, poi si passa dal dizionario degli alias, che conosce
    sia i sinonimi sia i prefissi di matrice. Solo se anche quello fallisce si
    ripiega sull'indice alfabetico.
    """
    nome = (analita or "").upper().strip()
    if pagina := LTO_PAGINE.get(nome):
        return f"{LTO_BASE}{pagina}.html"

    if alias:
        import ingest  # importato qui per non creare un ciclo tra i moduli

        canonico = ingest.canonico_di(nome, alias)
        if canonico and (pagina := LTO_PAGINE.get(canonico)):
            return f"{LTO_BASE}{pagina}.html"
        nome = canonico or nome

    if not nome:
        return LTO_INDICE
    # ripulisco il termine: via punteggiatura e prefissi di matrice, che
    # sporcherebbero la ricerca senza aggiungere significato
    termine = re.sub(r"[^\w\s]", " ", nome.lower())
    termine = re.sub(r"^\s*[spbu]\s+", "", termine)
    termine = re.sub(r"\s+", " ", termine).strip()
    return LTO_RICERCA + quote_plus(termine or nome.lower())
