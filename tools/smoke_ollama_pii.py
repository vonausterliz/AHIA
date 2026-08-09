#!/usr/bin/env python3
"""Smoke test live: AHIA -> Ollama locale -> reidratazione."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE))

import ollama_provider
import presidio_ahia
import pseudonimizzazione as pseudo
import secondo_parere_e2e


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3:30b-instruct")
    parser.add_argument("--host", default=None)
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()

    valori = {
        "paziente": "Adelmo Zorzi",
        "medico": "Dott.ssa Nevia Lattanzi",
        "codice": "ZRDALM74E09H501C",
        "telefono": "+39 352 8046173",
    }
    testo = (
        f"Paziente: {valori['paziente']}\n"
        f"Codice fiscale: {valori['codice']}\n"
        f"Refertato da {valori['medico']}\n"
        f"Recapito: {valori['telefono']}\n"
        "Quadro clinico sintetico: pressione 128/76 mmHg, creatinina "
        "0,88 mg/dL, terapia invariata. Fornisci una breve valutazione "
        "prudente e ricopia una volta, senza modificarle, tutte le sequenze "
        "opache presenti nel testo."
    )
    rilevate, stato = presidio_ahia.rileva(
        testo, {"nome": valori["paziente"]})
    rilevate = pseudo.risolvi_sovrapposizioni(testo, rilevate)
    if not rilevate:
        print(json.dumps({"superato": False, "errore": "nessuna PII rilevata"}))
        return 1

    def provider(payload: str) -> str:
        return ollama_provider.invia(
            payload, args.model, host=args.host, timeout=args.timeout)

    iniziato = time.monotonic()
    try:
        esito = secondo_parere_e2e.esegui(testo, rilevate, provider)
    except (ollama_provider.ErroreOllama,
            secondo_parere_e2e.ErroreConfinePrivacy) as exc:
        print(json.dumps(
            {"superato": False, "errore": str(exc)}, ensure_ascii=False))
        return 1
    durata = time.monotonic() - iniziato

    token_attesi = set(esito.sessione.token_a_valore)
    token_ricevuti = set(pseudo.TOKEN_RE.findall(esito.risposta_pseudonima))
    valori_payload = [
        nome for nome, valore in valori.items()
        if valore.casefold() in esito.payload.casefold()
    ]
    valori_risposta_esterna = [
        nome for nome, valore in valori.items()
        if valore.casefold() in esito.risposta_pseudonima.casefold()
    ]
    ripristinati = [
        nome for nome, valore in valori.items()
        if valore in esito.risposta_reidratata
    ]
    superato = (
        not valori_payload and not valori_risposta_esterna
        and token_attesi <= token_ricevuti
        and not esito.token_sconosciuti and not esito.token_malformati
    )
    print(json.dumps({
        "superato": superato,
        "modello": args.model,
        "durata_secondi": round(durata, 2),
        "presidio_attivo": stato.attivo,
        "pii_rilevate": len(rilevate),
        "token_attesi": len(token_attesi),
        "token_restituiti": len(token_ricevuti & token_attesi),
        "pii_nel_payload": valori_payload,
        "pii_nella_risposta_esterna": valori_risposta_esterna,
        "valori_reidratati": ripristinati,
        "token_sconosciuti": len(esito.token_sconosciuti),
        "token_malformati": len(esito.token_malformati),
    }, ensure_ascii=False, indent=2))
    return 0 if superato else 1


if __name__ == "__main__":
    raise SystemExit(main())
