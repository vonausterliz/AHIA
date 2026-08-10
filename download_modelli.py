"""Download Ollama non bloccanti e stato condiviso con l'interfaccia."""

from __future__ import annotations

from dataclasses import dataclass, replace
import threading
import time
from typing import Callable, Iterable

import core


@dataclass
class StatoDownload:
    id: int
    modello: str
    fase: str = "avvio"
    messaggio: str = "Avvio del download…"
    completato: int = 0
    totale: int = 0
    errore: str = ""

    @property
    def attivo(self) -> bool:
        return self.fase in {"avvio", "download"}

    @property
    def frazione(self) -> float:
        if not self.totale:
            return 0.0
        return min(self.completato / self.totale, 1.0)


_lock = threading.RLock()
_corrente: StatoDownload | None = None


def stato() -> StatoDownload | None:
    """Restituisce una fotografia coerente del download corrente o più recente."""
    with _lock:
        return replace(_corrente) if _corrente else None


def avvia(
    modello: str,
    sorgente: Callable[[str], Iterable[dict]] | None = None,
) -> tuple[bool, str]:
    """Avvia un pull in un thread; rifiuta pull concorrenti sulla stessa istanza."""
    global _corrente
    with _lock:
        if _corrente and _corrente.attivo:
            if _corrente.modello == modello:
                return False, f"Il download di {modello} è già in corso."
            return False, f"Attendi il download di {_corrente.modello} prima di avviarne un altro."
        _corrente = StatoDownload(id=time.time_ns(), modello=modello)
        identificativo = _corrente.id

    thread = threading.Thread(
        target=_esegui,
        args=(identificativo, modello, sorgente or core.scarica_modello),
        name=f"ahia-pull-{modello}",
        daemon=True,
    )
    thread.start()
    return True, f"Download di {modello} avviato."


def _esegui(
    identificativo: int,
    modello: str,
    sorgente: Callable[[str], Iterable[dict]],
) -> None:
    try:
        for aggiornamento in sorgente(modello):
            with _lock:
                if not _corrente or _corrente.id != identificativo:
                    return
                _corrente.fase = "download"
                _corrente.messaggio = str(
                    aggiornamento.get("status") or "Download in corso…"
                )
                _corrente.completato = int(aggiornamento.get("completed") or 0)
                _corrente.totale = int(aggiornamento.get("total") or 0)
        with _lock:
            if _corrente and _corrente.id == identificativo:
                _corrente.fase = "completato"
                _corrente.messaggio = "Installazione completata"
                if _corrente.totale:
                    _corrente.completato = _corrente.totale
    except Exception as exc:  # il worker non deve mai morire senza informare la UI
        with _lock:
            if _corrente and _corrente.id == identificativo:
                _corrente.fase = "errore"
                _corrente.messaggio = "Download non riuscito"
                _corrente.errore = str(exc)
