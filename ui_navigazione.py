"""Navigazione e barra laterale compatta di AHIA."""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

import config
import configurazione_modelli
import core


def _pagina_vuota() -> None:
    """Il contenuto resta in app.py; st.navigation gestisce URL e menu."""


def costruisci(
    conn,
    utente: dict,
    e_admin: bool,
    *,
    esci: Callable[[], None],
    mostra_avvertenza: Callable[[], None],
) -> tuple[str, dict[str, str], dict[str, str], str, bool, int, list[str]]:
    sezioni = {
        "Uso quotidiano": [
            st.Page(_pagina_vuota, title="Home", icon=":material/home:", url_path="home", default=True),
            st.Page(_pagina_vuota, title="Referti", icon=":material/lab_panel:", url_path="referti"),
            st.Page(_pagina_vuota, title="Andamenti", icon=":material/trending_up:", url_path="andamenti"),
            st.Page(_pagina_vuota, title="Assistente", icon=":material/assistant:", url_path="assistente"),
            st.Page(_pagina_vuota, title="Secondo parere", icon=":material/share:", url_path="secondo-parere"),
        ],
        "Gestione": [
            st.Page(_pagina_vuota, title="Profilo", icon=":material/badge:", url_path="profilo"),
            st.Page(
                _pagina_vuota, title="Dizionario e riferimenti",
                icon=":material/menu_book:", url_path="dizionario"),
        ],
        "Impostazioni": [
            st.Page(_pagina_vuota, title="Modelli e provider", icon=":material/smart_toy:", url_path="modelli"),
            st.Page(_pagina_vuota, title="Privacy e dati", icon=":material/shield:", url_path="privacy"),
            st.Page(_pagina_vuota, title="Diagnostica", icon=":material/monitoring:", url_path="diagnostica"),
            st.Page(_pagina_vuota, title="Guida", icon=":material/help:", url_path="guida"),
        ],
    }
    if e_admin:
        sezioni["Impostazioni"].insert(
            -2,
            st.Page(_pagina_vuota, title="Utenti", icon=":material/group:", url_path="utenti"),
        )

    selezionata = st.navigation(sezioni, position="sidebar")
    pagina = selezionata.url_path or "home"
    selezionata.run()

    modelli = core.modelli_disponibili()
    impostazioni = core.leggi_impostazioni(conn)
    risolto = configurazione_modelli.risolvi(conn, modelli)
    scelti = risolto["scelte"]
    emb = risolto["embedding"]
    strumenti = impostazioni.get("chat.strumenti", "1") == "1"
    n_referti = int(impostazioni.get("contesto.n_referti", 4))

    with st.sidebar:
        st.title(":material/monitor_heart: AHIA")
        st.caption(f"Archivio e lettura dei tuoi referti · v{config.VERSIONE}")
        if modelli:
            st.success(f"Ollama attivo · {len(modelli)} modelli")
        else:
            st.error("Ollama non raggiungibile")
        st.caption(
            f"Profilo modelli: **{configurazione_modelli.PROFILI[risolto['profilo']]['nome']}** · "
            f"{'automatico' if risolto['modalita'] == 'automatico' else 'personalizzato'}"
        )
        st.caption(
            f":material/account_circle: **{utente['nome_utente']}**"
            + (" · amministratore" if e_admin else "")
        )
        if st.button("Esci", icon=":material/logout:", width="stretch", key="nav_esci"):
            esci()
        if st.button(
            "Avvertenza e limiti", icon=":material/info:", width="stretch", key="nav_avvertenza"
        ):
            mostra_avvertenza()
        st.caption(f"Dati locali in `{config.DATA_DIR}`")
        st.caption(f"AGPL-3.0 · [codice sorgente]({config.REPO_URL})")

    return pagina, impostazioni, scelti, emb, strumenti, n_referti, modelli
