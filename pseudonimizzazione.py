"""Pseudonimizzazione reversibile del quesito per il secondo parere.

Questo modulo non conosce Streamlit, il database o i fornitori esterni. Riceve
testo e intervalli rilevati, genera token opachi per singola richiesta e conserva
la mappa esclusivamente nell'oggetto di sessione passato dal chiamante.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
import secrets
import unicodedata
from typing import Callable, Iterable


TOKEN_RE = re.compile(r"\[\[[0-9A-F]{24}\]\]")
TOKEN_SIMILE_RE = re.compile(r"\[\[[^\]\n]{1,80}\]\]")


@dataclass(frozen=True)
class Entita:
    """Intervallo identificativo rilevato nel testo sorgente."""

    start: int
    end: int
    tipo: str
    score: float = 1.0
    fonte: str = "manuale"

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError("Intervallo dell'entita' non valido")
        if not self.tipo:
            raise ValueError("Il tipo dell'entita' non puo' essere vuoto")


@dataclass
class SessionePseudonimi:
    """Mappa reversibile limitata a una richiesta.

    Non serializzare questo oggetto nei log, nel database o nel payload esterno.
    """

    richiesta_id: str = field(default_factory=lambda: secrets.token_urlsafe(12))
    token_a_valore: dict[str, str] = field(default_factory=dict)
    token_a_tipo: dict[str, str] = field(default_factory=dict)
    valore_a_token: dict[str, str] = field(default_factory=dict)
    # Valori che l'utente ha classificato come falsi positivi per la sola
    # richiesta corrente. Contiene esclusivamente forme normalizzate e resta in
    # memoria insieme alla mappa dei token.
    valori_consentiti: set[str] = field(default_factory=set)
    impronta_payload: str = ""

    def dimentica(self) -> None:
        self.token_a_valore.clear()
        self.token_a_tipo.clear()
        self.valore_a_token.clear()
        self.valori_consentiti.clear()
        self.impronta_payload = ""


@dataclass
class EsitoPseudonimizzazione:
    testo: str
    sessione: SessionePseudonimi
    entita: list[Entita]
    avvisi: list[str] = field(default_factory=list)


@dataclass
class EsitoReidratazione:
    testo: str
    token_sconosciuti: list[str] = field(default_factory=list)
    token_malformati: list[str] = field(default_factory=list)


@dataclass
class EsitoRipristino:
    testo: str
    token_ripristinati: list[str] = field(default_factory=list)
    token_sconosciuti: list[str] = field(default_factory=list)


def impronta(testo: str) -> str:
    """Impronta stabile dell'esatto payload UTF-8."""
    return hashlib.sha256(testo.encode("utf-8")).hexdigest()


def _normalizza_valore(valore: str) -> str:
    valore = unicodedata.normalize("NFKC", valore)
    return " ".join(valore.split()).casefold()


_PRIORITA_FONTE = {
    "manuale": 50,
    "personale": 45,
    "profilo": 40,
    "legacy": 30,
    "presidio": 20,
}


def _priorita(fonte: str) -> int:
    return max((p for nome, p in _PRIORITA_FONTE.items()
                if fonte.startswith(nome)), default=0)


def risolvi_sovrapposizioni(testo: str,
                            entita: Iterable[Entita]) -> list[Entita]:
    """Restituisce intervalli validi e non sovrapposti.

    Prevalgono fonte esplicita, span piu' completo e punteggio. L'ordinamento
    finale segue il testo, cosi' il risultato e' deterministico.
    """
    valide = [e for e in entita if e.end <= len(testo)]
    candidate = sorted(
        valide,
        key=lambda e: (-_priorita(e.fonte), -(e.end - e.start),
                       -e.score, e.start, e.end, e.tipo),
    )
    scelte: list[Entita] = []
    for corrente in candidate:
        if any(corrente.start < scelta.end and corrente.end > scelta.start
               for scelta in scelte):
            continue
        scelte.append(corrente)
    return sorted(scelte, key=lambda e: (e.start, e.end))


def _nuovo_token(testo: str, sessione: SessionePseudonimi,
                  generatore: Callable[[], str] | None = None) -> str:
    for _ in range(100):
        casuale = generatore() if generatore else secrets.token_hex(12).upper()
        casuale = re.sub(r"[^0-9A-F]", "", casuale.upper())
        if len(casuale) < 24:
            casuale = (casuale + secrets.token_hex(12).upper())[:24]
        else:
            casuale = casuale[:24]
        token = f"[[{casuale}]]"
        if token not in testo and token not in sessione.token_a_valore:
            return token
    raise RuntimeError("Non e' stato possibile generare un token univoco")


def pseudonimizza(testo: str, entita: Iterable[Entita], *,
                   sessione: SessionePseudonimi | None = None,
                   generatore: Callable[[], str] | None = None
                   ) -> EsitoPseudonimizzazione:
    """Sostituisce gli span rilevati con token casuali opachi.

    Le sostituzioni sono applicate da destra a sinistra per mantenere validi gli
    offset. La stessa grafia normalizzata riceve lo stesso token soltanto nella
    sessione corrente.
    """
    sessione = sessione or SessionePseudonimi()
    scelte = risolvi_sovrapposizioni(testo, entita)
    avvisi: list[str] = []

    for simile in TOKEN_SIMILE_RE.findall(testo):
        if simile not in sessione.token_a_valore:
            avvisi.append("Il testo sorgente contiene un token riservato "
                          "non appartenente alla richiesta.")
            break

    assegnazioni: list[tuple[Entita, str]] = []
    for entita_corrente in scelte:
        valore = testo[entita_corrente.start:entita_corrente.end]
        chiave = _normalizza_valore(valore)
        token = sessione.valore_a_token.get(chiave)
        if not token:
            token = _nuovo_token(testo, sessione, generatore)
            sessione.valore_a_token[chiave] = token
            sessione.token_a_valore[token] = valore
            sessione.token_a_tipo[token] = entita_corrente.tipo
        assegnazioni.append((entita_corrente, token))

    risultato = testo
    for entita_corrente, token in reversed(assegnazioni):
        risultato = (risultato[:entita_corrente.start] + token
                     + risultato[entita_corrente.end:])

    sessione.impronta_payload = impronta(risultato)
    return EsitoPseudonimizzazione(risultato, sessione, scelte, avvisi)


def reidrata(testo: str, sessione: SessionePseudonimi) -> EsitoReidratazione:
    """Ripristina esclusivamente token integri presenti nella mappa locale."""
    sconosciuti: set[str] = set()

    def sostituisci(match: re.Match[str]) -> str:
        token = match.group(0)
        valore = sessione.token_a_valore.get(token)
        if valore is None:
            sconosciuti.add(token)
            return token
        return valore

    risultato = TOKEN_RE.sub(sostituisci, testo)
    malformati = sorted({token for token in TOKEN_SIMILE_RE.findall(testo)
                         if not TOKEN_RE.fullmatch(token)})
    return EsitoReidratazione(risultato, sorted(sconosciuti), malformati)


def ripristina_falsi_positivi(
        testo: str, sessione: SessionePseudonimi,
        token: Iterable[str]) -> EsitoRipristino:
    """Ripristina token scelti e ignora quel valore solo nella richiesta.

    La mappa relativa ai token ripristinati viene eliminata immediatamente. Un
    valore modificato o una sua variante resta quindi soggetto alla scansione.
    """
    risultato = testo
    ripristinati: list[str] = []
    sconosciuti: list[str] = []
    for corrente in dict.fromkeys(token):
        valore = sessione.token_a_valore.get(corrente)
        if valore is None:
            sconosciuti.append(corrente)
            continue
        risultato = risultato.replace(corrente, valore)
        sessione.valori_consentiti.add(_normalizza_valore(valore))
        sessione.token_a_valore.pop(corrente, None)
        sessione.token_a_tipo.pop(corrente, None)
        chiave = _normalizza_valore(valore)
        if sessione.valore_a_token.get(chiave) == corrente:
            sessione.valore_a_token.pop(chiave, None)
        ripristinati.append(corrente)
    sessione.impronta_payload = impronta(risultato)
    return EsitoRipristino(risultato, ripristinati, sconosciuti)


def filtra_falsi_positivi(
        testo: str, entita: Iterable[Entita],
        sessione: SessionePseudonimi) -> list[Entita]:
    """Esclude solo gli span uguali ai valori accettati nella sessione."""
    return [
        corrente for corrente in entita
        if _normalizza_valore(testo[corrente.start:corrente.end])
        not in sessione.valori_consentiti
    ]


def verifica_payload(testo: str, sessione: SessionePseudonimi) -> list[str]:
    """Controlla collisioni, token estranei e valori noti ricomparsi."""
    avvisi: list[str] = []
    token_presenti = set(TOKEN_RE.findall(testo))
    estranei = token_presenti - set(sessione.token_a_valore)
    if estranei:
        avvisi.append(f"Sono presenti {len(estranei)} token sconosciuti.")

    malformati = {t for t in TOKEN_SIMILE_RE.findall(testo)
                  if not TOKEN_RE.fullmatch(t)}
    if malformati:
        avvisi.append(f"Sono presenti {len(malformati)} token malformati.")

    trapelati = 0
    for valore in sessione.token_a_valore.values():
        valore_norm = unicodedata.normalize("NFKC", valore).strip()
        if not valore_norm:
            continue
        schema = re.escape(valore_norm)
        schema = schema.replace(r"\ ", r"\s+")
        if valore_norm[0].isalnum():
            schema = rf"(?<!\w){schema}"
        if valore_norm[-1].isalnum():
            schema = rf"{schema}(?!\w)"
        if re.search(schema, unicodedata.normalize("NFKC", testo), re.IGNORECASE):
            trapelati += 1
    if trapelati:
        avvisi.append(f"Sembrano ricomparsi {trapelati} valori originali.")
    return avvisi


def trova_occorrenze(testo: str, valore: str) -> list[tuple[int, int]]:
    """Trova tutte le occorrenze letterali, senza attraversare token esistenti."""
    valore = valore.strip()
    if not valore:
        return []
    intervalli_token = [m.span() for m in TOKEN_SIMILE_RE.finditer(testo)]
    occorrenze = []
    for match in re.finditer(re.escape(valore), testo, re.IGNORECASE):
        if any(match.start() < fine and match.end() > inizio
               for inizio, fine in intervalli_token):
            continue
        occorrenze.append(match.span())
    return occorrenze


def rileva_valore(testo: str, valore: str, tipo: str = "ALTRO_PII",
                   occorrenze: Iterable[tuple[int, int]] | None = None, *,
                   fonte: str = "manuale",
                   ) -> list[Entita]:
    intervalli = list(occorrenze) if occorrenze is not None \
        else trova_occorrenze(testo, valore)
    return [Entita(a, b, tipo, 1.0, fonte) for a, b in intervalli]


def rileva_regole_personali(
        testo: str, regole: Iterable[tuple[str, str]]) -> list[Entita]:
    """Rileva valori ricordati usando confini lessicali quando applicabili."""
    risultati: list[Entita] = []
    intervalli_token = [m.span() for m in TOKEN_SIMILE_RE.finditer(testo)]
    for valore, tipo in regole:
        valore = (valore or "").strip()
        if not valore:
            continue
        schema = re.escape(valore)
        if valore[0].isalnum():
            schema = rf"(?<!\w){schema}"
        if valore[-1].isalnum():
            schema = rf"{schema}(?!\w)"
        for match in re.finditer(schema, testo, re.IGNORECASE):
            if any(match.start() < fine and match.end() > inizio
                   for inizio, fine in intervalli_token):
                continue
            risultati.append(Entita(match.start(), match.end(), tipo, 1.0,
                                     "personale"))
    return risultati


def rileva_profilo(testo: str, profilo: dict | None) -> list[Entita]:
    """Rileva nome completo e sue parti note dal profilo locale."""
    if not profilo:
        return []
    nome = (profilo.get("nome") or "").strip()
    if len(nome) < 3:
        return []
    valori = [nome]
    valori.extend(parte for parte in nome.split() if len(parte) >= 3)
    risultati: list[Entita] = []
    for valore in sorted(set(valori), key=len, reverse=True):
        # Il nome non deve essere estratto da un indirizzo email o da un alias
        # tecnico (es. ``mario.rossi@example.it``).
        schema = re.compile(
            rf"(?<![\w@.+-]){re.escape(valore)}(?![\w@.+-])",
            re.IGNORECASE,
        )
        risultati.extend(Entita(m.start(), m.end(), "PAZIENTE", 1.0,
                                "profilo") for m in schema.finditer(testo))
    return risultati


_PATTERN_LEGACY: list[tuple[str, re.Pattern[str], float]] = [
    ("CODICE_FISCALE",
     re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b", re.I), 1.0),
    ("CONTATTO",
     re.compile(r"(?<![\w.+-])[\w.+-]+@(?:[\w-]+\.)+[A-Z]{2,63}"
                r"(?![\w-])", re.I), 0.98),
    ("CONTATTO",
     re.compile(r"(?<!\d)(?:\+39\s?)?3\d{2}[\s.-]?\d{6,7}(?!\d)"), 0.95),
    ("DATA_CLINICA",
     re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"), 0.90),
    ("DATA_CLINICA",
     re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), 0.90),
    ("DATA_CLINICA",
     re.compile(r"\b\d{1,2}\s+(?:gennaio|febbraio|marzo|aprile|maggio|giugno|"
                r"luglio|agosto|settembre|ottobre|novembre|dicembre)\s+\d{4}\b",
                re.I), 0.92),
    ("INDIRIZZO",
     re.compile(r"\b(?:via|viale|piazza|corso|largo|vicolo)\s+"
                r"[\wÀ-ÿ' .-]+?\s*\d*(?=$|[,;\n])", re.I | re.M), 0.82),
    ("IDENTIFICATIVO_DOCUMENTO",
     re.compile(
         r"\b(?:referto|refert[oi]|nr|n[°.]?|prot(?:ocollo)?|accettazione|"
         r"acc|pratica|cartella|nosologic[oa]|id|codice|episodio|"
         r"prestazion[ei]|ricovero|impegnativa|richiesta|ordine|documento|"
         r"campione|barcode|accession)\.?\s*"
         r"(?:(?:n(?:umero)?|n[°.]|cod(?:ice)?|id)\s*)?[:#./-]?\s*"
         r"(?=[A-Z0-9._/-]{5,}\b)(?=[A-Z0-9._/-]*\d)"
         r"[A-Z0-9][A-Z0-9._/-]*",
         re.I,
     ), 0.92),
    ("IDENTIFICATIVO_DOCUMENTO",
     re.compile(r"\b[A-Z]{1,3}\d{5,}\b"), 0.82),
    ("IDENTIFICATIVO_SANITARIO",
     re.compile(r"\b\d{10,}\b"), 0.72),
    ("STRUTTURA",
     re.compile(r"\b(?:poliambulatorio|ambulatorio|ospedale|ospedaliera?|"
                r"clinica|casa\s+di\s+cura|presidio|policlinico|istituto|"
                r"fondazione|A\.?S\.?S\.?T\.?|A\.?S\.?L\.?|A\.?O\.?|IRCCS|"
                r"centro\s+medico|laboratorio\s+analisi|studio\s+medico)"
                r"[^\n,;]*", re.I), 0.82),
    ("PAZIENTE",
     re.compile(r"(?:(?<=nome: )|(?<=paziente: )|(?<=assistito: ))"
                r"[A-ZÀ-Ù][\wÀ-ÿ']+(?:\s+[A-ZÀ-Ù][\wÀ-ÿ']+){0,2}", re.I),
     0.90),
    ("MEDICO",
     re.compile(r"\b(?:(?:firmato|refertato)[ \t]+da|a[ \t]+cura[ \t]+d[ei]l?|"
                r"dott(?:\.ssa|oressa|ore|\.)?|dr(?:\.ssa|\.)?|"
                r"prof(?:\.ssa|\.)?)[ \t]*:?[ \t]*"
                r"[A-ZÀ-Ù][\wÀ-ÿ'.]+(?:[ \t]+[A-ZÀ-Ù][\wÀ-ÿ'.]+){0,2}",
                re.I), 0.88),
    ("IDENTIFICATIVO_DOCUMENTO",
     re.compile(r"\bR\.?E\.?A\.?\s*:?\s*[A-Z]{0,2}[-\s]?\d{4,}", re.I),
     0.92),
    ("CONTATTO",
     re.compile(r"\b(?:https?://|www\.)[\w.-]+\.[a-z]{2,}(?:/\S*)?", re.I),
     0.92),
    ("CONTATTO",
     re.compile(r"(?:tel|fax|telefono)\.?\s*:?\s*(?:\+39\s?)?"
                r"0\d[\d.\s/-]{5,}", re.I), 0.90),
]


def rileva_legacy(testo: str) -> list[Entita]:
    """Converte la conoscenza regex di AHIA in rilevazioni senza sostituzioni."""
    risultati: list[Entita] = []
    token_esistenti = [m.span() for m in TOKEN_SIMILE_RE.finditer(testo)]
    for tipo, schema, score in _PATTERN_LEGACY:
        for match in schema.finditer(testo):
            if any(match.start() < fine and match.end() > inizio
                   for inizio, fine in token_esistenti):
                continue
            risultati.append(Entita(match.start(), match.end(), tipo, score,
                                     "legacy"))
    return risultati


ISTRUZIONI_TOKEN = """Le sequenze delimitate da doppie parentesi quadre e
composte da 24 cifre esadecimali sono token opachi. Copiale esattamente quando
devi citarle: non modificarle, non tradurle, non spezzarle e non crearne di
nuove. Non tentare di dedurre che cosa rappresentano."""
