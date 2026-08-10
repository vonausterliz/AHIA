"""Coda persistente e non bloccante dei download Ollama."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
import json
import os
from pathlib import Path
import shutil
import threading
import time
from typing import Callable, Iterable

import config
import core


Sorgente = Callable[[str], Iterable[dict]]
GIB = 1024 ** 3


@dataclass
class StatoDownload:
    id: int
    modello: str
    fase: str = "in_coda"
    messaggio: str = "In attesa…"
    completato: int = 0
    totale: int = 0
    errore: str = ""
    dimensione_gb: float = 0.0
    annulla_richiesto: bool = False

    @property
    def attivo(self) -> bool:
        return self.fase in {"avvio", "download"}

    @property
    def pendente(self) -> bool:
        return self.fase == "in_coda" or self.attivo

    @property
    def ripetibile(self) -> bool:
        return self.fase in {"errore", "annullato"}

    @property
    def frazione(self) -> float:
        if not self.totale:
            return 0.0
        return min(self.completato / self.totale, 1.0)


class _DownloadAnnullato(Exception):
    pass


class CodaDownload:
    """Un solo worker seriale, stato atomico su disco e API thread-safe."""

    def __init__(
        self,
        percorso: Path,
        *,
        spazio_libero: Callable[[], int] | None = None,
    ) -> None:
        self.percorso = percorso
        self._spazio_libero = spazio_libero or _spazio_libero_modelli
        self._lock = threading.RLock()
        self._attivita: list[StatoDownload] = []
        self._sorgenti: dict[int, Sorgente] = {}
        self._worker_in_esecuzione = False
        self._errore_persistenza = ""
        self._carica()

    def stati(self) -> list[StatoDownload]:
        with self._lock:
            return [replace(elemento) for elemento in self._attivita]

    def stato(self) -> StatoDownload | None:
        elementi = self.stati()
        corrente = next((x for x in elementi if x.attivo), None)
        return corrente or (elementi[-1] if elementi else None)

    def errore_persistenza(self) -> str:
        with self._lock:
            return self._errore_persistenza

    def avvia(
        self,
        modello: str,
        sorgente: Sorgente | None = None,
        *,
        dimensione_gb: float = 0.0,
    ) -> tuple[bool, str]:
        with self._lock:
            duplicato = next(
                (x for x in self._attivita
                 if x.modello == modello and x.pendente),
                None,
            )
            if duplicato:
                fase = "già in corso" if duplicato.attivo else "già in coda"
                return False, f"Il download di {modello} è {fase}."

            sufficiente, dettaglio = self.verifica_spazio(dimensione_gb)
            if not sufficiente:
                return False, dettaglio

            if not any(x.pendente for x in self._attivita):
                self._attivita = []

            elemento = StatoDownload(
                id=time.time_ns(), modello=modello,
                dimensione_gb=max(float(dimensione_gb), 0.0),
            )
            self._attivita.append(elemento)
            self._sorgenti[elemento.id] = sorgente or core.scarica_modello
            self._salva()
            deve_avviare = self._prepara_worker()
            posizione = sum(x.pendente for x in self._attivita)

        if deve_avviare:
            self._lancia_worker()
        if posizione == 1:
            return True, f"Download di {modello} avviato."
        return True, f"{modello} aggiunto alla coda in posizione {posizione}."

    def riprendi(self, sorgente: Sorgente | None = None) -> bool:
        """Riavvia le richieste pendenti caricate dal file dopo un restart."""
        with self._lock:
            pendenti = [x for x in self._attivita if x.pendente]
            if not pendenti:
                return False
            for elemento in pendenti:
                self._sorgenti.setdefault(
                    elemento.id, sorgente or core.scarica_modello
                )
            deve_avviare = self._prepara_worker()
        if deve_avviare:
            self._lancia_worker()
        return deve_avviare

    def annulla(self, identificativo: int) -> tuple[bool, str]:
        with self._lock:
            elemento = self._trova(identificativo)
            if not elemento or not elemento.pendente:
                return False, "Il download non è più annullabile."
            elemento.annulla_richiesto = True
            if elemento.fase == "in_coda":
                elemento.fase = "annullato"
                elemento.messaggio = "Rimosso dalla coda"
                self._sorgenti.pop(elemento.id, None)
            else:
                elemento.messaggio = "Annullamento richiesto…"
            self._salva()
            return True, f"Annullamento di {elemento.modello} richiesto."

    def riprova(
        self,
        identificativo: int,
        sorgente: Sorgente | None = None,
    ) -> tuple[bool, str]:
        with self._lock:
            elemento = self._trova(identificativo)
            if not elemento or not elemento.ripetibile:
                return False, "Questo download non può essere riprovato."
            sufficiente, dettaglio = self.verifica_spazio(elemento.dimensione_gb)
            if not sufficiente:
                return False, dettaglio
            elemento.fase = "in_coda"
            elemento.messaggio = "In attesa…"
            elemento.completato = 0
            elemento.totale = 0
            elemento.errore = ""
            elemento.annulla_richiesto = False
            self._sorgenti[elemento.id] = sorgente or core.scarica_modello
            self._salva()
            deve_avviare = self._prepara_worker()
        if deve_avviare:
            self._lancia_worker()
        return True, f"{elemento.modello} aggiunto nuovamente alla coda."

    def verifica_spazio(self, dimensione_gb: float) -> tuple[bool, str]:
        if dimensione_gb <= 0:
            return True, "Dimensione non disponibile."
        liberi = self._spazio_libero()
        richiesti = int(dimensione_gb * 1_000_000_000) + GIB
        if liberi >= richiesti:
            return True, f"Spazio libero: {liberi / GIB:.1f} GB."
        return False, (
            f"Spazio insufficiente: servono circa {richiesti / GIB:.1f} GB "
            f"incluso il margine di sicurezza, ma ne restano {liberi / GIB:.1f}."
        )

    def attendi(self, timeout: float = 2.0) -> bool:
        """Solo per test e arresti controllati: attende che il worker termini."""
        scadenza = time.monotonic() + timeout
        while time.monotonic() < scadenza:
            with self._lock:
                if not self._worker_in_esecuzione:
                    return True
            time.sleep(0.01)
        return False

    def _prepara_worker(self) -> bool:
        if self._worker_in_esecuzione:
            return False
        self._worker_in_esecuzione = True
        return True

    def _lancia_worker(self) -> None:
        threading.Thread(
            target=self._smaltisci_coda,
            name="ahia-coda-download-ollama",
            daemon=True,
        ).start()

    def _smaltisci_coda(self) -> None:
        try:
            while True:
                with self._lock:
                    elemento = next(
                        (x for x in self._attivita if x.fase == "in_coda"),
                        None,
                    )
                    if not elemento:
                        return
                    if elemento.annulla_richiesto:
                        elemento.fase = "annullato"
                        elemento.messaggio = "Rimosso dalla coda"
                        self._salva()
                        continue
                    elemento.fase = "avvio"
                    elemento.messaggio = "Avvio del download…"
                    self._salva()
                    sorgente = self._sorgenti.get(
                        elemento.id, core.scarica_modello
                    )
                    identificativo = elemento.id
                    modello = elemento.modello
                self._esegui(identificativo, modello, sorgente)
                with self._lock:
                    self._sorgenti.pop(identificativo, None)
        finally:
            with self._lock:
                self._worker_in_esecuzione = False
                # Copre la rara richiesta accodata fra l'ultimo controllo e
                # l'uscita del worker.
                riparti = any(x.pendente for x in self._attivita)
                if riparti:
                    self._worker_in_esecuzione = True
            if riparti:
                self._lancia_worker()

    def _esegui(
        self,
        identificativo: int,
        modello: str,
        sorgente: Sorgente,
    ) -> None:
        generatore = iter(sorgente(modello))
        ultimo_salvataggio = 0.0
        try:
            for aggiornamento in generatore:
                with self._lock:
                    elemento = self._trova(identificativo)
                    if not elemento:
                        return
                    if elemento.annulla_richiesto:
                        raise _DownloadAnnullato
                    elemento.fase = "download"
                    elemento.messaggio = str(
                        aggiornamento.get("status") or "Download in corso…"
                    )
                    elemento.completato = int(
                        aggiornamento.get("completed") or 0
                    )
                    elemento.totale = int(aggiornamento.get("total") or 0)
                    adesso = time.monotonic()
                    if adesso - ultimo_salvataggio >= 0.5:
                        self._salva()
                        ultimo_salvataggio = adesso
            with self._lock:
                elemento = self._trova(identificativo)
                if elemento:
                    if elemento.annulla_richiesto:
                        raise _DownloadAnnullato
                    elemento.fase = "completato"
                    elemento.messaggio = "Installazione completata"
                    if elemento.totale:
                        elemento.completato = elemento.totale
                    self._salva()
        except _DownloadAnnullato:
            with self._lock:
                elemento = self._trova(identificativo)
                if elemento:
                    elemento.fase = "annullato"
                    elemento.messaggio = "Download annullato"
                    self._salva()
        except Exception as exc:  # un errore non blocca il prossimo elemento
            with self._lock:
                elemento = self._trova(identificativo)
                if elemento:
                    elemento.fase = "errore"
                    elemento.messaggio = "Download non riuscito"
                    elemento.errore = str(exc)
                    self._salva()
        finally:
            chiudi = getattr(generatore, "close", None)
            if chiudi:
                chiudi()

    def _trova(self, identificativo: int) -> StatoDownload | None:
        return next(
            (x for x in self._attivita if x.id == identificativo), None
        )

    def _carica(self) -> None:
        if not self.percorso.exists():
            return
        try:
            grezzi = json.loads(self.percorso.read_text(encoding="utf-8"))
            nomi = {campo.name for campo in fields(StatoDownload)}
            self._attivita = [
                StatoDownload(**{k: v for k, v in voce.items() if k in nomi})
                for voce in grezzi.get("attivita", [])
            ]
            for elemento in self._attivita:
                if elemento.annulla_richiesto:
                    elemento.fase = "annullato"
                    elemento.messaggio = "Download annullato al riavvio"
                elif elemento.attivo:
                    elemento.fase = "in_coda"
                    elemento.messaggio = "Interrotto: in attesa di ripresa…"
                    elemento.completato = 0
                    elemento.totale = 0
            self._salva()
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self._attivita = []
            self._errore_persistenza = f"Stato download non leggibile: {exc}"

    def _salva(self) -> None:
        payload = {
            "versione": 1,
            "attivita": [asdict(elemento) for elemento in self._attivita],
        }
        temporaneo = self.percorso.with_suffix(self.percorso.suffix + ".tmp")
        try:
            self.percorso.parent.mkdir(parents=True, exist_ok=True)
            temporaneo.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.chmod(temporaneo, 0o600)
            temporaneo.replace(self.percorso)
            self._errore_persistenza = ""
        except OSError as exc:
            self._errore_persistenza = f"Coda non salvata: {exc}"
            try:
                temporaneo.unlink(missing_ok=True)
            except OSError:
                pass


def _spazio_libero_modelli() -> int:
    configurato = os.environ.get("OLLAMA_MODELS", "").strip()
    percorso = Path(configurato) if configurato else Path.home() / ".ollama" / "models"
    while not percorso.exists() and percorso != percorso.parent:
        percorso = percorso.parent
    return shutil.disk_usage(percorso).free


_coda = CodaDownload(config.DATA_DIR / "download_modelli.json")


def stati() -> list[StatoDownload]:
    return _coda.stati()


def stato() -> StatoDownload | None:
    return _coda.stato()


def avvia(
    modello: str,
    sorgente: Sorgente | None = None,
    *,
    dimensione_gb: float = 0.0,
) -> tuple[bool, str]:
    return _coda.avvia(
        modello, sorgente, dimensione_gb=dimensione_gb
    )


def riprendi() -> bool:
    return _coda.riprendi()


def annulla(identificativo: int) -> tuple[bool, str]:
    return _coda.annulla(identificativo)


def riprova(identificativo: int) -> tuple[bool, str]:
    return _coda.riprova(identificativo)


def errore_persistenza() -> str:
    return _coda.errore_persistenza()


def verifica_spazio(dimensione_gb: float) -> tuple[bool, str]:
    return _coda.verifica_spazio(dimensione_gb)
