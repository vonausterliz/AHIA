"""Dettagli tecnici separati dalle pagine d'uso quotidiano."""

import pandas as pd
import streamlit as st

import core


def mostra_log_sessione() -> None:
    st.markdown("### Ultima elaborazione e Ollama")
    with st.expander("Registro dell'ultima elaborazione", icon=":material/receipt_long:"):
        registro = st.session_state.get("registro", [])
        if not registro:
            st.caption("Nessuna elaborazione in questa sessione.")
        for nome_file, righe in registro:
            st.markdown(f"**{nome_file}**")
            for riga in righe:
                st.markdown(riga)

    with st.expander(
        "Metriche dell'ultima elaborazione", icon=":material/speed:",
        expanded=bool(st.session_state.get("log")),
    ):
        metriche = st.session_state.get("log", [])
        if not metriche:
            st.caption("Nessuna elaborazione in questa sessione.")
        else:
            st.dataframe(pd.DataFrame(metriche), width="stretch", hide_index=True)
            st.caption(
                "Un caricamento iniziale alto indica che il modello entra in memoria; "
                "molti token e pochi tok/s possono indicare immagini troppo grandi."
            )

    with st.expander("Log del server Ollama", icon=":material/terminal:"):
        percorso, contenuto = core.log_server()
        if percorso:
            st.caption(f"`{percorso}`")
        st.code(contenuto, language="log")
