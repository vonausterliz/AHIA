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
    pendenti = [x for x in download_modelli.stati() if x.pendente]
    if pendenti:
        st.info(
            f"Ci sono già {len(pendenti)} download in corso o in attesa: "
            "questo modello verrà aggiunto alla coda."
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
    """Coda globale in sidebar, aggiornata senza rieseguire la pagina."""
    attivita = download_modelli.stati()
    if not attivita:
        return
    id_coda = attivita[-1].id
    if st.session_state.get("download_coda_nascosta") == id_coda:
        return

    notificati = set(st.session_state.get("download_notificati", []))
    conclusi_nuovi = [
        elemento for elemento in attivita
        if not elemento.pendente and elemento.id not in notificati
    ]
    for elemento in conclusi_nuovi:
        if elemento.fase == "completato":
            st.toast(
                f"{elemento.modello} è stato installato.",
                icon=":material/check_circle:",
            )
        else:
            st.toast(
                f"Download di {elemento.modello} non riuscito.",
                icon=":material/error:",
            )
        notificati.add(elemento.id)
    if conclusi_nuovi:
        st.session_state["download_notificati"] = list(notificati)
        if not any(elemento.pendente for elemento in attivita):
            # A coda conclusa rilegge i modelli e aggiorna i fallback.
            st.rerun(scope="app")

    st.caption("DOWNLOAD MODELLI")
    corrente = next((x for x in attivita if x.attivo), None)
    in_coda = [x for x in attivita if x.fase == "in_coda"]
    if corrente:
        testo = corrente.messaggio
        if corrente.totale:
            testo += (
                f" — {corrente.frazione:.0%} di "
                f"{corrente.totale / 1e9:.1f} GB"
            )
        st.progress(corrente.frazione, text=testo)
        st.caption(f"In corso: `{corrente.modello}`")
    if in_coda:
        nomi = " → ".join(f"`{x.modello}`" for x in in_coda)
        st.caption(f"In coda ({len(in_coda)}): {nomi}")
    if corrente or in_coda:
        st.caption("Puoi continuare a usare AHIA.")
        errori = sum(x.fase == "errore" for x in attivita)
        if errori:
            st.caption(f":material/error: {errori} download non riusciti")
        return

    completati = sum(x.fase == "completato" for x in attivita)
    errori = [x for x in attivita if x.fase == "errore"]
    if completati:
        st.success(f"Modelli installati: {completati}")
    for elemento in errori:
        st.error(f"{elemento.modello}: download non riuscito")
        if elemento.errore:
            st.caption(elemento.errore)
    if st.button("Nascondi", key=f"nascondi_coda_{id_coda}"):
        st.session_state["download_coda_nascosta"] = id_coda
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

    download_per_modello = {
        elemento.modello: elemento for elemento in download_modelli.stati()
        if elemento.pendente
    }

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
                download = download_per_modello.get(consigliato)
                etichetta_stato = (
                    "In download" if download and download.attivo
                    else "In coda" if download
                    else "Da installare"
                )
                if st.button(
                    etichetta_stato,
                    icon=":material/download:",
                    key=f"installa_consigliato_{ruolo}_{consigliato}",
                    width="stretch",
                    disabled=bool(download),
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
