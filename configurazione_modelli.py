"""Profili semplici e compatibilità con le impostazioni per-funzione storiche."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import config
import hardware_modelli


RUOLI = {
    "rapido": {
        "nome": "Operazioni rapide",
        "descrizione": "Classificazione, testo, dizionario e chat brevi.",
        "funzioni": ("estrazione_testo", "classificazione", "dizionario", "chat"),
    },
    "approfondito": {
        "nome": "Analisi approfondita",
        "descrizione": "Analisi clinica, struttura e compiti che richiedono più accuratezza.",
        "funzioni": ("analisi", "analisi_struttura", "diagnosi_estrazione", "estrazione_accurata"),
    },
    "visione": {
        "nome": "Visione e scansioni",
        "descrizione": "Referti fotografati o PDF che richiedono comprensione visiva.",
        "funzioni": ("estrazione_vision",),
    },
    "embedding": {
        "nome": "Ricerca semantica",
        "descrizione": "Vettori locali per cercare nei referti.",
        "funzioni": (),
    },
}

PROFILI = {
    "equilibrato": {
        "nome": "Equilibrato",
        "descrizione": "Buon compromesso tra qualità, velocità e memoria.",
    },
    "veloce": {
        "nome": "Più veloce",
        "descrizione": "Preferisce modelli piccoli per ridurre attesa e consumo di RAM.",
    },
    "qualita": {
        "nome": "Massima qualità",
        "descrizione": "Preferisce il modello locale più capace disponibile.",
    },
}

CANDIDATI = {
    "equilibrato": {
        "rapido": ("qwen3:14b", "qwen3:8b", "qwen3:30b-instruct", "qwen3:30b", "llama3.3", "gemma3:12b", "llama3.1:8b"),
        "approfondito": ("qwen3:30b-instruct", "qwen3:30b", "qwen3:32b", "qwen3:14b", "gemma3:27b"),
        "visione": ("qwen2.5vl:7b", "qwen3-vl:8b", "gemma3:12b", "llava"),
        "embedding": ("bge-m3", "nomic-embed-text", "mxbai-embed-large"),
    },
    "veloce": {
        "rapido": ("qwen3:4b", "qwen3:8b", "llama3.2:3b", "llama3.3", "qwen3:30b-instruct", "qwen3:30b", "gemma3:4b"),
        "approfondito": ("qwen3:14b", "qwen3:8b", "llama3.3", "qwen3:30b-instruct", "qwen3:30b", "gemma3:12b"),
        "visione": ("qwen2.5vl:3b", "qwen3-vl:4b", "gemma3:4b", "llava"),
        "embedding": ("nomic-embed-text", "bge-m3", "mxbai-embed-large"),
    },
    "qualita": {
        "rapido": ("qwen3:14b", "qwen3:30b-instruct", "qwen3:30b", "qwen3:32b", "llama3.3", "gemma3:27b"),
        "approfondito": ("qwen3:30b-instruct", "qwen3:30b", "qwen3:32b", "qwen3:14b", "gemma3:27b"),
        "visione": ("qwen3-vl:30b", "qwen2.5vl:32b", "qwen2.5vl:7b", "gemma3:27b"),
        "embedding": ("bge-m3", "mxbai-embed-large", "nomic-embed-text"),
    },
}


def _nome(elemento: Any) -> str:
    if isinstance(elemento, str):
        return elemento
    return str(getattr(elemento, "id", elemento))


def _ha_capacita(elemento: Any, capacita: str) -> bool:
    valori = {str(x).lower() for x in getattr(elemento, "capacita", ())}
    nome = _nome(elemento).lower()
    if capacita == "embedding":
        return "embedding" in valori or any(x in nome for x in ("embed", "bge", "nomic"))
    if capacita == "visione":
        return "visione" in valori or "vision" in valori or any(x in nome for x in ("vision", "-vl", "vl:"))
    return True


def modello_installato(
    candidato: str, disponibili: Iterable[Any]
) -> str | None:
    prefisso = candidato.lower().removesuffix(":latest")
    for elemento in disponibili:
        nome = _nome(elemento)
        basso = nome.lower().removesuffix(":latest")
        if (basso == prefisso or basso.startswith(f"{prefisso}:")
                or basso.startswith(f"{prefisso}-")):
            return nome
    return None


def _trova(disponibili: Iterable[Any], candidati: Iterable[str], capacita: str) -> str | None:
    elementi = list(disponibili)
    compatibili = [x for x in elementi if _ha_capacita(x, capacita)]
    for candidato in candidati:
        if trovato := modello_installato(candidato, compatibili):
            return trovato
    return _nome(compatibili[0]) if compatibili else None


def compatibili_per_ruolo(disponibili: Iterable[Any], ruolo: str) -> list[str]:
    capacita = "embedding" if ruolo == "embedding" else "visione" if ruolo == "visione" else ruolo
    return [_nome(x) for x in disponibili if _ha_capacita(x, capacita)]


def assegna_ruoli(
    disponibili: Iterable[Any],
    profilo: str = "equilibrato",
    raccomandati: dict[str, str] | None = None,
) -> dict[str, str | None]:
    profilo = profilo if profilo in PROFILI else "equilibrato"
    elementi = list(disponibili)
    preferenze = raccomandati or {}
    candidati = {
        ruolo: ((preferenze[ruolo],) if preferenze.get(ruolo) else ())
        + CANDIDATI[profilo][ruolo]
        for ruolo in RUOLI
    }
    return {
        ruolo: _trova(elementi, candidati[ruolo], ruolo)
        for ruolo in RUOLI
    }


def modalita(conn) -> str:
    esplicita = _leggi(conn, "modelli.modalita", "")
    if esplicita in {"automatico", "personalizzato"}:
        return esplicita
    if any(_leggi(conn, f"modello.{funzione}", "") for funzione in config.FUNZIONI):
        return "personalizzato"
    return "automatico"


def risolvi(
    conn,
    disponibili: Iterable[Any],
    profilo_hardware: hardware_modelli.ProfiloHardware | None = None,
) -> dict[str, Any]:
    """Restituisce scelte per funzione, embedding e metadati per la UI."""

    elementi = list(disponibili)
    modo = modalita(conn)
    profilo = _leggi(conn, "modelli.profilo", "equilibrato")
    if profilo not in PROFILI:
        profilo = "equilibrato"
    hardware_attivo = _leggi(conn, "modelli.hardware", "1") == "1"
    hardware = profilo_hardware or hardware_modelli.rileva()
    raccomandati = (
        hardware_modelli.raccomanda(hardware, profilo)
        if hardware_attivo else {}
    )
    ruoli = assegna_ruoli(elementi, profilo, raccomandati)
    if modo == "personalizzato":
        for ruolo in RUOLI:
            ruoli[ruolo] = _leggi(conn, f"modelli.ruolo.{ruolo}", ruoli.get(ruolo))
    scelte: dict[str, str] = {}
    for funzione in config.FUNZIONI:
        ruolo = ruolo_prevalente(funzione)
        automatico = ruoli.get(ruolo) or config.FUNZIONI[funzione]["default"]
        if modo == "personalizzato":
            scelte[funzione] = _leggi(conn, f"modello.{funzione}", automatico)
        else:
            scelte[funzione] = automatico
    embedding_auto = ruoli.get("embedding") or config.MODELLO_EMBEDDING
    embedding = (
        _leggi(conn, "modello.embedding", embedding_auto)
        if modo == "personalizzato"
        else embedding_auto
    )
    return {
        "modalita": modo,
        "profilo": profilo,
        "ruoli": ruoli,
        "scelte": scelte,
        "embedding": embedding,
        "hardware_attivo": hardware_attivo,
        "hardware": hardware,
        "raccomandati": raccomandati,
    }


def ruolo_prevalente(funzione: str) -> str:
    for ruolo, dati in RUOLI.items():
        if funzione in dati["funzioni"]:
            return ruolo
    return "rapido"


def _leggi(conn, chiave: str, predefinito: str = "") -> str:
    riga = conn.execute("SELECT valore FROM impostazioni WHERE chiave = ?", (chiave,)).fetchone()
    return str(riga[0]) if riga else predefinito
