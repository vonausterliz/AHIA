"""Orchestrazione testabile del confine privacy del secondo parere."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import pseudonimizzazione as pseudo


class ErroreConfinePrivacy(RuntimeError):
    pass


@dataclass
class EsitoSecondoParere:
    payload: str
    risposta_pseudonima: str
    risposta_reidratata: str
    sessione: pseudo.SessionePseudonimi
    token_sconosciuti: list[str]
    token_malformati: list[str]


def esegui(testo: str, entita: Iterable[pseudo.Entita],
           provider: Callable[[str], str]) -> EsitoSecondoParere:
    """Pseudonimizza, invia al provider e reidrata esclusivamente in locale."""
    protetto = pseudo.pseudonimizza(testo, entita)
    payload = protetto.testo + "\n\n---\n\n" + pseudo.ISTRUZIONI_TOKEN
    protetto.sessione.impronta_payload = pseudo.impronta(payload)
    if avvisi := pseudo.verifica_payload(payload, protetto.sessione):
        raise ErroreConfinePrivacy(
            "Il payload non supera i controlli prima dell'invio: " +
            " ".join(avvisi))
    risposta_pseudonima = provider(payload)
    reidratata = pseudo.reidrata(risposta_pseudonima, protetto.sessione)
    return EsitoSecondoParere(
        payload=payload,
        risposta_pseudonima=risposta_pseudonima,
        risposta_reidratata=reidratata.testo,
        sessione=protetto.sessione,
        token_sconosciuti=reidratata.token_sconosciuti,
        token_malformati=reidratata.token_malformati,
    )
