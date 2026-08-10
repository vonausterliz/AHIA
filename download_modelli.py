"""Coda non bloccante dei download Ollama, condivisa con l'interfaccia."""

from __future__ import annotations

from dataclasses import dataclass, replace
import threading
import time
from typing import Callable, Iterable

import core


Sorgente = Callable[[str], Iterable[dict]]


@dataclass
class StatoDownload:
    id: int
    modello: str
    fase: str = "in_coda"
    messaggio: str = "In attesa…"
    completato: int = 0
    totale: int = 0
    errore: str = ""

    @property
    def attivo(self) -> bool:
        return self.fase in {"avvio", "download"}

    @property
    def pendente(self) -> bool:
        return self.fase == "in_coda" or self.attivo

    @property
    def frazione(self) -> float:
        if not self.totale:
            return 0.0
        return min(self.completato / self.totale, 1.0)


_lock = threading.RLock()
_attivita: list[StatoDownload] = []
_sorgenti: dict[int, Sorgente] = {}
_worker_in_esecuzione = False


def stati() -> list[StatoDownload]:
    """Fotografia coerente della coda corrente, inclusi gli esiti conclusi."""
    with _lock:
        return [replace(elemento) for elemento in _attivita]


def stato() -> StatoDownload | None:
    """Download in esecuzione, oppure l'ultima attività della coda."""
    elementi = stati()
    corrente = next((elemento for elemento in elementi if elemento.attivo), None)
    return corrente or (elementi[-1] if elementi else None)


def avvia(
    modello: str,
    sorgente: Sorgente | None = None,
) -> tuple[bool, str]:
    """Accoda un pull e avvia, se necessario, l'unico worker seriale."""
    global _attivita, _worker_in_esecuzione
    with _lock:
        duplicato = next(
            (elemento for elemento in _attivita
             if elemento.modello == modello and elemento.pendente),
            None,
        )
        if duplicato:
            fase = "già in corso" if duplicato.attivo else "già in coda"
            return False, f"Il download di {modello} è {fase}."

        pendenti = sum(elemento.pendente for elemento in _attivita)
        if not pendenti:
            # Una nuova richiesta dopo la fine delle precedenti apre una nuova
            # coda e non trascina nella UI una cronologia ormai conclusa.
            _attivita = []

        elemento = StatoDownload(id=time.time_ns(), modello=modello)
        _attivita.append(elemento)
        _sorgenti[elemento.id] = sorgente or core.scarica_modello

        deve_avviare_worker = not _worker_in_esecuzione
        if deve_avviare_worker:
            _worker_in_esecuzione = True
        posizione = sum(item.pendente for item in _attivita)

    if deve_avviare_worker:
        threading.Thread(
            target=_smaltisci_coda,
            name="ahia-coda-download-ollama",
            daemon=True,
        ).start()

    if posizione == 1:
        return True, f"Download di {modello} avviato."
    return True, f"{modello} aggiunto alla coda in posizione {posizione}."


def _smaltisci_coda() -> None:
    global _worker_in_esecuzione
    while True:
        with _lock:
            elemento = next(
                (item for item in _attivita if item.fase == "in_coda"), None
            )
            if not elemento:
                _worker_in_esecuzione = False
                return
            elemento.fase = "avvio"
            elemento.messaggio = "Avvio del download…"
            sorgente = _sorgenti[elemento.id]
            identificativo = elemento.id
            modello = elemento.modello

        _esegui(identificativo, modello, sorgente)
        with _lock:
            _sorgenti.pop(identificativo, None)


def _esegui(
    identificativo: int,
    modello: str,
    sorgente: Sorgente,
) -> None:
    try:
        for aggiornamento in sorgente(modello):
            with _lock:
                elemento = _trova(identificativo)
                if not elemento:
                    return
                elemento.fase = "download"
                elemento.messaggio = str(
                    aggiornamento.get("status") or "Download in corso…"
                )
                elemento.completato = int(aggiornamento.get("completed") or 0)
                elemento.totale = int(aggiornamento.get("total") or 0)
        with _lock:
            elemento = _trova(identificativo)
            if elemento:
                elemento.fase = "completato"
                elemento.messaggio = "Installazione completata"
                if elemento.totale:
                    elemento.completato = elemento.totale
    except Exception as exc:  # il worker prosegue col prossimo elemento
        with _lock:
            elemento = _trova(identificativo)
            if elemento:
                elemento.fase = "errore"
                elemento.messaggio = "Download non riuscito"
                elemento.errore = str(exc)


def _trova(identificativo: int) -> StatoDownload | None:
    return next(
        (elemento for elemento in _attivita if elemento.id == identificativo),
        None,
    )
