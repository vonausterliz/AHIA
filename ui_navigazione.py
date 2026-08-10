"""Navigazione e barra laterale compatta di AHIA."""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

import config
import configurazione_modelli
import core


def _pagina_vuota() -> None:
    """Il contenuto resta in app.py; st.navigation gestisce URL e menu."""


PAGINA_REFERTI = st.Page(
    _pagina_vuota, title="Referti", icon=":material/lab_panel:", url_path="referti"
)
PAGINA_ANDAMENTI = st.Page(
    _pagina_vuota, title="Andamenti", icon=":material/trending_up:", url_path="andamenti"
)
PAGINA_ASSISTENTE = st.Page(
    _pagina_vuota, title="Assistente", icon=":material/assistant:", url_path="assistente"
)


def _simbolo_svg(con_testo: bool = True) -> str:
    """Marchio AHIA, orizzontale nel menu e quadrato quando è chiuso."""

    versione = config.VERSIONE
    larghezza = 330 if con_testo else 64
    testo = f"""
  <text class="ahia-nome" x="76" y="37" font-family="sans-serif"
        font-size="34" font-weight="750" letter-spacing="1.2">AHIA</text>
  <text class="ahia-sottotitolo" x="77" y="54" font-family="sans-serif"
        font-size="11.5">I tuoi referti, chiari e sotto controllo · v{versione}</text>
""" if con_testo else ""
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {larghezza} 64" role="img">
  <title>AHIA — I tuoi referti, chiari e sotto controllo</title>
  <defs>
    <linearGradient id="ahia-gradiente" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#199688"/>
      <stop offset="1" stop-color="#12675f"/>
    </linearGradient>
  </defs>
  <style>
    .ahia-nome {{ fill: #173f3b; }}
    .ahia-sottotitolo {{ fill: #536d69; }}
     (prefers-color-scheme: dark) {{
      .ahia-nome {{ fill: #f1fbf9; }}
      .ahia-sottotitolo {{ fill: #bad0cc; }}
    }}
  </style>
  <rect x="4" y="4" width="56" height="56" rx="17"
        fill="url(#ahia-gradiente)"/>
  <path d="M13 32h9l4-10 8 22 6-15 4 7h7" fill="none" stroke="#fff"
        stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="13" cy="32" r="2" fill="#fff"/>
  <circle cx="51" cy="36" r="2" fill="#fff"/>
  {testo}
</svg>
""".strip()


def _logo_svg() -> str:
    return _simbolo_svg(con_testo=True)


def _icona_svg() -> str:
    return _simbolo_svg(con_testo=False)


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
            PAGINA_REFERTI,
            PAGINA_ANDAMENTI,
            PAGINA_ASSISTENTE,
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

    st.logo(
        _logo_svg(),
        size="large",
        icon_image=_icona_svg(),
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
