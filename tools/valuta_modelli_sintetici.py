#!/usr/bin/env python3
"""Valutazione preliminare e non clinica dei modelli locali di AHIA."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import re
import sys

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE))

import core
import ollama_provider


FIXTURE = RADICE / "tests" / "fixtures" / "valutazione_modelli_sintetica.json"


def valuta(modello: str, casi: list[dict]) -> dict:
    risultati = []
    for caso in casi:
        prompt = core.SYSTEM + "\n\nDATI SINTETICI:\n" + caso["contesto"]
        prompt += "\n\n" + core.PROMPT_ANALISI
        if caso.get("usa_prompt_incoerenze"):
            prompt += core.PROMPT_INCOERENZE
        risposta = ollama_provider.invia(prompt, modello, timeout=300)
        richiesti = {
            schema: bool(re.search(schema, risposta, re.IGNORECASE))
            for schema in caso["richiesti"]
        }
        vietati = {
            schema: bool(re.search(schema, risposta, re.IGNORECASE))
            for schema in caso["vietati"]
        }
        superato = all(richiesti.values()) and not any(vietati.values())
        risultati.append({
            "id": caso["id"], "superato": superato,
            "richiesti": richiesti, "vietati_presenti": vietati,
            "risposta": risposta,
        })
        print(f"{modello} · {caso['id']}: {'OK' if superato else 'DA RIVEDERE'}")
    return {
        "modello": modello,
        "casi_superati": sum(x["superato"] for x in risultati),
        "casi_totali": len(risultati),
        "risultati": risultati,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("modelli", nargs="+", help="nomi installati in Ollama")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    corpus = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rapporto = {
        "data": dt.date.today().isoformat(),
        "tipo": "valutazione automatica preliminare, non validazione clinica",
        "corpus": {k: v for k, v in corpus.items() if k != "casi"},
        "modelli": [valuta(modello, corpus["casi"]) for modello in args.modelli],
    }
    output = args.output or RADICE / "docs" / "VALUTAZIONE_MODELLI_1.26.json"
    output.write_text(
        json.dumps(rapporto, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
