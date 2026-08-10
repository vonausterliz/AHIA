"""Pagine Streamlit dedicate alle impostazioni, fuori dal flusso quotidiano."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

import catalogo_modelli as catalogo
import config
import configurazione_modelli as configurazione
import core
import segreti
import semantica
import utenti
import ui_modelli_locali


def _formato_data(iso: str | None) -> str:
    if not iso:
        return "mai"
    try:
        valore = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return valore.astimezone().strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return iso


def _salva_se_cambiato(conn, chiave: str, nuovo: str, vecchio: str) -> bool:
    if nuovo == vecchio:
        return False
    core.salva_impostazione(conn, chiave, nuovo)
    return True


def mostra_modelli(conn, utente: dict, password: str | None) -> None:
    st.subheader("Modelli e provider")
    st.caption(
        "AHIA sceglie pochi modelli per ruolo. La disponibilità viene letta dai "
        "provider solo quando premi Aggiorna; nessun catalogo esterno viene "
        "contattato in automatico."
    )

    disponibili = core.modelli_disponibili()
    risolto = configurazione.risolvi(conn, disponibili)
    impostazioni = core.leggi_impostazioni(conn)

    st.markdown("### Modelli locali")
    if disponibili:
        st.success(f"Ollama attivo · {len(disponibili)} modelli installati")
    else:
        st.error(f"Ollama non raggiungibile su {config.OLLAMA_HOST}")
    if st.button("Rileggi modelli Ollama", icon=":material/refresh:", key="rileggi_ollama"):
        st.rerun()
    with st.expander(f"Modelli installati ({len(disponibili)})"):
        if disponibili:
            st.dataframe(pd.DataFrame([
                {"Provider": "Ollama", "Modello": nome, "Disponibile": "sì"}
                for nome in disponibili
            ]), hide_index=True, width="stretch")
        else:
            st.caption("Nessun modello locale rilevato.")

    modalita = st.radio(
        "Configurazione",
        ["automatico", "personalizzato"],
        index=0 if risolto["modalita"] == "automatico" else 1,
        format_func=lambda x: "Automatica (consigliata)" if x == "automatico" else "Personalizzata",
        horizontal=True,
        help="La modalità personalizzata conserva anche le scelte per-funzione delle versioni precedenti.",
    )
    if _salva_se_cambiato(conn, "modelli.modalita", modalita, risolto["modalita"]):
        st.rerun()

    profilo = st.segmented_control(
        "Priorità",
        list(configurazione.PROFILI),
        default=risolto["profilo"],
        format_func=lambda x: configurazione.PROFILI[x]["nome"],
        help="Cambia la preferenza automatica, non scarica né invia dati.",
    ) or risolto["profilo"]
    if _salva_se_cambiato(conn, "modelli.profilo", profilo, risolto["profilo"]):
        st.rerun()
    st.caption(configurazione.PROFILI[profilo]["descrizione"])

    ui_modelli_locali.mostra(conn, risolto, disponibili)

    if modalita == "personalizzato":
        st.markdown("#### Scelte per ruolo")
        st.caption("Quattro scelte coprono l'uso normale. Le eccezioni per singola funzione sono sotto.")
        for ruolo, dati in configurazione.RUOLI.items():
            corrente = impostazioni.get(f"modelli.ruolo.{ruolo}") or risolto["ruoli"].get(ruolo) or ""
            opzioni = configurazione.compatibili_per_ruolo(disponibili, ruolo)
            if corrente and corrente not in opzioni:
                opzioni.insert(0, corrente)
            if not opzioni:
                opzioni = [corrente or ""]
            nuovo = st.selectbox(
                dati["nome"], opzioni,
                index=opzioni.index(corrente) if corrente in opzioni else 0,
                help=dati["descrizione"], key=f"ruolo_modello_{ruolo}",
            )
            if _salva_se_cambiato(conn, f"modelli.ruolo.{ruolo}", nuovo, corrente):
                for funzione in dati["funzioni"]:
                    core.elimina_impostazione(conn, f"modello.{funzione}")
                st.rerun()

        with st.expander("Eccezioni per singola funzione", icon=":material/tune:"):
            st.caption("Usale solo se sai perché un compito richiede un modello diverso dal suo ruolo.")
            for funzione, dati in config.FUNZIONI.items():
                corrente = risolto["scelte"][funzione]
                ruolo_funzione = configurazione.ruolo_prevalente(funzione)
                opzioni = configurazione.compatibili_per_ruolo(
                    disponibili, ruolo_funzione)
                if corrente not in opzioni:
                    opzioni.insert(0, corrente)
                nuovo = st.selectbox(
                    dati["label"], opzioni, opzioni.index(corrente),
                    help=dati["aiuto"], key=f"eccezione_{funzione}",
                )
                if nuovo != corrente:
                    core.salva_impostazione(conn, f"modello.{funzione}", nuovo)
                    st.rerun()

    st.markdown("#### Ricerca semantica")
    emb = risolto["embedding"]
    indicizzati, frammenti = semantica.stato(conn, emb)
    con_testo, totali = core.documenti_indicizzati(conn)
    st.caption(
        f"{con_testo}/{totali} documenti con testo · {indicizzati} indicizzati "
        f"({frammenti} frammenti) · modello `{emb}`"
    )
    mancanti = semantica.da_indicizzare(conn, emb)
    if mancanti and st.button(
        f"Indicizza {len(mancanti)} documenti", icon=":material/database:", key="impostazioni_indicizza"
    ):
        avanzamento = st.progress(0.0)
        try:
            for i, riga in enumerate(mancanti, 1):
                semantica.indicizza(conn, riga["sha256"], riga["testo"], emb)
                avanzamento.progress(i / len(mancanti), text=riga["nome_file"])
            st.success("Indice aggiornato.")
            st.rerun()
        except core.ErroreOllama as exc:
            st.error(str(exc))

    st.divider()
    st.markdown("### Provider esterni")
    st.warning(
        "Disponibile non significa validato clinicamente. AHIA mostra ciò che il provider "
        "rende accessibile al tuo account; al momento nessun modello esterno ha una "
        "validazione clinica completa eseguita dal progetto AHIA."
    )
    provider = st.selectbox(
        "Provider", list(segreti.FORNITORI),
        format_func=lambda x: segreti.FORNITORI[x]["nome"], key="catalogo_provider",
    )
    cfg = segreti.FORNITORI[provider]
    configurati = segreti.fornitori_configurati(conn, utente["id"])
    chiave = segreti.leggi_chiave(conn, utente["id"], password, provider) if password else None

    c1, c2 = st.columns([2, 1])
    with c1:
        nuova = st.text_input(
            f"Chiave {cfg['nome']}", type="password", placeholder=cfg["prefisso"] + "…",
            help=f"Crea o gestisci la chiave su {cfg['dove_chiave']}", key=f"chiave_{provider}",
        )
    with c2:
        st.write("")
        st.write("")
        if st.button("Salva chiave", icon=":material/save:", key=f"salva_chiave_{provider}"):
            if not password:
                st.error("Riaccedi per cifrare la chiave con la password di sessione.")
            elif errore := segreti.convalida_formato(provider, nuova):
                st.error(errore)
            else:
                segreti.salva_chiave(conn, utente["id"], password, provider, nuova.strip())
                st.success("Chiave salvata e cifrata.")
                st.rerun()
    if provider in configurati and st.button(
        "Rimuovi chiave", icon=":material/delete:", key=f"rimuovi_chiave_{provider}"
    ):
        segreti.elimina_chiave(conn, utente["id"], provider)
        st.rerun()

    cache, aggiornata = catalogo.leggi_cache(conn, provider)
    st.caption(f"Catalogo aggiornato: {_formato_data(aggiornata)}")
    if st.button(
        "Aggiorna elenco modelli", icon=":material/refresh:",
        disabled=not chiave, key=f"aggiorna_catalogo_{provider}",
        help=None if chiave else "Salva prima la chiave del provider.",
    ):
        with st.spinner("Lettura del catalogo del provider…"):
            try:
                cache = catalogo.carica(provider, chiave=chiave or "")
                catalogo.salva_cache(conn, provider, cache)
                st.success(f"Catalogo aggiornato: {len(cache)} modelli.")
                st.rerun()
            except catalogo.ErroreCatalogo as exc:
                st.error(str(exc))

    if cache:
        compatibili = [m for m in cache if "chat" in m.capacita]
        scelto = impostazioni.get(f"modello.esterno.{provider}", cfg["modello"])
        opzioni = [m.id for m in compatibili]
        if scelto not in opzioni:
            opzioni.insert(0, scelto)
        nuovo = st.selectbox(
            "Modello per il Secondo parere", opzioni, opzioni.index(scelto),
            key=f"modello_esterno_{provider}",
        )
        if _salva_se_cambiato(conn, f"modello.esterno.{provider}", nuovo, scelto):
            st.rerun()
        per_id = {m.id: m for m in cache}
        vista_catalogo = st.segmented_control(
            "Mostra", ["In evidenza", "Compatibili", "Tutti"],
            default="Compatibili", key=f"vista_catalogo_{provider}")
        st.caption(
            "In evidenza raccoglie modelli generalisti con forte capacità di ragionamento; "
            "non è una certificazione né una validazione per uso medico.")
        pattern_evidenza = {
            "openai": ("gpt-5.5", "gpt-5.4", "o3"),
            "anthropic": ("claude-opus-4-6", "claude-sonnet-4-5"),
            "openrouter": ("openai/gpt-5.5", "openai/gpt-5.4",
                           "anthropic/claude-opus-4.6",
                           "anthropic/claude-sonnet-4.5"),
        }.get(provider, ())
        evidenza = [m for m in compatibili
                    if any(m.id.startswith(p) for p in pattern_evidenza)]
        visualizzati = (evidenza if vista_catalogo == "In evidenza" else
                        compatibili if vista_catalogo == "Compatibili" else cache)
        if vista_catalogo == "In evidenza" and not visualizzati:
            st.info("Nessun modello in evidenza è disponibile in questo catalogo.")
        righe = []
        for modello in visualizzati:
            compatibile = "chat" in modello.capacita
            righe.append({
                "Modello": modello.nome,
                "ID": modello.id,
                "Input": ", ".join(modello.input),
                "Contesto": modello.contesto,
                "€/M input": modello.costo_input_milione,
                "€/M output": modello.costo_output_milione,
                "Disponibile": "sì",
                "Compatibile AHIA": "sì" if compatibile else "no / non noto",
                "Validazione clinica AHIA": "non eseguita",
            })
        if righe:
            st.dataframe(pd.DataFrame(righe), hide_index=True, width="stretch")
        if nuovo not in per_id:
            st.error("Il modello scelto non compare più nel catalogo. AHIA non userà un fallback silenzioso.")
    else:
        st.info("Aggiorna il catalogo per scegliere tra i modelli disponibili al tuo account.")

    if provider == "openrouter":
        st.caption(
            "AHIA usa l'endpoint UE e richiede zero data retention, nessuna raccolta dati "
            "e nessun fallback. Il provider può comunque rifiutare la richiesta se nessun "
            "endpoint soddisfa questi vincoli."
        )


def mostra_privacy(conn, utente: dict) -> None:
    st.subheader("Privacy e dati")
    st.caption("Backup, posizione dell'archivio e confini di ciò che può lasciare il computer.")
    st.success(f"Archivio locale: `{config.DATA_DIR}`")
    st.markdown(
        "Le funzioni ordinarie usano Ollama in locale. Solo il Secondo parere può inviare "
        "un payload esterno, dopo pseudonimizzazione, verifica e conferma esplicita. "
        "La pseudonimizzazione riduce il rischio ma non rende anonima una storia clinica."
    )
    zip_dati = utenti.esporta_archivio(utente["id"])
    if zip_dati:
        st.download_button(
            "Esporta il mio archivio", zip_dati,
            f"ahia_{utente['nome_utente']}_{dt.date.today().isoformat()}.zip",
            mime="application/zip", icon=":material/download:", key="privacy_esporta",
        )
    else:
        st.info("Nessun dato da esportare per ora.")
    st.caption(
        "Per ripristinare il backup su un'altra installazione, usa Gestione utenti oppure "
        "scompatta lo zip nella cartella dell'utente sotto `archivi/`."
    )
