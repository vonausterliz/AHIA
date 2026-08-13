"""Presentazione delle raccomandazioni locali e download con conferma."""

from __future__ import annotations

import streamlit as st

import configurazione_modelli as configurazione
import core
import download_modelli
import hardware_modelli


def _testo_avanzamento(elemento: download_modelli.StatoDownload) -> str:
    """Percentuale e byte leggibili, quando Ollama li rende disponibili."""
    if not elemento.totale:
        return "Preparazione del download…"
    percentuale = min(round(elemento.frazione * 100), 100)
    scaricati = elemento.completato / 1_000_000_000
    totale = elemento.totale / 1_000_000_000
    return f"{percentuale}% · {scaricati:.1f} di {totale:.1f} GB"


def _barra_download(elemento: download_modelli.StatoDownload) -> None:
    testo = f"{elemento.modello} · {_testo_avanzamento(elemento)}"
    st.progress(elemento.frazione, text=testo)
    st.caption(elemento.messaggio)


@st.dialog("Conferma il download del modello")
def _conferma_download(
    modello: str,
    ruolo: str,
    hardware: hardware_modelli.ProfiloHardware,
) -> None:
    info = hardware_modelli.MODELLI.get(modello)
    st.markdown(f"### `{modello}`")
    st.write(f"Ruolo: **{ruolo}**")
    dimensione_gb = info.dimensione_gb if info else 0.0
    if info:
        st.write(f"Download stimato: **{dimensione_gb:g} GB** · {info.nota}")
        spazio_ok, dettaglio_spazio = download_modelli.verifica_spazio(
            dimensione_gb
        )
        if spazio_ok:
            st.caption(f":material/hard_drive: {dettaglio_spazio}")
        else:
            st.error(dettaglio_spazio)
    else:
        spazio_ok = True
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
        disabled=not spazio_ok,
    ):
        avviato, messaggio = download_modelli.avvia(
            modello, dimensione_gb=dimensione_gb
        )
        if avviato:
            st.toast(messaggio, icon=":material/download:")
            st.rerun()
        else:
            st.warning(messaggio)


@st.fragment(run_every=1)
def mostra_stato_download() -> None:
    """Coda globale persistente, aggiornata senza rieseguire la pagina."""
    download_modelli.riprendi()
    attivita = download_modelli.stati()
    errore_stato = download_modelli.errore_persistenza()
    if not attivita and not errore_stato:
        return
    id_coda = attivita[-1].id if attivita else 0
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
        elif elemento.fase == "annullato":
            st.toast(
                f"Download di {elemento.modello} annullato.",
                icon=":material/cancel:",
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
            st.rerun(scope="app")

    st.caption("DOWNLOAD MODELLI")
    if errore_stato:
        st.warning(errore_stato)
    corrente = next((x for x in attivita if x.attivo), None)
    in_coda = [x for x in attivita if x.fase == "in_coda"]
    if corrente:
        _barra_download(corrente)
    if in_coda:
        nomi = " → ".join(f"`{x.modello}`" for x in in_coda)
        st.caption(f"In coda ({len(in_coda)}): {nomi}")

    pendenti = [x for x in attivita if x.pendente]
    if pendenti:
        with st.expander("Gestisci coda", icon=":material/format_list_numbered:"):
            for elemento in pendenti:
                riga, azione = st.columns([3, 1])
                riga.caption(
                    f"{elemento.modello} · "
                    f"{'in corso' if elemento.attivo else 'in attesa'}"
                )
                if azione.button(
                    "", icon=":material/cancel:",
                    help=f"Annulla {elemento.modello}",
                    key=f"annulla_download_{elemento.id}",
                ):
                    download_modelli.annulla(elemento.id)
                    st.rerun(scope="fragment")
        st.caption("La coda viene recuperata al riavvio di AHIA.")
        return

    completati = sum(x.fase == "completato" for x in attivita)
    falliti = [x for x in attivita if x.fase == "errore"]
    annullati = sum(x.fase == "annullato" for x in attivita)
    if completati:
        nomi_completati = ", ".join(
            f"`{x.modello}`" for x in attivita if x.fase == "completato"
        )
        st.success(f"Download completato: {nomi_completati}")
    if annullati:
        st.caption(f"Download annullati: {annullati}")
    for elemento in falliti:
        st.error(f"{elemento.modello}: download non riuscito")
        if elemento.errore:
            st.caption(elemento.errore)
        if st.button(
            "Riprova", icon=":material/refresh:",
            key=f"riprova_download_{elemento.id}",
        ):
            download_modelli.riprova(elemento.id)
            st.rerun(scope="fragment")
    if st.button("Nascondi", key=f"nascondi_coda_{id_coda}"):
        st.session_state["download_coda_nascosta"] = id_coda
        st.rerun(scope="fragment")


@st.fragment(run_every=1)
def mostra_avanzamento_pagina() -> None:
    """Avanzamento evidente nella pagina Modelli, oltre al riepilogo laterale."""
    download_modelli.riprendi()
    attivita = download_modelli.stati()
    corrente = next((x for x in attivita if x.attivo), None)
    in_coda = [x for x in attivita if x.fase == "in_coda"]
    completati = [x for x in attivita if x.fase == "completato"]
    falliti = [x for x in attivita if x.fase == "errore"]
    if not (corrente or in_coda or completati or falliti):
        return

    st.markdown("##### Download modelli")
    if corrente:
        _barra_download(corrente)
    if in_coda:
        st.caption(
            "In attesa: " + " → ".join(f"`{x.modello}`" for x in in_coda)
        )
    if not corrente and not in_coda and completati:
        nomi = ", ".join(f"`{x.modello}`" for x in completati)
        st.success(f"Download completato: {nomi}. Il modello è installato.")
    for elemento in falliti:
        st.error(f"Download di `{elemento.modello}` non riuscito.")
    st.divider()


def mostra(conn, risolto: dict, disponibili: list[str]) -> None:
    hardware = risolto["hardware"]
    st.markdown("#### Raccomandazioni per questa macchina")
    st.info(f":material/memory: {hardware.descrizione}")
    mostra_avanzamento_pagina()
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
