"""Adapter opzionale fra AHIA e Presidio Analyzer.

Presidio e spaCy sono caricati soltanto alla prima analisi. In loro assenza il
modulo restituisce comunque le rilevazioni deterministiche di AHIA e uno stato
esplicito, senza impedire l'avvio dell'applicazione.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
import threading

from pseudonimizzazione import (Entita, TOKEN_SIMILE_RE, rileva_legacy,
                                rileva_profilo, rileva_regole_personali)


@dataclass(frozen=True)
class StatoPresidio:
    attivo: bool
    disponibile: bool
    modello: str
    dettaglio: str = ""


_lock = threading.Lock()
_analyzer = None
_errore: str | None = None


def _abilitato() -> bool:
    return os.environ.get("AHIA_PRESIDIO_ENABLED", "1").strip().lower() \
        not in {"0", "false", "no", "off"}


def modello_configurato() -> str:
    return os.environ.get("AHIA_PRESIDIO_MODEL", "it_core_news_lg").strip()


def soglia_configurata(tipo_presidio: str | None = None) -> float:
    """Soglia globale o specifica per entita.

    AHIA_PRESIDIO_SCORE_PERSON prevale sulla variabile globale soltanto per
    PERSON. Valori non validi ricadono sulla soglia globale, limitata a 0..1.
    """
    globale = os.environ.get("AHIA_PRESIDIO_SCORE", "0.55")
    nome = f"AHIA_PRESIDIO_SCORE_{tipo_presidio}" if tipo_presidio else ""
    grezza = os.environ.get(nome, globale) if nome else globale
    try:
        return min(1.0, max(0.0, float(grezza)))
    except ValueError:
        if tipo_presidio:
            try:
                return min(1.0, max(0.0, float(globale)))
            except ValueError:
                pass
        return 0.55


def modalita_strict() -> bool:
    return os.environ.get("AHIA_PRESIDIO_STRICT", "0").strip().lower() \
        in {"1", "true", "yes", "on"}


def _crea_analyzer():
    """Crea AnalyzerEngine con NER e recognizer italiani di Presidio."""
    from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    configurazione = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "it", "model_name": modello_configurato()}],
    }
    provider = NlpEngineProvider(nlp_configuration=configurazione)
    nlp_engine = provider.create_engine()
    registro = RecognizerRegistry(supported_languages=["it"])
    registro.load_predefined_recognizers(
        languages=["it"], nlp_engine=nlp_engine, countries=["it"])
    return AnalyzerEngine(
        registry=registro,
        nlp_engine=nlp_engine,
        supported_languages=["it"],
    )


def _ottieni_analyzer():
    global _analyzer, _errore
    if not _abilitato():
        return None
    if _analyzer is not None or _errore is not None:
        return _analyzer
    with _lock:
        if _analyzer is not None or _errore is not None:
            return _analyzer
        try:
            _analyzer = _crea_analyzer()
        except (ImportError, ModuleNotFoundError) as exc:
            _errore = ("Presidio o il modello NLP italiano non sono installati "
                       f"({exc.__class__.__name__}).")
        except Exception as exc:
            _errore = f"Presidio non disponibile: {exc.__class__.__name__}."
    return _analyzer


def stato(*, inizializza: bool = False) -> StatoPresidio:
    if not _abilitato():
        return StatoPresidio(False, False, modello_configurato(),
                             "Disattivato da AHIA_PRESIDIO_ENABLED.")
    if inizializza:
        _ottieni_analyzer()
    if _analyzer is not None:
        return StatoPresidio(True, True, modello_configurato(), "")
    if _errore:
        return StatoPresidio(False, False, modello_configurato(), _errore)
    return StatoPresidio(False, True, modello_configurato(),
                         "Non ancora inizializzato.")


_TIPI = {
    "PERSON": "PERSONA",
    "LOCATION": "LOCALITA",
    "ORGANIZATION": "STRUTTURA",
    "IT_FISCAL_CODE": "CODICE_FISCALE",
    "IT_DRIVER_LICENSE": "IDENTIFICATIVO_DOCUMENTO",
    "IT_IDENTITY_CARD": "IDENTIFICATIVO_DOCUMENTO",
    "IT_PASSPORT": "IDENTIFICATIVO_DOCUMENTO",
}


def _accetta_risultato_ner(testo: str, risultato) -> bool:
    """Riduce falsi positivi clinici noti del NER generico italiano.

    Il modello assegna spesso lo stesso punteggio a nomi veri e ad analiti,
    farmaci o unita. Le regole sono quindi strutturali e non dipendono dal solo
    score: una persona NER deve avere almeno due parole; una localita composta
    è ammessa, mentre una localita di una parola richiede un indicatore nel
    contesto immediatamente precedente.
    """
    valore = testo[risultato.start:risultato.end].strip()
    parole = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ']+", valore)
    if risultato.entity_type == "PERSON":
        return len(parole) >= 2 and all(len(parola) >= 2 for parola in parole)
    if risultato.entity_type == "LOCATION":
        if len(valore) < 3 or any(carattere.isdigit() for carattere in valore):
            return False
        if len(parole) >= 2:
            return True
        prefisso = testo[max(0, risultato.start - 40):risultato.start]
        return bool(re.search(
            r"(?:\b(?:a|da|presso|in|di)\s+|"
            r"(?:luogo|comune|citt[aà]|residenza|domicilio)\s*:\s*)$",
            prefisso, re.IGNORECASE))
    return True


def rileva_presidio(testo: str) -> tuple[list[Entita], StatoPresidio]:
    analyzer = _ottieni_analyzer()
    stato_corrente = stato()
    if analyzer is None:
        return [], stato_corrente
    try:
        risultati = analyzer.analyze(
            text=testo,
            language="it",
            entities=list(_TIPI),
            score_threshold=min(soglia_configurata(tipo) for tipo in _TIPI),
        )
    except Exception as exc:
        return [], StatoPresidio(
            False, False, modello_configurato(),
            f"Analisi Presidio fallita: {exc.__class__.__name__}.",
        )
    token_esistenti = [m.span() for m in TOKEN_SIMILE_RE.finditer(testo)]
    entita = [
        Entita(r.start, r.end, _TIPI[r.entity_type], float(r.score), "presidio")
        for r in risultati
        if r.entity_type in _TIPI
        and float(r.score) >= soglia_configurata(r.entity_type)
        and 0 <= r.start < r.end <= len(testo)
        and _accetta_risultato_ner(testo, r)
        and not any(r.start < fine and r.end > inizio
                    for inizio, fine in token_esistenti)
    ]
    return entita, stato_corrente


def rileva(testo: str, profilo: dict | None = None,
           regole_personali: list[tuple[str, str]] | None = None
           ) -> tuple[list[Entita], StatoPresidio]:
    """Unisce profilo, recognizer AHIA e NER Presidio."""
    entita = rileva_regole_personali(testo, regole_personali or [])
    entita.extend(rileva_profilo(testo, profilo))
    entita.extend(rileva_legacy(testo))
    rilevate_presidio, stato_corrente = rileva_presidio(testo)
    entita.extend(rilevate_presidio)
    return entita, stato_corrente


def _reset_cache_per_test() -> None:
    global _analyzer, _errore
    with _lock:
        _analyzer = None
        _errore = None
