"""Presentazione delle raccomandazioni locali e download con conferma."""

from __future__ import annotations

import streamlit as st

import configurazione_modelli as configurazione
import core
import download_modelli
import hardware_modelli


@st.dialog("Conferma il download del modello")
def _conferma_download(
    modello: str,
    ruolo: str,
    hardware: hardware_modelli.ProfiloHardware,
) -> None:
    info = hardware_modelli.MODELLI.get(modello)
    st.markdown(f"### `{modello}`")
    st.write(f"Ruolo: **{ruolo}**")
    if info:
        st.write(f"Download stimato: **{info.dimensione_gb:g} GB** · {info.nota}")
    st.write(
        "Esecuzione prevista su questa macchina: "
        f"**{hardware_modelli.esecuzione_prevista(hardware, modello)}**."
    )
    st.warning(
        "Il download viene effettuato da Ollama e può richiedere tempo e spazio "
        "su disco. Il modello non viene scaricato finché non confermi qui sotto."
    )
    annulla, conferma = st.columns(2)
    if annulla.button("Annulla", width="stretch", key=f"annulla_{modello}"):
        st.rerun()
    if conferma.button(
        "Conferma e scarica",
        type="primary",
        icon=":material/download:",
        width="stretch",
        key=f"conferma_{modello}",
    ):
        avviato, messaggio = download_modelli.avvia(modello)
        if avviato:
            st.toast(messaggio, icon=":material/download:")
            st.rerun()
        else:
            st.warning(messaggio)


@st.fragment(run_every=1)
def mostra_stato_download() -> None:
    """Indicatore globale in sidebar, aggiornato senza rieseguire la pagina."""
    download = download_modelli.stato()
    if not download or st.session_state.get("download_nascosto") == download.id:
        return

    st.caption("DOWNLOAD MODELLO")
    if download.attivo:
        testo = download.messaggio
        if download.totale:
            testo += f" — {download.frazione:.0%} di {download.totale / 1e9:.1f} GB"
        st.progress(download.frazione, text=testo)
        st.caption(f"`{download.modello}` · puoi continuare a usare AHIA")
        return

    notificato = st.session_state.get("download_notificato")
    if notificato != download.id:
        st.session_state["download_notificato"] = download.id
        if download.fase == "completato":
            st.toast(f"{download.modello} è stato installato.", icon=":material/check_circle:")
        else:
            st.toast(f"Download di {download.modello} non riuscito.", icon=":material/error:")
        st.rerun(scope="app")

    if download.fase == "completato":
        st.success(f"{download.modello} installato")
    else:
        st.error(f"Download di {download.modello} non riuscito")
        if download.errore:
            st.caption(download.errore)
    if st.button("Nascondi", key=f"nascondi_download_{download.id}"):
        st.session_state["download_nascosto"] = download.id
        st.rerun(scope="fragment")


def mostra(conn, risolto: dict, disponibili: list[str]) -> None:
    hardware = risolto["hardware"]
    st.markdown("#### Raccomandazioni per questa macchina")
    st.info(f":material/memory: {hardware.descrizione}")
    usa_hardware = st.toggle(
        "Adatta automaticamente le raccomandazioni all’hardware",
        value=risolto["hardware_attivo"],
        help=(
            "La rilevazione è interamente locale. Considera RAM, VRAM o memoria "
            "unificata; non invia né salva informazioni sulla macchina."
        ),
        key="usa_raccomandazioni_hardware",
    )
    if usa_hardware != risolto["hardware_attivo"]:
        core.salva_impostazione(conn, "modelli.hardware", "1" if usa_hardware else "0")
        st.rerun()

    intestazione = st.columns([1.35, 1.55, 1.75, 1.0])
    intestazione[0].caption("RUOLO")
    intestazione[1].caption("IN USO")
    intestazione[2].caption("CONSIGLIATO")
    intestazione[3].caption("STATO")

    for ruolo, dati in configurazione.RUOLI.items():
        in_uso = (
            risolto["embedding"]
            if ruolo == "embedding"
            else risolto["ruoli"].get(ruolo)
        )
        consigliato = risolto["raccomandati"].get(ruolo) or in_uso
        colonne = st.columns([1.35, 1.55, 1.75, 1.0])
        colonne[0].markdown(f"**{dati['nome']}**")
        colonne[1].code(in_uso or "—", language=None)
        with colonne[2]:
            st.code(consigliato or "—", language=None)
            if consigliato:
                info = hardware_modelli.MODELLI.get(consigliato)
                dimensione = f"{info.dimensione_gb:g} GB · " if info else ""
                st.caption(
                    dimensione
                    + hardware_modelli.esecuzione_prevista(hardware, consigliato)
                )
        with colonne[3]:
            if consigliato and configurazione.modello_installato(
                    consigliato, disponibili):
                st.success("Installato")
            elif consigliato:
                download = download_modelli.stato()
                in_corso = bool(download and download.attivo)
                if st.button(
                    "In download" if in_corso and download.modello == consigliato else "Da installare",
                    icon=":material/download:",
                    key=f"installa_consigliato_{ruolo}_{consigliato}",
                    width="stretch",
                    disabled=in_corso,
                ):
                    _conferma_download(consigliato, dati["nome"], hardware)
            else:
                st.caption("Non disponibile")
        st.divider()

    if risolto["modalita"] == "personalizzato":
        st.caption(
            "La raccomandazione hardware non sostituisce le tue scelte "
            "personalizzate; indica soltanto un'alternativa adatta alla macchina."
        )
