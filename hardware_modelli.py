"""Rilevazione hardware locale e raccomandazioni Ollama conservative.

La rilevazione non usa la rete e non salva identificativi hardware. Le dimensioni
sono stime delle varianti Q4 pubblicate nella libreria Ollama: servono a spiegare
la scelta e a prevenire download sproporzionati, non sono requisiti assoluti.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import glob
import os
import platform
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class ProfiloHardware:
    ram_gb: float
    vram_gb: float
    gpu: str
    architettura: str
    memoria_unificata: bool = False

    @property
    def acceleratore_gb(self) -> float:
        if self.memoria_unificata:
            return self.ram_gb * 0.75
        return self.vram_gb

    @property
    def descrizione(self) -> str:
        parti = [f"RAM {self.ram_gb:.0f} GB"]
        if self.memoria_unificata:
            parti.append("memoria unificata")
        elif self.vram_gb:
            parti.append(f"VRAM {self.vram_gb:.0f} GB")
        else:
            parti.append("nessuna GPU dedicata rilevata")
        if self.gpu:
            parti.append(self.gpu)
        return " · ".join(parti)


@dataclass(frozen=True)
class ModelloHardware:
    id: str
    dimensione_gb: float
    nota: str


MODELLI = {
    "qwen3:4b": ModelloHardware("qwen3:4b", 2.5, "compatto"),
    "qwen3:8b": ModelloHardware("qwen3:8b", 5.2, "veloce e generalista"),
    "qwen3:14b": ModelloHardware("qwen3:14b", 9.3, "analisi locale equilibrata"),
    "qwen3:30b-instruct": ModelloHardware(
        "qwen3:30b-instruct", 19.0, "qualità maggiore, più lento"
    ),
    "qwen3-vl:4b": ModelloHardware("qwen3-vl:4b", 3.3, "visione compatta"),
    "qwen3-vl:8b": ModelloHardware("qwen3-vl:8b", 6.1, "visione equilibrata"),
    "qwen3-vl:30b": ModelloHardware("qwen3-vl:30b", 20.0, "visione di qualità"),
    "bge-m3": ModelloHardware("bge-m3", 1.2, "embedding multilingue"),
    "nomic-embed-text": ModelloHardware(
        "nomic-embed-text", 0.274, "embedding leggero"
    ),
}


def _ram_totale_gb() -> float:
    if os.name == "nt":
        try:
            import ctypes

            class StatoMemoria(ctypes.Structure):
                _fields_ = [
                    ("lunghezza", ctypes.c_ulong),
                    ("carico", ctypes.c_ulong),
                    ("totale_fisico", ctypes.c_ulonglong),
                    ("disponibile_fisico", ctypes.c_ulonglong),
                    ("totale_pagina", ctypes.c_ulonglong),
                    ("disponibile_pagina", ctypes.c_ulonglong),
                    ("totale_virtuale", ctypes.c_ulonglong),
                    ("disponibile_virtuale", ctypes.c_ulonglong),
                    ("disponibile_esteso", ctypes.c_ulonglong),
                ]

            stato = StatoMemoria()
            stato.lunghezza = ctypes.sizeof(StatoMemoria)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stato)):
                return round(stato.totale_fisico / 1024 ** 3, 1)
        except (AttributeError, OSError):
            pass
    try:
        pagine = os.sysconf("SC_PHYS_PAGES")
        dimensione = os.sysconf("SC_PAGE_SIZE")
        return round(pagine * dimensione / 1024 ** 3, 1)
    except (AttributeError, OSError, ValueError):
        return 0.0


def _nvidia() -> tuple[str, float]:
    try:
        esito = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return "", 0.0
    if esito.returncode:
        return "", 0.0
    nomi: list[str] = []
    memoria_mib = 0.0
    for riga in esito.stdout.splitlines():
        try:
            nome, memoria = riga.rsplit(",", 1)
            nomi.append(nome.strip())
            memoria_mib += float(memoria.strip())
        except (ValueError, TypeError):
            continue
    return " + ".join(nomi), round(memoria_mib / 1024, 1)


def _amd_vram() -> float:
    valori = []
    for percorso in glob.glob("/sys/class/drm/card*/device/mem_info_vram_total"):
        try:
            valori.append(int(Path(percorso).read_text(encoding="ascii").strip()))
        except (OSError, ValueError):
            continue
    return round(sum(valori) / 1024 ** 3, 1) if valori else 0.0


@lru_cache(maxsize=1)
def rileva() -> ProfiloHardware:
    sistema = platform.system()
    architettura = platform.machine() or "sconosciuta"
    ram = _ram_totale_gb()
    if sistema == "Darwin" and architettura in {"arm64", "aarch64"}:
        return ProfiloHardware(ram, ram, "Apple Silicon", architettura, True)
    gpu, vram = _nvidia()
    if not vram:
        vram = _amd_vram()
        if vram:
            gpu = "GPU AMD"
    return ProfiloHardware(ram, vram, gpu, architettura)


def raccomanda(hardware: ProfiloHardware, profilo: str) -> dict[str, str]:
    """Quattro modelli obiettivo, indipendenti da quelli già installati."""

    acceleratore = hardware.acceleratore_gb
    ram = hardware.ram_gb
    if profilo == "veloce":
        return {
            "rapido": "qwen3:4b",
            "approfondito": "qwen3:8b" if acceleratore >= 6 or ram >= 24 else "qwen3:4b",
            "visione": "qwen3-vl:4b",
            "embedding": "nomic-embed-text" if ram < 16 else "bge-m3",
        }

    if profilo == "qualita":
        grande = acceleratore >= 20 or ram >= 48
        return {
            "rapido": "qwen3:14b" if acceleratore >= 10 or ram >= 32 else "qwen3:8b",
            "approfondito": "qwen3:30b-instruct" if grande else "qwen3:14b",
            "visione": "qwen3-vl:30b" if acceleratore >= 20 else "qwen3-vl:8b",
            "embedding": "bge-m3",
        }

    # Equilibrato: privilegia modelli che restano interamente sull'acceleratore.
    if acceleratore >= 10:
        rapido, approfondito, visione = "qwen3:8b", "qwen3:14b", "qwen3-vl:8b"
    elif acceleratore >= 6:
        rapido, approfondito, visione = "qwen3:4b", "qwen3:8b", "qwen3-vl:4b"
    elif ram >= 32:
        rapido, approfondito, visione = "qwen3:8b", "qwen3:14b", "qwen3-vl:4b"
    else:
        rapido, approfondito, visione = "qwen3:4b", "qwen3:8b", "qwen3-vl:4b"
    return {
        "rapido": rapido,
        "approfondito": approfondito,
        "visione": visione,
        "embedding": "bge-m3" if ram >= 16 else "nomic-embed-text",
    }


def esecuzione_prevista(hardware: ProfiloHardware, modello: str) -> str:
    info = MODELLI.get(modello)
    if not info:
        return "requisiti non stimati"
    margine = info.dimensione_gb + max(1.5, info.dimensione_gb * 0.18)
    if hardware.memoria_unificata and margine <= hardware.acceleratore_gb:
        return "in memoria unificata"
    if hardware.vram_gb and margine <= hardware.vram_gb:
        return "interamente su GPU"
    if margine + 2 <= hardware.ram_gb:
        return "in GPU/RAM, più lento" if hardware.vram_gb else "in RAM/CPU, più lento"
    return "sconsigliato: memoria probabilmente insufficiente"
