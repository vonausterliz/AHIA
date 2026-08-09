"""Client minimale per gli smoke test locali con Ollama.

Non registra prompt o risposte e traduce gli errori di rete senza includere il
contenuto clinico nel messaggio.
"""

from __future__ import annotations

import json
import os
from urllib import error, parse, request


HOST_PREDEFINITO = "http://127.0.0.1:11434"


class ErroreOllama(RuntimeError):
    pass


def _host_valido(host: str) -> str:
    host = host.strip().rstrip("/")
    analizzato = parse.urlparse(host)
    if analizzato.scheme not in {"http", "https"} or not analizzato.hostname:
        raise ErroreOllama("L'indirizzo del server Ollama non è valido.")
    if analizzato.query or analizzato.fragment or analizzato.username:
        raise ErroreOllama("L'indirizzo del server Ollama non è valido.")
    return host


def invia(prompt: str, modello: str, *, host: str | None = None,
          timeout: float = 180.0) -> str:
    """Invia un prompt non streaming e restituisce il solo testo del modello."""
    if not prompt.strip():
        raise ErroreOllama("Il prompt per Ollama è vuoto.")
    if not modello.strip():
        raise ErroreOllama("Il nome del modello Ollama è vuoto.")
    base = _host_valido(
        host or os.environ.get("OLLAMA_HOST", HOST_PREDEFINITO))
    corpo = json.dumps({
        "model": modello,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {"temperature": 0},
    }).encode("utf-8")
    richiesta = request.Request(
        base + "/api/chat", data=corpo,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(richiesta, timeout=timeout) as risposta:
            dati = json.loads(risposta.read().decode("utf-8"))
    except (error.HTTPError, error.URLError, TimeoutError, OSError) as exc:
        raise ErroreOllama(
            "Ollama non è raggiungibile o ha rifiutato la richiesta.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ErroreOllama("Ollama ha restituito una risposta non valida.") from exc
    contenuto = dati.get("message", {}).get("content")
    if not isinstance(contenuto, str) or not contenuto.strip():
        raise ErroreOllama("Ollama ha restituito una risposta vuota.")
    return contenuto
