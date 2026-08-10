#!/usr/bin/env python3
"""Crea uno ZIP portabile del codice AHIA senza dati, segreti o virtualenv."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import zipfile


RADICE = Path(__file__).resolve().parents[1]


def _git(*argomenti: str) -> str:
    esito = subprocess.run(
        ["git", *argomenti], cwd=RADICE, capture_output=True,
        text=True, check=True,
    )
    return esito.stdout.strip()


def _versione() -> str:
    testo = (RADICE / "config.py").read_text(encoding="utf-8")
    risultato = re.search(r'^VERSIONE\s*=\s*"([^"]+)"', testo, re.MULTILINE)
    if not risultato:
        raise RuntimeError("VERSIONE non trovata in config.py")
    return risultato.group(1)


def crea(destinazione: Path, *, consenti_modifiche: bool = False) -> Path:
    stato = _git("status", "--porcelain")
    if stato and not consenti_modifiche:
        raise RuntimeError(
            "Il repository contiene modifiche non committate. "
            "Committale oppure usa --consenti-modifiche per un pacchetto di test."
        )
    file = [
        Path(riga) for riga in _git(
            "ls-files", "--cached", "--others", "--exclude-standard"
        ).splitlines() if riga
    ]
    versione = _versione()
    prefisso = f"AHIA-{versione}"
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    righe_manifest = [
        f"# versione={versione}",
        f"# commit={_git('rev-parse', '--short', 'HEAD')}",
        f"# working_tree_dirty={'true' if stato else 'false'}",
        "",
    ]
    with zipfile.ZipFile(destinazione, "w", zipfile.ZIP_DEFLATED) as archivio:
        for relativo in sorted(file):
            percorso = RADICE / relativo
            if not percorso.is_file():
                continue
            dati = percorso.read_bytes()
            archivio.writestr(f"{prefisso}/{relativo.as_posix()}", dati)
            impronta = hashlib.sha256(dati).hexdigest()
            righe_manifest.append(f"{impronta}  {relativo.as_posix()}")
        archivio.writestr(
            f"{prefisso}/MANIFEST.sha256",
            "\n".join(righe_manifest) + "\n",
        )
    return destinazione


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--consenti-modifiche", action="store_true")
    args = parser.parse_args()
    versione = _versione()
    output = args.output or RADICE / "builds" / f"AHIA-{versione}.zip"
    print(crea(output.resolve(), consenti_modifiche=args.consenti_modifiche))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
