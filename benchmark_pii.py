"""Benchmark riproducibile della pipeline PII di AHIA."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable, Iterable

import presidio_ahia
import pseudonimizzazione as pseudo


CORPUS_PREDEFINITO = (
    Path(__file__).parent / "tests" / "fixtures" /
    "pseudonimizzazione_benchmark.json"
)


@dataclass(frozen=True)
class Annotazione:
    start: int
    end: int
    tipo: str
    valore: str


@dataclass(frozen=True)
class CasoBenchmark:
    id: str
    testo: str
    annotazioni: tuple[Annotazione, ...]
    must_preserve: tuple[str, ...]
    profilo: dict | None = None


def carica_corpus(path: Path = CORPUS_PREDEFINITO
                  ) -> tuple[dict, list[CasoBenchmark]]:
    sorgente = json.loads(path.read_text(encoding="utf-8"))
    casi: list[CasoBenchmark] = []
    for gruppo in sorgente["groups"]:
        for indice, valore in enumerate(gruppo["values"], 1):
            testo = gruppo["template"].replace("{pii}", valore)
            inizio = testo.index(valore)
            profilo = {"nome": valore} if gruppo.get("profile_value") else None
            casi.append(CasoBenchmark(
                id=f"{gruppo['id']}_{indice:02d}",
                testo=testo,
                annotazioni=(Annotazione(
                    inizio, inizio + len(valore), gruppo["type"], valore),),
                must_preserve=tuple(gruppo.get("must_preserve", [])),
                profilo=profilo,
            ))
    for indice, testo in enumerate(sorgente["negative_cases"], 1):
        casi.append(CasoBenchmark(
            id=f"negativo_{indice:02d}", testo=testo, annotazioni=(),
            must_preserve=(testo,), profilo=None,
        ))
    if len(casi) != int(sorgente["target_cases"]):
        raise ValueError(
            f"Corpus incompleto: attesi {sorgente['target_cases']}, "
            f"trovati {len(casi)}")
    metadata = {chiave: sorgente[chiave] for chiave in
                ("version", "license", "provenance", "target_cases")}
    return metadata, casi


def _copre(entita: Iterable[pseudo.Entita], annotazione: Annotazione,
           tipo: str | None = None) -> bool:
    intervalli = sorted(
        (e.start, e.end) for e in entita
        if (tipo is None or e.tipo == tipo)
        and e.end > annotazione.start and e.start < annotazione.end
    )
    cursore = annotazione.start
    for inizio, fine in intervalli:
        if inizio > cursore:
            return False
        cursore = max(cursore, fine)
        if cursore >= annotazione.end:
            return True
    return False


def _rapporto(numeratore: int, denominatore: int) -> float:
    return numeratore / denominatore if denominatore else 1.0


def valuta(casi: Iterable[CasoBenchmark],
           rilevatore: Callable[[str, dict | None], Iterable[pseudo.Entita]]
           ) -> dict:
    statistiche = defaultdict(
        lambda: {"annotate": 0, "protette": 0, "tipo_corretto": 0})
    totale_predette = predette_pertinenti = 0
    leak = preservazione = round_trip = 0
    dettagli_errori: list[dict] = []
    numero_casi = 0

    for caso in casi:
        numero_casi += 1
        predette = pseudo.risolvi_sovrapposizioni(
            caso.testo, list(rilevatore(caso.testo, caso.profilo)))
        totale_predette += len(predette)
        predette_pertinenti += sum(
            1 for e in predette
            if any(e.end > a.start and e.start < a.end
                   for a in caso.annotazioni))
        esito = pseudo.pseudonimizza(caso.testo, predette)
        errori_caso: list[str] = []

        for annotazione in caso.annotazioni:
            dati_tipo = statistiche[annotazione.tipo]
            dati_tipo["annotate"] += 1
            if _copre(predette, annotazione):
                dati_tipo["protette"] += 1
            else:
                errori_caso.append(
                    f"non protetta: {annotazione.tipo}")
            if _copre(predette, annotazione, annotazione.tipo):
                dati_tipo["tipo_corretto"] += 1
            if annotazione.valore.casefold() in esito.testo.casefold():
                leak += 1
                errori_caso.append(f"leak: {annotazione.tipo}")

        for frammento in caso.must_preserve:
            if frammento not in esito.testo:
                preservazione += 1
                errori_caso.append("contenuto clinico modificato")
        if pseudo.reidrata(esito.testo, esito.sessione).testo != caso.testo:
            round_trip += 1
            errori_caso.append("round-trip fallito")
        if errori_caso:
            dettagli_errori.append(
                {"caso": caso.id, "errori": sorted(set(errori_caso))})

    totale_annotate = sum(d["annotate"] for d in statistiche.values())
    totale_protette = sum(d["protette"] for d in statistiche.values())
    totale_tipi = sum(d["tipo_corretto"] for d in statistiche.values())
    per_tipo = {
        tipo: {
            **dati,
            "recall": _rapporto(dati["protette"], dati["annotate"]),
            "accuratezza_tipo": _rapporto(
                dati["tipo_corretto"], dati["annotate"]),
        }
        for tipo, dati in sorted(statistiche.items())
    }
    precisione = _rapporto(predette_pertinenti, totale_predette)
    rapporto = {
        "casi": numero_casi,
        "annotazioni": totale_annotate,
        "predizioni": totale_predette,
        "recall": _rapporto(totale_protette, totale_annotate),
        "precisione_span": precisione,
        "accuratezza_tipo": _rapporto(totale_tipi, totale_annotate),
        "leak": leak,
        "errori_preservazione": preservazione,
        "errori_round_trip": round_trip,
        "per_tipo": per_tipo,
        "errori": dettagli_errori,
    }
    rapporto["obiettivi"] = {
        "recall_almeno_97": rapporto["recall"] >= 0.97,
        "precisione_almeno_90": precisione >= 0.90,
        "zero_leak": leak == 0,
        "zero_errori_preservazione": preservazione == 0,
        "round_trip_completo": round_trip == 0,
    }
    rapporto["superato"] = all(rapporto["obiettivi"].values())
    return rapporto


def rilevatore_ahia(con_presidio: bool = True
                    ) -> Callable[[str, dict | None], list[pseudo.Entita]]:
    def rileva(testo: str, profilo: dict | None) -> list[pseudo.Entita]:
        if con_presidio:
            return presidio_ahia.rileva(testo, profilo)[0]
        entita = pseudo.rileva_profilo(testo, profilo)
        entita.extend(pseudo.rileva_legacy(testo))
        return entita
    return rileva


def come_json(rapporto: dict) -> str:
    return json.dumps(rapporto, ensure_ascii=False, indent=2, sort_keys=True)
