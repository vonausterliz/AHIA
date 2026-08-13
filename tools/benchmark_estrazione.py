#!/usr/bin/env python3
"""Esegue il benchmark L2 su testo sintetico e manifest di verita."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE))

import benchmark_estrazione
from config import FUNZIONI
import ingest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path,
                        default=benchmark_estrazione.CORPUS_PREDEFINITO)
    args = parser.parse_args()
    metadata, casi = benchmark_estrazione.carica_corpus(args.corpus)
    modelli = {
        nome: FUNZIONI[nome]["default"]
        for nome in ("classificazione", "estrazione_testo",
                     "estrazione_vision", "analisi")
    }
    risultati = []
    for caso in casi:
        estratto = ingest.elabora(
            ingest.Contenuto(testo=caso["testo"], immagini=[]),
            modelli,
            tipo_forzato="analisi_sangue",
        )
        risultati.append({
            "caso": caso["id"],
            **benchmark_estrazione.valuta_manifest(
                caso["truth"], estratto["esami"]
            ),
        })
    print(json.dumps(
        {"corpus": metadata, "risultati": risultati},
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
