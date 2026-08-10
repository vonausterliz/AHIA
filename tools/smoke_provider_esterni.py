#!/usr/bin/env python3
"""Smoke live opzionale dei provider, esclusivamente con token sintetici."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE))

import pseudonimizzazione as pseudo
import segreti


VARIABILI = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--conferma-costi", action="store_true",
        help="autorizza una breve chiamata fatturabile per ogni chiave presente",
    )
    args = parser.parse_args()
    disponibili = {
        nome: os.environ[variabile]
        for nome, variabile in VARIABILI.items()
        if os.environ.get(variabile)
    }
    if not disponibili:
        print("SKIP: nessuna chiave provider presente nell'ambiente.")
        return 0
    if not args.conferma_costi:
        print("SKIP: usa --conferma-costi per autorizzare le chiamate live.")
        return 0

    token = "[[0123456789ABCDEF01234567]]"
    payload = (
        "Caso interamente sintetico. Restituisci soltanto la parola OK seguita "
        f"dal token, copiato esattamente: {token}"
    )
    for nome, chiave in disponibili.items():
        risposta = segreti.invia(nome, chiave, payload)
        ripristino = pseudo.reidrata(
            risposta,
            pseudo.SessionePseudonimi(token_a_valore={token: "VALORE_TEST"}),
        )
        if token not in risposta or "VALORE_TEST" not in ripristino.testo:
            raise RuntimeError(f"{nome}: token non conservato correttamente")
        print(f"OK: {nome}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
