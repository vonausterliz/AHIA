#!/usr/bin/env python3
"""Esegue il benchmark PII sintetico di AHIA."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE))

import benchmark_pii
import presidio_ahia


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base", action="store_true",
        help="usa solo profilo e recognizer AHIA, senza Presidio")
    parser.add_argument(
        "--verifica-obiettivi", action="store_true",
        help="restituisce codice 1 se almeno un obiettivo non è raggiunto")
    gruppo_corpus = parser.add_mutually_exclusive_group()
    gruppo_corpus.add_argument(
        "--holdout", action="store_true",
        help="usa il corpus holdout congelato, mai usato per il tuning")
    gruppo_corpus.add_argument(
        "--corpus", type=Path,
        help="usa un corpus JSON nel formato benchmark AHIA")
    args = parser.parse_args()

    percorso = (args.corpus or
                (benchmark_pii.CORPUS_HOLDOUT if args.holdout
                 else benchmark_pii.CORPUS_PREDEFINITO))
    metadata, casi = benchmark_pii.carica_corpus(percorso)
    rapporto = benchmark_pii.valuta(
        casi, benchmark_pii.rilevatore_ahia(con_presidio=not args.base))
    rapporto["corpus"] = metadata
    rapporto["motore"] = "ahia-base" if args.base else "ahia-presidio"
    if not args.base:
        rapporto["presidio"] = asdict_stato(
            presidio_ahia.stato(inizializza=True))
    print(benchmark_pii.come_json(rapporto))
    return 1 if args.verifica_obiettivi and not rapporto["superato"] else 0


def asdict_stato(stato) -> dict:
    return {
        "attivo": stato.attivo,
        "disponibile": stato.disponibile,
        "modello": stato.modello,
        "dettaglio": stato.dettaglio,
    }


if __name__ == "__main__":
    raise SystemExit(main())
