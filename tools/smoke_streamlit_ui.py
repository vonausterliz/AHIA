#!/usr/bin/env python3
"""Smoke test isolato: bootstrap, login, disclaimer e Home autenticata."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile


def main() -> int:
    dati = tempfile.TemporaryDirectory(prefix="ahia-ui-smoke-")
    os.environ["AHIA_DATA_DIR"] = dati.name
    os.environ["AHIA_ADMIN_USER"] = "smokeadmin"
    os.environ["AHIA_ADMIN_PASSWORD"] = "SmokePassword!123"

    from streamlit.testing.v1 import AppTest

    app = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(app), default_timeout=30).run()
    _verifica(at, "bootstrap")
    at.text_input[0].set_value("smokeadmin")
    at.text_input[1].set_value("SmokePassword!123")
    at.button[0].click().run()
    _verifica(at, "login")
    at.checkbox[0].check()
    at.button[0].click().run()
    _verifica(at, "home")

    titoli = [x.value for x in at.title]
    didascalie = [x.value for x in at.sidebar.caption]
    assert "Il tuo archivio sanitario, in locale" in titoli, titoli
    assert any("Profilo modelli:" in x for x in didascalie), didascalie
    assert any("smokeadmin" in x for x in didascalie), didascalie
    sorgente_impostazioni = f"""
import core
import segreti
import ui_impostazioni
conn = core.apri_db({str(Path(dati.name) / "impostazioni.db")!r})
segreti.prepara(conn)
ui_impostazioni.mostra_modelli(conn, {{"id": 1, "nome_utente": "smokeadmin"}}, None)
"""
    pagina_modelli = AppTest.from_string(
        sorgente_impostazioni, default_timeout=30).run()
    _verifica(pagina_modelli, "modelli e provider")
    assert "Modelli e provider" in [x.value for x in pagina_modelli.subheader]

    print("OK: bootstrap, login, disclaimer, navigazione e Home")
    dati.cleanup()
    return 0


def _verifica(at, fase: str) -> None:
    errori = [str(x.value) for x in at.exception]
    if errori:
        raise AssertionError(f"{fase}: {errori}")


if __name__ == "__main__":
    raise SystemExit(main())
