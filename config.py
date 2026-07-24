"""AHIA — configurazione: percorsi, funzioni LLM, conversioni, dizionario."""

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

import os
from pathlib import Path

VERSIONE = "1.5.2"

# AGPL-3.0, articolo 13: chi interagisce con il programma attraverso una rete
# deve poter ottenere il sorgente. Se pubblichi una tua versione modificata,
# aggiorna questo indirizzo.
REPO_URL = "https://github.com/<utente>/ahia"

# --- Percorsi: tutto resta in locale ---------------------------------------

DATA_DIR = Path(os.environ.get("AHIA_DATA_DIR")
                or os.environ.get("SALUTE_DATA_DIR")  # nome precedente
                or Path.home() / ".ahia")

# Migrazione dalla cartella della versione precedente, una tantum
_PRECEDENTE = Path.home() / ".salute-locale"
if not DATA_DIR.exists() and _PRECEDENTE.exists():
    try:
        _PRECEDENTE.rename(DATA_DIR)
    except OSError:
        DATA_DIR = _PRECEDENTE  # spostamento impossibile: si continua sulla vecchia

DATA_DIR.mkdir(parents=True, exist_ok=True)

# Le utenze stanno in un database a parte; i dati sanitari di ogni utente in una
# cartella propria. L'isolamento e' fisico: nessuna query puo' attraversare il
# confine tra due archivi, perche' sono file diversi.
AUTH_DB = DATA_DIR / "utenti.db"
ARCHIVI_DIR = DATA_DIR / "archivi"
ARCHIVI_DIR.mkdir(exist_ok=True)

# Percorsi della versione a utente singolo, migrati al primo amministratore.
LEGACY_DB = DATA_DIR / "salute.db"
LEGACY_PDF = DATA_DIR / "referti"
LEGACY_ALIAS = DATA_DIR / "alias_analiti.json"
LEGACY_RIFERIMENTI = DATA_DIR / "riferimenti_personali.json"


class Archivio:
    """Percorsi dei dati di un singolo utente."""

    def __init__(self, utente_id: int):
        self.dir = ARCHIVI_DIR / str(utente_id)
        self.pdf = self.dir / "referti"
        self.pdf.mkdir(parents=True, exist_ok=True)
        self.db = self.dir / "salute.db"
        self.alias = self.dir / "alias_analiti.json"
        self.riferimenti = self.dir / "riferimenti_personali.json"

    def __repr__(self):
        return f"Archivio({self.dir})"


# Compatibilita' con l'uso a utente singolo (script, test, migrazioni)
DB_PATH = LEGACY_DB
PDF_DIR = LEGACY_PDF
ALIAS_PATH = LEGACY_ALIAS

# --- Ollama ----------------------------------------------------------------

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
if not OLLAMA_HOST.startswith(("http://", "https://")):
    # senza questo controllo un OLLAMA_HOST malevolo potrebbe far leggere
    # file locali con lo schema file:
    raise ValueError(f"OLLAMA_HOST deve iniziare con http:// o https:// "
                     f"(ricevuto: {OLLAMA_HOST!r})")
OLLAMA_CHAT_URL = f"{OLLAMA_HOST}/api/chat"
OLLAMA_TAGS_URL = f"{OLLAMA_HOST}/api/tags"
OLLAMA_PULL_URL = f"{OLLAMA_HOST}/api/pull"
OLLAMA_EMBED_URL = f"{OLLAMA_HOST}/api/embed"
OLLAMA_EMBED_URL_LEGACY = f"{OLLAMA_HOST}/api/embeddings"
TIMEOUT_LLM = 900
TIMEOUT_PULL = 7200  # un modello da 20 GB su linea lenta

# --- Ricerca semantica sui referti narrativi --------------------------------
# bge-m3 e' multilingue e regge bene l'italiano medico; circa 1,2 GB.
# Alternative: granite-embedding:278m (piu' leggero),
# mxbai-embed-large (ottimo ma solo inglese, sconsigliato qui).

MODELLO_EMBEDDING = "bge-m3"
DIM_FRAMMENTO = 800        # caratteri per frammento
SOVRAPPOSIZIONE = 150      # coda ripetuta tra frammenti contigui
BRANI_NEL_CONTESTO = 5

# Log del server Ollama: percorsi noti sui tre sistemi, il primo esistente
# viene usato. Su Linux con systemd il log sta nel journal e il file non esiste.
LOG_OLLAMA = [
    Path.home() / ".ollama" / "logs" / "server.log",          # macOS, Linux
    Path(os.environ.get("LOCALAPPDATA", "")) / "Ollama" / "server.log",  # Windows
    Path(os.environ.get("LOCALAPPDATA", "")) / "Ollama" / "app.log",     # Windows
    Path("/var/log/ollama.log"),
]

# --- Estrazione ------------------------------------------------------------

MIN_CHARS_PAGINA = 120  # sotto questa resa media il PDF e' considerato scansione
DPI_RASTER = 300

# --- Funzioni che usano un LLM ---------------------------------------------
# Ognuna ha modello e parametri propri: le estrazioni trascrivono e vanno
# tenute deterministiche, analisi e chat devono ragionare.
# "think" attiva il ragionamento esplicito sui modelli che lo supportano
# (qwen3, deepseek-r1...): migliora l'analisi, rallenta tutto il resto.
# Sui modelli che non lo supportano il parametro viene ignorato.
# La scelta dell'utente e' salvata nel database e ha la precedenza sul default.

FUNZIONI: dict[str, dict] = {
    "estrazione_testo": {
        "label": "Estrazione — PDF nativi",
        "aiuto": "Trascrive una tabella: serve precisione, non ragionamento.",
        "default": "qwen3:14b", "temperature": 0.0, "num_ctx": 16384, "think": False,
    },
    "estrazione_vision": {
        "label": "Estrazione — scansioni",
        "aiuto": "Legge l'immagine della pagina: serve un modello multimodale "
                 "(qwen2.5vl, llama3.2-vision, gemma3).",
        "default": "qwen2.5vl:7b", "temperature": 0.0, "num_ctx": 16384, "think": False,
    },
    "analisi": {
        "label": "Analisi referti",
        "aiuto": "Gira una volta sola: qui conviene il modello piu' capace che "
                 "la macchina regge, anche se lento.",
        "default": "qwen3:14b", "temperature": 0.2, "num_ctx": 16384, "think": True,
    },
    "classificazione": {
        "label": "Classificazione documenti",
        "aiuto": "Riconosce di che tipo di documento si tratta leggendo la prima "
                 "pagina. Compito semplice: basta un modello piccolo.",
        "default": "qwen3:14b", "temperature": 0.0, "num_ctx": 8192, "think": False,
    },
    "dizionario": {
        "label": "Proposte dizionario",
        "aiuto": "Suggerisce a quale nome canonico ricondurre le diciture nuove. "
                 "Le proposte vanno sempre confermate a mano.",
        "default": "qwen3:14b", "temperature": 0.0, "num_ctx": 8192, "think": False,
    },
    "chat": {
        "label": "Chat",
        "aiuto": "Botta e risposta: qui la latenza si sente.",
        "default": "qwen3:14b", "temperature": 0.3, "num_ctx": 16384, "think": False,
    },
}

# --- Avvertenza mostrata al primo avvio -------------------------------------
# Alzando la versione l'avvertenza viene ripresentata a chi l'aveva accettata.

DISCLAIMER_VERSIONE = "2"

DISCLAIMER = {"it": """
### AHIA è uno strumento sperimentale

Nasce come banco di prova per verificare che cosa un modello linguistico
eseguito in locale sia in grado di fare su documenti sanitari: leggerli,
strutturarli, metterli in serie storica. Questo è il suo scopo, e l'unico.

**Non è un dispositivo medico.** Non è certificato né validato clinicamente, e
non fornisce diagnosi, prognosi o indicazioni terapeutiche. Nessuna delle sue
risposte va intesa come parere sanitario.

**I risultati possono essere sbagliati.** L'estrazione automatica può leggere
male un valore, spostare una virgola decimale o attribuire a una riga
l'intervallo di riferimento di un'altra. Il modello che commenta i dati non
conosce la storia clinica, il motivo per cui gli esami sono stati prescritti,
le terapie in corso né l'esame obiettivo: può produrre affermazioni del tutto
plausibili e comunque errate. Confronta sempre i valori estratti con il referto
originale.

**Non sostituisce il medico e non deve ritardarne il consulto.**
L'interpretazione degli esami spetta a un professionista sanitario, che è
l'unico a poterli leggere alla luce di tutto il quadro. Se un valore ti
preoccupa, se hai sintomi o se stai valutando decisioni che riguardano la tua
salute, parlane con il tuo medico. In caso di urgenza, chiama il 112.

**Responsabilità.** Il software è fornito così com'è, senza garanzie di alcun
tipo, espresse o implicite. Chi lo ha realizzato declina ogni responsabilità
per l'uso che ne viene fatto e per qualsiasi conseguenza derivante dalle
informazioni prodotte. L'utilizzo avviene a rischio esclusivo di chi lo usa.

**I tuoi dati.** Restano su questa macchina, in una cartella non cifrata, e non
vengono inviati ad alcun servizio esterno. La riservatezza dell'archivio
dipende da come proteggi il computer su cui gira.

**Secondo parere.** L'app può preparare un testo anonimizzato da sottoporre a
un modello esterno. Quel testo non parte da solo: viene mostrato per intero e
sei tu a copiarlo altrove. Da quel momento vale l'informativa del servizio che
scegli, non questa. Rileggilo prima di inviarlo: ciò che esce da qui non torna
indietro.
""", "en": """
### AHIA is an experimental tool

It was built to test what a locally run language model can do with medical
documents: read them, structure them, and track them over time. That is its
purpose, and its only one.

**It is not a medical device.** It is neither certified nor clinically
validated, and it provides no diagnosis, prognosis, or treatment advice. None
of its output should be taken as medical opinion.

**Its results can be wrong.** Automated extraction may misread a value, shift a
decimal point, or assign one row's reference range to another. The model
commenting on the data knows nothing of your clinical history, why the tests
were ordered, what treatments you are on, or the findings of a physical
examination: it can produce statements that sound entirely plausible and are
still incorrect. Always check extracted values against the original report.

**It does not replace a doctor, and must not delay seeing one.** Interpreting
test results is the job of a healthcare professional, who alone can read them
in the light of the whole picture. If a value worries you, if you have
symptoms, or if you are weighing decisions about your health, talk to your
doctor. In an emergency, call your local emergency number.

**Liability.** The software is provided as is, without warranty of any kind,
express or implied. Its author disclaims all liability for how it is used and
for any consequence arising from the information it produces. You use it
entirely at your own risk.

**Your data.** It stays on this machine, in an unencrypted folder, and is sent
to no external service. How well the archive is protected depends on how well
you protect the computer it runs on.

**Second opinion.** The app can prepare an anonymised text to submit to an
external model. That text is never sent automatically: it is shown to you in
full and you are the one who copies it elsewhere. From that point the privacy
policy of the service you choose applies, not this one. Read it before sending:
what leaves here does not come back.
"""}

# --- Tipologie di documento -------------------------------------------------
# "tabellare" distingue i referti con valori numerici, da cui si estraggono gli
# analiti, dai documenti narrativi (ecografie, visite), di cui si conserva una
# sintesi. La chiave e' quella salvata nel database: non va cambiata a cuor
# leggero, le etichette invece si.

TIPI: dict[str, dict] = {
    "analisi_sangue": {"label": "Analisi del sangue",
                       "icona": ":material/bloodtype:", "tabellare": True},
    "analisi_urine": {"label": "Analisi delle urine",
                      "icona": ":material/water_drop:", "tabellare": True},
    "altro_laboratorio": {"label": "Altri esami di laboratorio",
                          "icona": ":material/labs:", "tabellare": True},
    "ecografia": {"label": "Ecografia", "icona": ":material/waves:",
                  "tabellare": False},
    "radiografia": {"label": "Radiografia", "icona": ":material/radiology:",
                    "tabellare": False},
    "tac_rm": {"label": "TAC / Risonanza magnetica",
               "icona": ":material/imagesearch_roller:", "tabellare": False},
    "cardiologia": {"label": "Elettrocardiogramma / cardiologia",
                    "icona": ":material/ecg_heart:", "tabellare": False},
    "visita": {"label": "Visita specialistica",
               "icona": ":material/stethoscope:", "tabellare": False},
    "ricovero": {"label": "Ricovero, intervento, pronto soccorso",
                 "icona": ":material/local_hospital:", "tabellare": False},
    "altro": {"label": "Altro documento", "icona": ":material/description:",
              "tabellare": False},
}

TIPO_PREDEFINITO = "altro"


def e_tabellare(tipo: str) -> bool:
    return TIPI.get(tipo, TIPI[TIPO_PREDEFINITO])["tabellare"]


def etichetta(tipo: str) -> str:
    return TIPI.get(tipo, TIPI[TIPO_PREDEFINITO])["label"]


# --- Conversioni verso l'unita' canonica -----------------------------------
# (analita, unita_sorgente_minuscola) -> (fattore, unita_target)

CONVERSIONI: dict[tuple[str, str], tuple[float, str]] = {
    ("GLUCOSIO", "mmol/l"): (18.0182, "mg/dL"),
    ("CREATININA", "umol/l"): (0.0113, "mg/dL"),
    ("COLESTEROLO TOTALE", "mmol/l"): (38.67, "mg/dL"),
    ("COLESTEROLO HDL", "mmol/l"): (38.67, "mg/dL"),
    ("COLESTEROLO LDL", "mmol/l"): (38.67, "mg/dL"),
    ("TRIGLICERIDI", "mmol/l"): (88.57, "mg/dL"),
    ("BILIRUBINA TOTALE", "umol/l"): (0.0585, "mg/dL"),
    ("EMOGLOBINA", "mmol/l"): (1.611, "g/dL"),
    ("FERRITINA", "pmol/l"): (0.4457, "ng/mL"),
    ("VITAMINA D", "nmol/l"): (0.4006, "ng/mL"),
    ("UREA", "mmol/l"): (6.006, "mg/dL"),
    ("ACIDO URICO", "umol/l"): (0.0168, "mg/dL"),
}

# --- Dizionario di base: canonico -> diciture note --------------------------
# alias_analiti.json nella cartella dati lo estende e ha la precedenza.

_DIZIONARIO: dict[str, list[str]] = {
    "CREATININA": ["creatinina", "creatininemia", "creatinina sierica"],
    "GLUCOSIO": ["glucosio", "glicemia", "glucosio sierico"],
    "UREA": ["urea", "azotemia"],
    "ACIDO URICO": ["acido urico", "uricemia"],
    "COLESTEROLO TOTALE": ["colesterolo totale", "colesterolo"],
    "COLESTEROLO HDL": ["colesterolo hdl", "hdl colesterolo", "colesterolo hdl calcolato"],
    "COLESTEROLO LDL": ["colesterolo ldl", "ldl colesterolo calcolato",
                        "colesterolo ldl calcolato"],
    "TRIGLICERIDI": ["trigliceridi"],
    "EMOGLOBINA": ["emoglobina", "hb"],
    "EMATOCRITO": ["ematocrito", "hct"],
    "LEUCOCITI": ["leucociti", "globuli bianchi", "wbc"],
    "ERITROCITI": ["eritrociti", "globuli rossi", "rbc"],
    "PIASTRINE": ["piastrine", "plt"],
    "AST": ["ast got", "got ast", "transaminasi got", "ast"],
    "ALT": ["alt gpt", "gpt alt", "transaminasi gpt", "alt"],
    "GGT": ["gamma gt", "ggt", "gamma glutamil transferasi"],
    "ALP": ["fosfatasi alcalina", "alp"],
    "BILIRUBINA TOTALE": ["bilirubina totale"],
    "BILIRUBINA DIRETTA": ["bilirubina diretta"],
    "PROTEINE TOTALI": ["proteine totali"],
    "ALBUMINA": ["albumina"],
    "GAMMA GLOBULINE": ["gamma globuline", "gammaglobuline", "gamma"],
    "ALFA1 GLOBULINE": ["alfa 1 globuline", "alfa1"],
    "ALFA2 GLOBULINE": ["alfa 2 globuline", "alfa2"],
    "BETA GLOBULINE": ["beta globuline", "beta"],
    "TSH": ["tsh", "tsh riflesso"],
    "FT3": ["ft3"],
    "FT4": ["ft4"],
    "FERRITINA": ["ferritina"],
    "FERRO": ["ferro", "sideremia"],
    "TRANSFERRINA": ["transferrina"],
    "VITAMINA D": ["vitamina d", "vitamina d 25 oh", "25 oh vitamina d"],
    "VITAMINA B12": ["vitamina b12"],
    "FOLATI": ["folati", "acido folico"],
    "HBA1C": ["hba1c", "emoglobina glicata", "emoglobina glicata hba1c"],
    "PCR": ["pcr", "proteina c reattiva"],
    "VES": ["ves"],
    "SODIO": ["sodio"],
    "POTASSIO": ["potassio"],
    "CLORO": ["cloro"],
    "CALCIO": ["calcio"],
    "FOSFORO": ["fosforo"],
    "MAGNESIO": ["magnesio"],
    "URINE PESO SPECIFICO": ["peso specifico", "urine peso specifico"],
    "URINE PH": ["ph", "urine ph"],
    "URINE PROTEINE": ["proteine", "urine proteine"],
    "URINE GLUCOSIO": ["glucosio urine", "urine glucosio"],
    "URINE CHETONI": ["corpi chetonici", "urine corpi chetonici", "urine chetoni"],
    "URINE NITRITI": ["nitriti", "urine nitriti"],
    "URINE SANGUE": ["sangue occulto", "emoglobina urine", "urine sangue", "urine emoglobina"],
    "URINE LEUCOCITI": ["leucociti urine", "urine leucociti"],
}

ALIAS_BASE: dict[str, str] = {
    dicitura: canonico for canonico, diciture in _DIZIONARIO.items() for dicitura in diciture
}
