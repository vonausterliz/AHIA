"""Metriche per il benchmark L2 sui manifest di verita FAKING_MEDDOC."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from typing import Iterable

import ingest


CORPUS_PREDEFINITO = (
    Path(__file__).parent / "tests" / "fixtures" / "faking_meddoc_corpus.json"
)
CORPUS_DOMINIO = (
    Path(__file__).parent / "tests" / "fixtures" / "ahia_domain_corpus.json"
)


def carica_corpus(path: Path = CORPUS_PREDEFINITO) -> tuple[dict, list[dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    casi = payload.get("cases", [])
    if len(casi) != payload.get("target_cases"):
        raise ValueError(
            f"Corpus incompleto: attesi {payload.get('target_cases')}, "
            f"trovati {len(casi)}"
        )
    metadata = {
        chiave: valore for chiave, valore in payload.items() if chiave != "cases"
    }
    return metadata, casi


def _normalizzati(esami: Iterable[dict], alias: dict[str, str]) -> list[dict]:
    sconosciuti: set[str] = set()
    risultati = []
    for esame in esami:
        adattato = {
            "nome_referto": esame.get("nome_referto", esame.get("nome", "")),
            "valore": esame.get("valore", ""),
            "unita": esame.get("unita", ""),
            "range_min": esame.get("range_min"),
            "range_max": esame.get("range_max"),
            "flag": esame.get("flag", ""),
        }
        if normalizzato := ingest.normalizza(adattato, alias, sconosciuti):
            risultati.append(normalizzato)
    return risultati


def _per_analita(esami: Iterable[dict]) -> dict[str, list[dict]]:
    gruppi: dict[str, list[dict]] = defaultdict(list)
    for esame in esami:
        gruppi[esame["analita"]].append(esame)
    return gruppi


def valuta_manifest(
    manifest: dict,
    estratti: Iterable[dict],
    alias: dict[str, str] | None = None,
    *,
    tolleranza_relativa: float = 0.001,
) -> dict:
    """Confronta l'estrazione con la verita, senza pretendere ordine identico."""
    alias = alias or ingest.carica_alias(Path("/percorso/inesistente"))
    attesi = _normalizzati(manifest.get("esami", []), alias)
    predetti = _normalizzati(estratti, alias)
    per_atteso = _per_analita(attesi)
    per_predetto = _per_analita(predetti)

    trovati = valori_corretti = unita_corrette = 0
    mancanti: list[str] = []
    errori_valore: list[str] = []
    errori_unita: list[str] = []
    for analita, voci in per_atteso.items():
        disponibili = per_predetto.get(analita, [])
        for indice, atteso in enumerate(voci):
            if indice >= len(disponibili):
                mancanti.append(analita)
                continue
            trovato = disponibili[indice]
            trovati += 1
            valore_atteso = atteso["valore"]
            valore_trovato = trovato["valore"]
            scala = max(abs(valore_atteso or 0), 1.0)
            if (
                valore_atteso is not None
                and valore_trovato is not None
                and abs(valore_trovato - valore_atteso)
                <= tolleranza_relativa * scala
            ):
                valori_corretti += 1
            else:
                errori_valore.append(analita)
            if trovato["unita"].casefold() == atteso["unita"].casefold():
                unita_corrette += 1
            else:
                errori_unita.append(analita)

    allucinazioni = []
    for analita, voci in per_predetto.items():
        eccedenza = len(voci) - len(per_atteso.get(analita, []))
        allucinazioni.extend([analita] * max(0, eccedenza))

    totale = len(attesi)
    return {
        "attesi": totale,
        "estratti": len(predetti),
        "trovati": trovati,
        "recall_analiti": trovati / totale if totale else 1.0,
        "accuratezza_valori": valori_corretti / trovati if trovati else 0.0,
        "accuratezza_unita": unita_corrette / trovati if trovati else 0.0,
        "allucinazioni": len(allucinazioni),
        "mancanti": mancanti,
        "errori_valore": errori_valore,
        "errori_unita": errori_unita,
        "analiti_allucinati": allucinazioni,
    }
