#!/usr/bin/env python3
"""Smoke test isolato: autenticazione, menu e conferma download modelli."""

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
    assert "Inizia dal tuo primo referto" in titoli, titoli
    carica = next(b for b in at.button if b.label == "Carica un referto")
    carica.click().run()
    _verifica(at, "navigazione al primo referto")
    assert "Caricamento referti" in [x.value for x in at.subheader]
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
    da_installare = [b for b in pagina_modelli.button
                      if b.label == "Da installare"]
    assert da_installare, "nessun modello hardware proposto per il download"
    da_installare[0].click().run()
    _verifica(pagina_modelli, "conferma download")
    assert any(b.label == "Conferma e scarica" for b in pagina_modelli.button)

    print("OK: bootstrap, login, menu, Home, hardware e conferma download")
    dati.cleanup()
    return 0


def _verifica(at, fase: str) -> None:
    errori = [str(x.value) for x in at.exception]
    if errori:
        raise AssertionError(f"{fase}: {errori}")


if __name__ == "__main__":
    raise SystemExit(main())
