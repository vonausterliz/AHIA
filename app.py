"""AHIA — archivio, andamenti e lettura assistita dei referti, tutto offline.

Avvio:  streamlit run app.py
"""

# AHIA — archivio e lettura dei referti medici, in locale.
# Copyright (C) 2026  {AUTORE}
#
# Questo programma e' software libero: puoi ridistribuirlo e/o modificarlo
# secondo i termini della GNU Affero General Public License, versione 3, come
# pubblicata dalla Free Software Foundation.
#
# Distribuito nella speranza che sia utile, ma SENZA ALCUNA GARANZIA, neppure
# quella implicita di commerciabilita' o idoneita' a uno scopo particolare.
# Vedi la GNU Affero General Public License per i dettagli:
# https://www.gnu.org/licenses/agpl-3.0.html

from __future__ import annotations

import json
import time

import pandas as pd
import streamlit as st

import config
import core
import grafici
import ingest
import parere
import riferimenti
import semantica
import strumenti
import utenti
from config import (BRANI_NEL_CONTESTO, DATA_DIR, DISCLAIMER,
                    DISCLAIMER_VERSIONE, FUNZIONI, MODELLO_EMBEDDING,
                    OLLAMA_HOST, REPO_URL, TIPI, VERSIONE, e_tabellare,
                    etichetta)

st.set_page_config(page_title="AHIA — referti e andamenti",
                   page_icon=":material/monitor_heart:", layout="wide")


@st.cache_resource
def get_auth():
    """Database delle utenze, condiviso."""
    return utenti.apri()


@st.cache_resource
def get_archivio(utente_id: int):
    """Database sanitario dell'utente. Uno per utente, file separati."""
    return core.apri_db(config.Archivio(utente_id).db)


@st.cache_data(ttl=600, show_spinner=False)
def brani_pertinenti(utente_id: int, domanda: str, modello: str,
                     quanti: int) -> str:
    """Recupero semantico memorizzato.

    Senza cache ogni interazione con un widget rieseguirebbe lo script e con
    esso una chiamata di embedding a Ollama: centinaia di millisecondi buttati
    a ogni clic, per una risposta che non cambia.
    """
    try:
        return semantica.brani_per_contesto(
            semantica.cerca(get_archivio(utente_id), domanda, quanti, modello))
    except core.ErroreOllama:
        return ""


auth = get_auth()


def _primo_avvio():
    """Creazione dell'amministratore: l'app non esiste finche' non c'e'."""
    st.title(":material/shield_person: Crea l'amministratore")
    st.info("Questa e' l'utenza amministratore: non serve crearne un'altra "
            "dopo. Potrai accedere con queste credenziali e troverai la scheda "
            "**Utenti** per creare gli altri account.")
    env_utente, env_password = utenti.variabile_admin_iniziale()
    if env_utente and env_password:
        errore = utenti.crea(auth, env_utente, env_password, "admin", False)
        if not errore:
            st.success(f"Amministratore «{env_utente}» creato dalle variabili "
                       "d'ambiente.")
            st.rerun()
        st.error(errore)

    with st.form("primo_admin"):
        nome = st.text_input("Nome utente")
        pw1 = st.text_input("Password", type="password",
                            help=f"Almeno {utenti.LUNGHEZZA_MINIMA} caratteri e "
                                 "tre tipi di carattere diversi.")
        pw2 = st.text_input("Ripeti la password", type="password")
        if st.form_submit_button("Crea amministratore", type="primary",
                                 icon=":material/person_add:"):
            if pw1 != pw2:
                st.error("Le due password non coincidono.")
            elif errore := utenti.crea(auth, nome, pw1, "admin", False):
                st.error(errore)
            else:
                nuovo_id = auth.execute(
                    "SELECT id FROM utenti WHERE nome_utente=?",
                    (nome,)).fetchone()["id"]
                if utenti.migra_archivio_singolo(nuovo_id):
                    st.info("L'archivio della versione precedente e' stato "
                            "assegnato a questa utenza.")
                st.success(f"Amministratore «{nome}» creato: accedi con queste "
                           "credenziali. La gestione degli altri utenti e' "
                           "nella scheda Utenti.")
                st.rerun()
    st.caption("La password viene salvata solo come impronta scrypt: se la "
               "dimentichi non e' recuperabile, va reimpostata cancellando il "
               "database.")


def _accedi():
    st.title(":material/lock: AHIA")
    st.caption("Archivio e lettura dei tuoi referti")
    with st.form("accesso"):
        nome = st.text_input("Nome utente")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Accedi", type="primary",
                                 icon=":material/login:"):
            utente, errore = utenti.verifica(auth, nome, password)
            if utente:
                st.session_state["utente"] = utente
                st.rerun()
            else:
                st.error(errore)


def _cambia_password_obbligatorio(utente: dict):
    st.title(":material/key: Cambio password")
    st.write("Al primo accesso devi scegliere una password personale.")
    with st.form("cambio"):
        pw1 = st.text_input("Nuova password", type="password")
        pw2 = st.text_input("Ripeti la password", type="password")
        if st.form_submit_button("Salva", type="primary", icon=":material/save:"):
            if pw1 != pw2:
                st.error("Le due password non coincidono.")
            elif errore := utenti.cambia_password(auth, utente["id"], pw1):
                st.error(errore)
            else:
                st.session_state["utente"]["cambio_password"] = False
                st.rerun()


if not utenti.esistono_utenti(auth):
    _primo_avvio()
    st.stop()

utente_corrente = st.session_state.get("utente")
if not utente_corrente:
    _accedi()
    st.stop()

if utente_corrente.get("cambio_password"):
    _cambia_password_obbligatorio(utente_corrente)
    st.stop()

e_admin = utente_corrente["ruolo"] == "admin"

# Da qui in poi si lavora esclusivamente sull'archivio dell'utente collegato:
# file diverso per ogni utente, quindi nessuna query puo' vedere altri dati.
archivio = config.Archivio(utente_corrente["id"])
conn = get_archivio(utente_corrente["id"])
alias = ingest.carica_alias(archivio.alias)

CHIAVE_DISCLAIMER = "disclaimer.versione_accettata"


@st.dialog("Prima di usare AHIA — Before using AHIA", width="large")
def avvertenza(bloccante: bool = True):
    lingua = st.segmented_control("Lingua", ["Italiano", "English"],
                                  default="Italiano", label_visibility="collapsed")
    st.markdown(DISCLAIMER["en" if lingua == "English" else "it"])
    if not bloccante:
        return
    letto = st.checkbox("Ho letto e compreso quanto sopra / "
                        "I have read and understood the above")
    if st.button("Accetto e prosegui / Accept and continue", type="primary",
                 icon=":material/check:", disabled=not letto, key="btn_accetto_e_prosegui_accept_and_cont_182"):
        core.salva_impostazione(conn, CHIAVE_DISCLAIMER, DISCLAIMER_VERSIONE)
        st.rerun()


if core.leggi_impostazioni(conn).get(CHIAVE_DISCLAIMER) != DISCLAIMER_VERSIONE:
    avvertenza()
    st.stop()


def riapplica_alias(alias: dict[str, str]) -> int:
    """Ricalcola l'analita canonico sulle righe gia' salvate. Nessuna chiamata LLM."""
    aggiornate = 0
    for r in conn.execute("SELECT id, nome_referto, analita FROM risultati"):
        canonico = ingest.canonico_di(r["nome_referto"], alias)
        if canonico and canonico != r["analita"]:
            conn.execute("UPDATE risultati SET analita = ? WHERE id = ?",
                         (canonico, r["id"]))
            aggiornate += 1
    conn.commit()
    return aggiornate


def mostra_risposta(model: str, messaggi: list[dict], funzione: str) -> str:
    """Rende la risposta in streaming, mostrando anche la fase di ragionamento."""
    with st.chat_message("assistant"):
        stato = st.status("In attesa del modello…", expanded=False)
        segnaposto = st.empty()
        pensiero, testo = "", ""
        try:
            for tipo, pezzo in core.chat_stream(model, messaggi, funzione):
                if tipo == "pensiero":
                    pensiero += pezzo
                    stato.update(label=f"Il modello sta ragionando… "
                                       f"({len(pensiero)} caratteri)")
                    stato.write(pezzo)
                else:
                    if not testo:
                        stato.update(label="Ragionamento concluso", state="complete")
                    testo += pezzo
                    segnaposto.markdown(testo)
        except core.ErroreOllama as e:
            stato.update(label="Errore", state="error")
            st.error(str(e))
            return ""
        if not testo:
            stato.update(label="Nessuna risposta", state="error")
            st.warning("Il modello non ha prodotto testo. Se e' un modello con "
                       "ragionamento, potrebbe aver esaurito il contesto: riduci "
                       "i referti nel contesto o disattiva `think` in config.py.")
        else:
            stato.update(label="Completato", state="complete")
        return testo


# --- Barra laterale --------------------------------------------------------

with st.sidebar:
    # CSS su una stringa costante scritta qui: nessun dato esterno finisce
    # nel markup, a differenza dei nomi provenienti dai referti.
    st.markdown(
        """<style>
        section[data-testid="stSidebar"] h1 {
            font-size: 2.9rem;
            font-weight: 700;
            letter-spacing: 0.06em;
            padding-bottom: 0.1rem;
        }
        section[data-testid="stSidebar"] h1 span[data-testid="stIconMaterial"] {
            font-size: 2.4rem;
            vertical-align: -4px;
        }
        </style>""", unsafe_allow_html=True)
    st.title(":material/monitor_heart: AHIA")
    st.caption(f"Archivio e lettura dei tuoi referti · v{VERSIONE}")
    modelli = core.modelli_disponibili()
    if modelli:
        st.success(f"Ollama attivo — {len(modelli)} modelli")
    else:
        st.error(f"Ollama non raggiungibile su {OLLAMA_HOST}")

    impostazioni = core.leggi_impostazioni(conn)
    scelti: dict[str, str] = {}
    with st.expander("Modelli per funzione", icon=":material/tune:", expanded=True):
        for chiave, cfg in FUNZIONI.items():
            salvato = impostazioni.get(f"modello.{chiave}", cfg["default"])
            if modelli:
                opzioni = modelli if salvato in modelli else [salvato, *modelli]
                valore = st.selectbox(cfg["label"], opzioni, opzioni.index(salvato),
                                      help=cfg["aiuto"], key=f"mod_{chiave}")
            else:
                valore = st.text_input(cfg["label"], salvato, help=cfg["aiuto"],
                                       key=f"mod_{chiave}")
            if valore != salvato:
                core.salva_impostazione(conn, f"modello.{chiave}", valore)
            if cfg["think"]:
                st.caption(":material/psychology: ragionamento attivo")
            if modelli and valore not in modelli:
                st.caption(":material/warning: non installato")
                if st.button(f"Scarica {valore}", key=f"pull_{chiave}",
                             icon=":material/download:", width="stretch"):
                    barra = st.progress(0.0, text="avvio del download…")
                    try:
                        for stato in core.scarica_modello(valore):
                            tot = stato.get("total") or 0
                            fatto = stato.get("completed") or 0
                            etichetta = stato.get("status", "")
                            if tot:
                                etichetta += f" — {fatto / tot:.0%} di {tot / 1e9:.1f} GB"
                            barra.progress(min(fatto / tot, 1.0) if tot else 0.0,
                                           text=etichetta)
                        st.success(f"{valore} scaricato.")
                        st.rerun()
                    except core.ErroreOllama as e:
                        st.error(str(e))
            scelti[chiave] = valore

    disponibili = core.numero_prelievi(conn)
    with st.expander("Ricerca semantica", icon=":material/manage_search:"):
        emb_salvato = impostazioni.get("modello.embedding", MODELLO_EMBEDDING)
        if modelli:
            opzioni_e = modelli if emb_salvato in modelli else [emb_salvato, *modelli]
            emb = st.selectbox("Modello di embedding", opzioni_e,
                               opzioni_e.index(emb_salvato),
                               help="Multilingue: bge-m3 e' il piu' affidabile "
                                    "sull'italiano medico. I valori di laboratorio "
                                    "non vengono vettorizzati: restano in SQL.")
        else:
            emb = st.text_input("Modello di embedding", emb_salvato)
        if emb != emb_salvato:
            core.salva_impostazione(conn, "modello.embedding", emb)
        if modelli and emb not in modelli:
            st.caption(":material/warning: non installato")

        indicizzati, frammenti = semantica.stato(conn, emb)
        con_testo, totali = core.documenti_indicizzati(conn)
        st.caption(f"{con_testo}/{totali} documenti con testo · "
                   f"{indicizzati} indicizzati ({frammenti} frammenti)")

        mancanti = semantica.da_indicizzare(conn, emb)
        if mancanti and st.button(f"Indicizza {len(mancanti)} documenti",
                                  icon=":material/database:", width="stretch", key="btn_indicizza_documenti_308"):
            avanzamento = st.progress(0.0)
            try:
                for i, r in enumerate(mancanti, 1):
                    semantica.indicizza(conn, r["sha256"], r["testo"], emb)
                    avanzamento.progress(i / len(mancanti), text=r["nome_file"])
                st.success("Indice aggiornato.")
                st.rerun()
            except core.ErroreOllama as e:
                st.error(str(e))
        elif not mancanti and con_testo:
            st.caption(":material/check_circle: indice allineato")

    tool_attivi = impostazioni.get("chat.strumenti", "1") == "1"
    nuovo_tool = st.toggle("Strumenti nella chat", tool_attivi,
                           help="Il modello puo' interrogare l'archivio (serie "
                                "storiche, conteggi, ricerca nei referti) invece "
                                "di rispondere solo con cio' che vede nel "
                                "contesto. Piu' preciso ma piu' lento, e richiede "
                                "un modello che supporti i tool.")
    if nuovo_tool != tool_attivi:
        core.salva_impostazione(conn, "chat.strumenti", "1" if nuovo_tool else "0")
        st.rerun()

    n_default = int(impostazioni.get("contesto.n_referti", 4))
    if disponibili > 1:
        massimo = max(disponibili, n_default)
        n_referti = st.slider(f"Referti nel contesto (ne hai {disponibili})",
                              1, massimo, min(n_default, massimo))
        if n_referti != n_default:
            core.salva_impostazione(conn, "contesto.n_referti", str(n_referti))
    else:
        n_referti = n_default

    # Ollama tronca il prompt senza avvisare se supera num_ctx
    token = core.stima_token(core.costruisci_contesto(conn, n_referti))
    ctx_min = min(FUNZIONI[f]["num_ctx"] for f in ("analisi", "chat"))
    quota = token / ctx_min
    if quota > 0.6:
        st.warning(f"Contesto ~{token:,} token su {ctx_min:,} disponibili. "
                   "Riduci i referti o alza `num_ctx` in config.py, "
                   "altrimenti Ollama tronca il prompt senza avvisare.".replace(",", "."))
    else:
        st.caption(f"Contesto ~{token:,} token ({quota:.0%} di {ctx_min:,})"
                   .replace(",", "."))

    c1, c2 = st.columns([2, 1])
    c1.caption(f":material/account_circle: **{utente_corrente['nome_utente']}**"
               + (" · amministratore" if e_admin else ""))
    if c2.button("Esci", icon=":material/logout:", width="stretch", key="btn_esci_358"):
        st.session_state.pop("utente", None)
        st.rerun()

    st.caption(f"Dati in `{DATA_DIR}` — nulla lascia questa macchina.")
    if st.button("Avvertenza e limiti d'uso", icon=":material/info:",
                 width="stretch", key="btn_avvertenza_e_limiti_d_uso_363"):
        avvertenza(bloccante=False)
    st.caption("Strumento sperimentale, non un dispositivo medico. "
               "Non sostituisce il parere del medico.")
    st.caption(f"AGPL-3.0 · [codice sorgente]({REPO_URL})")

etichette_schede = [
    ":material/badge: Profilo",
    ":material/lab_panel: Referti",
    ":material/trending_up: Andamenti",
    ":material/insights: Analisi",
    ":material/forum: Chat",
    ":material/share: Secondo parere",
    ":material/menu_book: Dizionario",
]
if e_admin:
    etichette_schede.append(":material/group: Utenti")
tabs = st.tabs(etichette_schede)

# --- Profilo ---------------------------------------------------------------

with tabs[0]:
    st.subheader("Profilo")
    st.caption("Contestualizza i valori: range e rilevanza di uno scostamento "
               "dipendono da eta' e sesso.")
    p = core.leggi_profilo(conn)
    with st.form("profilo"):
        c1, c2, c3 = st.columns(3)
        nome = c1.text_input("Nome o etichetta", p.get("nome") or "")
        anno = c2.number_input("Anno di nascita", 1900, 2025,
                               int(p.get("anno_nascita") or 1980))
        sesso = c3.selectbox("Sesso biologico", ["", "F", "M"],
                             ["", "F", "M"].index(p.get("sesso") or ""))
        c4, c5 = st.columns(2)
        altezza = c4.number_input("Altezza (cm)", 0.0, 250.0,
                                  float(p.get("altezza_cm") or 0), step=1.0,
                                  help="In centimetri: 175, non 1,75. "
                                       "I valori sotto 3 vengono convertiti.")
        peso = c5.number_input("Peso (kg)", 0.0, 300.0, float(p.get("peso_kg") or 0),
                               step=0.5)
        bmi_corrente = core.calcola_bmi(core.normalizza_altezza(altezza), peso)
        if bmi_corrente:
            c5.caption(f"BMI {bmi_corrente}")
        terapie = st.text_area("Terapie in corso", p.get("terapie") or "",
                               placeholder="farmaco, dosaggio, da quando")
        note = st.text_area("Note", p.get("note") or "",
                            placeholder="condizioni note, interventi, abitudini")
        if st.form_submit_button("Salva", type="primary", icon=":material/save:"):
            core.salva_profilo(conn, {
                "nome": nome, "anno_nascita": int(anno), "sesso": sesso,
                "altezza_cm": altezza or None, "peso_kg": peso or None,
                "terapie": terapie, "note": note})
            corretta = core.normalizza_altezza(altezza)
            if corretta and corretta != altezza:
                st.info(f"Altezza interpretata come {corretta:.0f} cm.")
            if impostazioni.get("catalogo.attivo", "0") == "1":
                n_cat = core.applica_catalogo(conn, sesso, archivio.riferimenti)
                if n_cat:
                    st.info(f"{n_cat} intervalli del catalogo riallineati al "
                            "sesso indicato.")
            st.success("Profilo salvato.")

# --- Referti ---------------------------------------------------------------

with tabs[1]:
    st.subheader("Caricamento referti")
    st.caption(f"`{scelti['estrazione_testo']}` per i PDF nativi, "
               f"`{scelti['estrazione_vision']}` per le scansioni.")
    caricati = st.file_uploader("PDF dei referti", "pdf", accept_multiple_files=True)
    c1, c2 = st.columns([2, 3])
    forza = c1.checkbox("Rielabora anche i file gia' presenti")
    tipo_forzato = c2.selectbox(
        "Tipologia", ["Riconosci automaticamente", *TIPI],
        format_func=lambda t: t if t == "Riconosci automaticamente" else etichetta(t),
        help="Forza la tipologia quando il riconoscimento automatico sbaglia. "
             "Si puo' correggere anche dopo, dall'elenco.")
    tipo_scelto = None if tipo_forzato == "Riconosci automaticamente" else tipo_forzato

    if caricati and st.button("Elabora", type="primary",
                              icon=":material/play_arrow:", key="btn_elabora_442"):
        sconosciuti: set[str] = set()
        st.session_state["log"] = []
        st.session_state["registro"] = []
        barra = st.progress(0.0)

        for i, up in enumerate(caricati, 1):
            avvio = time.perf_counter()
            righe_log: list[str] = []

            with st.status(f"{up.name}", expanded=True) as riquadro:

                def annota(messaggio: str, righe=righe_log, avvio=avvio):
                    """Una riga di registro con il tempo trascorso."""
                    trascorso = time.perf_counter() - avvio
                    riga = f"`{trascorso:5.1f}s`  {messaggio}"
                    righe.append(riga)
                    st.write(riga)

                blob = up.read()
                sha = core.sha256_bytes(blob)
                annota(f"Impronta del file `{sha[:12]}`")

                if core.file_gia_presente(conn, sha) and not forza:
                    annota("File gia' presente in archivio: saltato. "
                           "Spunta «Rielabora» per forzarne la rilettura.")
                    riquadro.update(label=f"{up.name} — gia' presente",
                                    state="complete")
                    barra.progress(i / len(caricati))
                    st.session_state["registro"].append((up.name, righe_log))
                    continue

                percorso = archivio.pdf / f"{sha[:12]}_{core.nome_file_sicuro(up.name)}"
                percorso.write_bytes(blob)
                annota(f"Copia archiviata in `{percorso.name}`")

                try:
                    dati_doc, origine, log_modello = None, None, []
                    doc = ingest.elabora_documento(percorso, scelti, tipo_scelto,
                                                   progress=annota)
                    st.session_state["log"] += [{"file": up.name, **r}
                                                for r in doc["log"]]
                except core.ErroreOllama as e:
                    annota(f"**Errore:** {e}")
                    riquadro.update(label=f"{up.name} — errore Ollama",
                                    state="error")
                    doc = None
                except Exception as e:  # JSON malformato, PDF illeggibile
                    annota(f"**Errore:** {type(e).__name__}: {e}")
                    riquadro.update(label=f"{up.name} — elaborazione fallita",
                                    state="error")
                    doc = None

                if doc:
                    righe = [r for e in doc["esami"]
                             if (r := ingest.normalizza(e, alias, sconosciuti))]
                    nuovi_nomi = [r["nome_referto"] for r in righe
                                  if r["analita"] in
                                  {n.upper() for n in sconosciuti}]
                    if righe:
                        annota(f"Normalizzazione: {len(righe)} valori ricondotti "
                               f"a {len({r['analita'] for r in righe})} analiti")
                    if nuovi_nomi:
                        annota(f"Diciture nuove da mappare: "
                               f"{', '.join(sorted(set(nuovi_nomi))[:6])}"
                               + (" …" if len(set(nuovi_nomi)) > 6 else ""))

                    if e_tabellare(doc["tipo"]) and not doc["data_documento"]:
                        annota("**Attenzione:** data non rilevata, i valori non "
                               "saranno confrontabili nel tempo.")

                    nuove = core.salva_referto(conn, sha, up.name, doc["origine"],
                                               {"data_prelievo": doc["data_documento"],
                                                "laboratorio": doc["struttura"]},
                                               righe)
                    core.salva_documento(conn, sha, doc)
                    annota(f"Salvati {nuove} valori nuovi"
                           + (f" ({len(righe) - nuove} gia' presenti)"
                              if len(righe) > nuove else ""))

                    testo_doc = doc["testo"] or "\n".join(
                        filter(None, [doc["narrativa"].get("sintesi"),
                                      doc["narrativa"].get("conclusioni")]))
                    core.salva_testo(conn, sha, testo_doc)
                    if testo_doc:
                        annota(f"Indicizzato per la ricerca: {len(testo_doc)} caratteri")

                    if impostazioni.get("catalogo.attivo", "0") == "1":
                        n_cat = core.applica_catalogo(
                            conn, core.leggi_profilo(conn).get("sesso", ""),
                            archivio.riferimenti)
                        if n_cat:
                            annota(f"Catalogo: completati {n_cat} intervalli mancanti")

                    riquadro.update(
                        label=f"{TIPI[doc['tipo']]['icona']} {up.name} — "
                              f"{etichetta(doc['tipo'])} · "
                              f"{doc['data_documento'] or 'senza data'} · "
                              f"{time.perf_counter() - avvio:.0f}s",
                        state="complete", expanded=False)

                st.session_state["registro"].append((up.name, righe_log))
            barra.progress(i / len(caricati))

        if sconosciuti:
            st.warning(f"{len(sconosciuti)} diciture non riconosciute: "
                       "mappale nella scheda Dizionario.")

    st.divider()
    st.subheader("Cerca nei referti")
    c1, c2 = st.columns([4, 1])
    domanda = c1.text_input("cerca", placeholder="steatosi, ritmo sinusale, tiroide…",
                            label_visibility="collapsed")
    modo_ricerca = c2.selectbox("modo", ["Parole", "Significato"],
                                label_visibility="collapsed",
                                help="Parole: ricerca esatta, immediata, trova tutto. "
                                     "Significato: trova anche i sinonimi, richiede "
                                     "l'indice semantico.")
    if domanda:
        if modo_ricerca == "Parole":
            esiti = core.cerca_testo(conn, domanda)
            if not esiti:
                st.info("Nessuna corrispondenza.")
            for r in esiti:
                testa = etichetta(r["tipo"]) if r["tipo"] else "Documento"
                st.markdown(f"**{testa}** · {r['data_documento'] or 'senza data'} · "
                            f"{r['titolo'] or r['nome_file']}")
                st.caption(r["estratto"])
        else:
            try:
                brani = semantica.cerca(conn, domanda, 5,
                                        impostazioni.get("modello.embedding",
                                                         MODELLO_EMBEDDING))
            except core.ErroreOllama as e:
                st.error(str(e))
                brani = []
            if not brani:
                st.info("Nessun risultato: forse l'indice semantico non e' ancora "
                        "stato costruito (barra laterale).")
            for b in brani:
                testa = etichetta(b["tipo"]) if b["tipo"] else "Documento"
                st.markdown(f"**{testa}** · {b['data'] or 'senza data'} · "
                            f"{b['titolo'] or b['nome_file']} "
                            f"· affinita' {b['punteggio']:.0%}")
                st.caption(b["testo"])

    st.divider()
    st.subheader("Archivio per tipologia")

    gruppi = core.documenti_per_tipo(conn)
    orfani = [r for r in core.elenco_file(conn)
              if not any(r["sha256"] == d["sha256"]
                         for lista in gruppi.values() for d in lista)]

    if not gruppi and not orfani:
        st.info("Nessun documento caricato.")
    else:
        conteggi = " · ".join(f"{TIPI[t]['icona']} {etichetta(t)}: {len(v)}"
                              for t, v in gruppi.items() if t in TIPI)
        if conteggi:
            st.markdown(conteggi)

        # Ogni documento genera due widget: con centinaia di referti la scheda
        # diventerebbe pesante. Si mostrano i piu' recenti, con la possibilita'
        # di aprire tutto quando serve.
        LIMITE = 25
        for tipo in [t for t in TIPI if t in gruppi]:
            righe = gruppi[tipo]
            with st.expander(f"{etichetta(tipo)} ({len(righe)})",
                             icon=TIPI[tipo]["icona"]):
                if len(righe) > LIMITE:
                    tutti = st.checkbox(
                        f"Mostra tutti i {len(righe)} documenti "
                        f"(predefinito: i {LIMITE} piu' recenti)",
                        key=f"tutti_{tipo}")
                    if not tutti:
                        righe = righe[:LIMITE]
                for d in righe:
                    c1, c2, c3 = st.columns([3, 2, 1])
                    testa = d["data_documento"] or "senza data"
                    c1.markdown(f"**{testa}** — {d['titolo'] or d['nome_file']}")
                    dettagli = []
                    if d["struttura"]:
                        dettagli.append(d["struttura"])
                    if d["n_esami"]:
                        dettagli.append(f"{d['n_esami']} valori")
                    dettagli.append(d["origine"])
                    c1.caption(" · ".join(dettagli))

                    nuovo_tipo = c2.selectbox(
                        "tipologia", list(TIPI), index=list(TIPI).index(tipo),
                        format_func=etichetta, key=f"tipo_{d['sha256']}",
                        label_visibility="collapsed")
                    if nuovo_tipo != tipo:
                        core.cambia_tipo(conn, d["sha256"], nuovo_tipo)
                        st.rerun()
                    if c3.button("Elimina", key=f"del_{d['sha256']}",
                                 icon=":material/delete:", width="stretch"):
                        core.elimina_referto(conn, d["sha256"])
                        st.rerun()

                    if d["sintesi"]:
                        with st.container(border=True):
                            st.write(d["sintesi"])
                            if d["conclusioni"]:
                                st.markdown(f"**Conclusioni:** {d['conclusioni']}")
                    st.divider()

        if orfani:
            with st.expander(f"Senza tipologia ({len(orfani)}) — caricati con una "
                             "versione precedente", icon=":material/help:"):
                for r in orfani:
                    c1, c2 = st.columns([3, 2])
                    c1.markdown(f"**{r['data_prelievo'] or 'senza data'}** — "
                                f"{r['nome_file']} · {r['n_esami']} valori")
                    scelta_t = c2.selectbox("tipologia", list(TIPI),
                                            index=list(TIPI).index("analisi_sangue"),
                                            format_func=etichetta,
                                            key=f"orf_{r['sha256']}",
                                            label_visibility="collapsed")
                    if c2.button("Assegna", key=f"ass_{r['sha256']}",
                                 icon=":material/label:", width="stretch"):
                        core.salva_documento(conn, r["sha256"], {
                            "tipo": scelta_t, "data_documento": r["data_prelievo"],
                            "titolo": r["nome_file"], "struttura": "",
                            "narrativa": {}})
                        st.rerun()

        with st.expander("Ultimo referto di laboratorio in dettaglio",
                         icon=":material/table_view:"):
            ultimo = core.ultimo_referto(conn)
            if ultimo:
                st.dataframe(pd.DataFrame([dict(r) for r in ultimo])[
                    ["analita", "nome_referto", "valore_testo", "unita",
                     "range_min", "range_max", "flag"]],
                    width="stretch", hide_index=True)
            else:
                st.caption("Nessun valore di laboratorio in archivio.")

    st.divider()
    st.subheader("Log")

    with st.expander("Registro dell'ultima elaborazione",
                     icon=":material/receipt_long:",
                     expanded=False):
        if not st.session_state.get("registro"):
            st.caption("Nessuna elaborazione in questa sessione.")
        for nome_file, righe in st.session_state.get("registro", []):
            st.markdown(f"**{nome_file}**")
            for r in righe:
                st.markdown(r)

    with st.expander("Metriche dell'ultima elaborazione", icon=":material/speed:",
                     expanded=bool(st.session_state.get("log"))):
        if not st.session_state.get("log"):
            st.caption("Nessuna elaborazione in questa sessione.")
        else:
            st.dataframe(pd.DataFrame(st.session_state["log"]),
                         width="stretch", hide_index=True)
            st.caption("`caricamento_s` alto solo alla prima chiamata e' normale: "
                       "e' il modello che entra in memoria. `tok_s` bassi con "
                       "`token_in` molto alti indicano pagine rasterizzate troppo "
                       "grandi: abbassa DPI_RASTER in config.py.")

    with st.expander("Log del server Ollama", icon=":material/terminal:"):
        percorso, contenuto = core.log_server()
        if percorso:
            st.caption(f"`{percorso}`")
        st.code(contenuto, language="log")

# --- Andamenti -------------------------------------------------------------

with tabs[2]:
    st.subheader("Andamenti nel tempo")
    analiti = core.elenco_analiti(conn)
    if not analiti:
        st.info("Carica almeno un referto per vedere gli andamenti.")
    else:
        fuori = core.analiti_fuori_range(conn)
        MODI = {
            "fuori_range": "Indicatori fuori norma nell'ultimo referto",
            "ultimi": "Gli ultimi che avevo aperto",
            "fissi": "Un elenco fisso che scelgo io",
        }
        modo = impostazioni.get("andamenti.modo", "fuori_range")
        salvati = [a for a in json.loads(
            impostazioni.get("andamenti.selezione", "[]")) if a in analiti]

        if "sel_andamenti" not in st.session_state:
            if modo == "fuori_range":
                iniziale = (fuori or analiti)[:4]
            else:
                iniziale = salvati or (fuori or analiti)[:4]
            st.session_state["sel_andamenti"] = iniziale

        c1, c2 = st.columns([5, 1])
        with c1:
            selezione = st.multiselect("Indicatori da tracciare", analiti,
                                       key="sel_andamenti")
        with c2:
            st.markdown("&nbsp;")
            with st.popover("All'avvio", icon=":material/settings:",
                            width="stretch"):
                nuovo_modo = st.radio("Quando apro la scheda, mostra",
                                      list(MODI), format_func=MODI.get,
                                      index=list(MODI).index(modo))
                if nuovo_modo != modo:
                    core.salva_impostazione(conn, "andamenti.modo", nuovo_modo)
                    st.rerun()
                if nuovo_modo == "fissi":
                    if st.button("Fissa la selezione corrente",
                                 icon=":material/push_pin:", width="stretch", key="btn_fissa_la_selezione_corrente_689"):
                        core.salva_impostazione(conn, "andamenti.selezione",
                                                json.dumps(selezione))
                        st.success("Elenco fissato.")
                    if salvati:
                        st.caption("Fissati ora: " + ", ".join(salvati))
                elif nuovo_modo == "fuori_range":
                    st.caption(f"{len(fuori)} indicatori attualmente fuori norma."
                               if fuori else "Nessun indicatore fuori norma: "
                               "verranno mostrati i primi in ordine alfabetico.")

        # in modalita' "ultimi" la selezione corrente diventa quella di domani
        if modo == "ultimi" and selezione != salvati:
            core.salva_impostazione(conn, "andamenti.selezione",
                                    json.dumps(selezione))
        df = grafici.serie_df(conn, selezione)

        doppie = [d for d in core.misure_duplicate(conn) if d["analita"] in selezione]
        if doppie:
            with st.expander(f"{len(doppie)} misurazioni ripetute nella stessa data",
                             icon=":material/report:"):
                st.caption("Nel grafico compare l'ultima caricata. Di solito sono "
                           "due referti dello stesso giorno, o lo stesso referto "
                           "caricato due volte con nomi diversi.")
                st.dataframe(pd.DataFrame([dict(d) for d in doppie]),
                             width="stretch", hide_index=True)

        if df.empty:
            st.info("Nessun dato numerico per gli indicatori selezionati.")
        else:
            dmin, dmax = df["data"].min().date(), df["data"].max().date()
            if dmin < dmax:
                da, a = st.slider("Periodo", dmin, dmax, (dmin, dmax), format="MM/YYYY")
                df = df[(df["data"].dt.date >= da) & (df["data"].dt.date <= a)]

            vista = st.radio("Vista", ["Un grafico per indicatore",
                                       "Confronto normalizzato", "Mappa degli stati"],
                             horizontal=True, label_visibility="collapsed")

            if vista == "Un grafico per indicatore":
                colonne = (st.columns(2) if st.checkbox(
                    "Due colonne", len(selezione) > 2) else [st.container()])
                for i, nome_a in enumerate(sorted(df["analita"].unique())):
                    with colonne[i % len(colonne)]:
                        # niente unsafe_allow_html: il nome dell'analita viene
                        # da un PDF, quindi e' dato non fidato
                        st.markdown(f"**{nome_a}** — "
                                    f"[cos'e' questo esame]({riferimenti.scheda(nome_a, alias)})")
                        st.altair_chart(grafici.grafico_analita(df, nome_a),
                                        use_container_width=True)
            elif vista == "Confronto normalizzato":
                st.caption("Ogni valore e' rapportato al proprio intervallo di "
                           "riferimento: dentro la fascia verde significa nella "
                           "norma, fuori significa fuori range, qualunque sia "
                           "l'unita' di misura. Per gli esami con il solo limite "
                           "inferiore (HDL, vitamina D…) l'indice scende quando "
                           "il valore migliora.")
                st.altair_chart(grafici.grafico_comparativo(df), use_container_width=True)
            else:
                st.caption("Una riga per indicatore, una colonna per prelievo.")
                st.altair_chart(grafici.heatmap_stati(df), use_container_width=True)

            st.divider()
            st.markdown("**Variazioni**")
            tabella = grafici.tabella_variazioni(df)
            tabella["Scheda"] = tabella["Analita"].map(
                lambda a: riferimenti.scheda(a, alias))
            st.dataframe(
                tabella, width="stretch", hide_index=True,
                column_config={"Scheda": st.column_config.LinkColumn(
                    "Scheda", display_text="labtestsonline",
                    help="Descrizione dell'esame sul portale SIBioC")})
            c1, c2 = st.columns(2)
            c1.download_button("Scarica la tabella (CSV)",
                               tabella.to_csv(index=False).encode(),
                               "variazioni.csv", "text/csv",
                               icon=":material/download:", width="stretch")
            c2.download_button("Scarica i dati grezzi (CSV)",
                               df.drop(columns=["data"]).to_csv(index=False).encode(),
                               "serie_storiche.csv", "text/csv",
                               icon=":material/download:", width="stretch")

# --- Analisi ---------------------------------------------------------------

with tabs[3]:
    st.subheader("Lettura assistita dei referti")
    st.caption(f"Modello in uso: `{scelti['analisi']}`")
    documenti = core.elenco_documenti(conn)
    tipi_presenti = [t for t in TIPI if any(d["tipo"] == t for d in documenti)]

    AMBITI = ["Tutto l'archivio", "Una tipologia", "Un referto specifico"]
    c1, c2 = st.columns([1, 2])
    ambito = c1.radio("Ambito dell'analisi", AMBITI,
                      disabled=not documenti, label_visibility="collapsed")
    sha_scelto = tipo_scelto_an = None

    if ambito == "Una tipologia" and tipi_presenti:
        tipo_scelto_an = c2.selectbox(
            "Tipologia", tipi_presenti, format_func=etichetta,
            help="Analizza solo i documenti di questo tipo: utile per leggere "
                 "gli esami del sangue senza il rumore degli altri referti.")
    elif ambito == "Un referto specifico" and documenti:
        indice = {f"{d['data_documento'] or 'senza data'} · {etichetta(d['tipo'])}"
                  f" · {d['titolo'] or d['nome_file']}": d["sha256"]
                  for d in documenti}
        sha_scelto = indice[c2.selectbox("Referto", list(indice))]
    elif ambito == "Una tipologia":
        c2.info("Nessun documento con tipologia assegnata.")

    emb_scelto = impostazioni.get("modello.embedding", MODELLO_EMBEDDING)
    brani_txt = ""
    if not sha_scelto and not tipo_scelto_an and semantica.stato(conn, emb_scelto)[0]:
        fuori_norma = core.analiti_fuori_range(conn)
        interrogazione = ("conclusioni diagnostiche reperti rilevanti "
                          + " ".join(fuori_norma[:10]))
        brani_txt = brani_pertinenti(utente_corrente["id"], interrogazione,
                                     emb_scelto, BRANI_NEL_CONTESTO)

    contesto = core.costruisci_contesto(conn, n_referti, brani_txt,
                                        sha=sha_scelto, tipo=tipo_scelto_an)
    if brani_txt:
        st.caption(":material/manage_search: il contesto include i passaggi dei "
                   "referti narrativi piu' pertinenti ai valori alterati, "
                   "al posto delle sintesi generiche.")
    with st.expander(f"Dati che verranno passati al modello "
                     f"(~{core.stima_token(contesto):,} token)".replace(",", "."),
                     icon=":material/data_object:"):
        st.markdown(contesto)

    if st.button("Genera analisi", type="primary", icon=":material/auto_awesome:",
                 disabled=not modelli, key="btn_genera_analisi_819"):
        istruzione = core.PROMPT_ANALISI
        if sha_scelto:
            istruzione = ("Analizza il referto qui sopra. Se ci sono numeri gia' "
                          "calcolati sull'intero archivio, usali per collocare "
                          "questi valori nell'andamento nel tempo.\n\n"
                          + core.PROMPT_ANALISI)
        elif tipo_scelto_an:
            istruzione = (f"Analizza i referti di tipo "
                          f"'{etichetta(tipo_scelto_an)}' qui sopra.\n\n"
                          + core.PROMPT_ANALISI)
        messaggi = [{"role": "system", "content": core.SYSTEM},
                    {"role": "user", "content": f"{contesto}\n\n{istruzione}"}]
        st.session_state["analisi"] = mostra_risposta(
            scelti["analisi"], messaggi, "analisi")

    if st.session_state.get("analisi"):
        st.download_button("Scarica l'analisi (Markdown)", st.session_state["analisi"],
                           "analisi_referti.md", icon=":material/download:")
    st.caption("Strumento di lettura, non di diagnosi: i valori vanno interpretati "
               "dal medico alla luce della storia clinica.")

# --- Chat ------------------------------------------------------------------

with tabs[4]:
    st.subheader("Chat sui propri dati")
    st.caption(f"Modello in uso: `{scelti['chat']}`")

    conversazioni = {f"{c['id']} · {c['titolo']}": c["id"]
                     for c in core.elenco_conversazioni(conn)}
    c1, c2 = st.columns([3, 1])
    scelta = c1.selectbox("Conversazione", ["＋ nuova", *conversazioni])
    conv_id = conversazioni.get(scelta)

    if conv_id is None:
        if c2.button("Crea", icon=":material/add:", width="stretch", key="btn_crea_855"):
            core.crea_conversazione(conn, "Conversazione", scelti["chat"])
            st.rerun()
        st.info("Crea una conversazione per iniziare.")
    else:
        if c2.button("Elimina", icon=":material/delete:", width="stretch", key="btn_elimina_860"):
            core.elimina_conversazione(conn, conv_id)
            st.rerun()

        storico = core.leggi_messaggi(conn, conv_id)
        for m in storico:
            with st.chat_message(m["ruolo"]):
                st.markdown(m["contenuto"])

        if domanda := st.chat_input("Chiedi qualcosa sui tuoi esami…",
                                    disabled=not modelli):
            core.aggiungi_messaggio(conn, conv_id, "user", domanda)
            with st.chat_message("user"):
                st.markdown(domanda)
            emb_chat = impostazioni.get("modello.embedding", MODELLO_EMBEDDING)
            brani_chat = ""
            if semantica.stato(conn, emb_chat)[0]:
                brani_chat = brani_pertinenti(utente_corrente["id"], domanda,
                                              emb_chat, BRANI_NEL_CONTESTO)
            messaggi = [
                {"role": "system",
                 "content": core.SYSTEM + "\n\n"
                 + core.costruisci_contesto(conn, n_referti, brani_chat)},
                *[{"role": m["ruolo"], "content": m["contenuto"]} for m in storico],
                {"role": "user", "content": domanda}]
            if nuovo_tool:
                with st.chat_message("assistant"):
                    with st.status("Interrogo l'archivio…") as stato_tool:
                        try:
                            risposta, tracce = core.chat_con_strumenti(
                                scelti["chat"],
                                [{"role": "system",
                                  "content": messaggi[0]["content"] + "\n\n"
                                  + strumenti.promemoria()}, *messaggi[1:]],
                                "chat", strumenti.DEFINIZIONI,
                                lambda n, a: strumenti.esegui(conn, n, a),
                                avviso=stato_tool.write,
                                max_giri=strumenti.MAX_GIRI)
                            stato_tool.update(
                                label=(f"{len(tracce)} interrogazioni"
                                       if tracce else "Nessuna interrogazione"),
                                state="complete")
                        except core.ErroreOllama as e:
                            stato_tool.update(label="Errore", state="error")
                            st.error(f"{e}\n\nSe il modello non supporta i "
                                     "tool, disattiva gli strumenti dalla barra "
                                     "laterale.")
                            risposta, tracce = "", []
                    if risposta:
                        st.markdown(risposta)
                    if tracce:
                        with st.expander("Dati richiesti dal modello",
                                         icon=":material/function:"):
                            for t in tracce:
                                st.markdown(f"**{t['strumento']}**"
                                            f"`{t['argomenti']}`")
                                st.code(t["risultato"][:1500], language="json")
                if risposta:
                    core.aggiungi_messaggio(conn, conv_id, "assistant", risposta)
            elif risposta := mostra_risposta(scelti["chat"], messaggi, "chat"):
                core.aggiungi_messaggio(conn, conv_id, "assistant", risposta)
            st.rerun()

# --- Secondo parere --------------------------------------------------------

with tabs[5]:
    st.subheader("Secondo parere da un modello esterno")
    st.caption("Prepara un quesito anonimizzato da sottoporre a un modello di "
               "frontiera. Nulla viene inviato da qui: il testo lo copi tu, "
               "dopo averlo letto.")

    if not core.numero_prelievi(conn):
        st.info("Carica almeno un referto.")
    else:
        c1, c2, c3 = st.columns(3)
        quanti = c1.number_input("Referti da includere", 1,
                                 core.numero_prelievi(conn),
                                 min(4, core.numero_prelievi(conn)))
        eta_modo = c2.selectbox("Eta'", ["fascia", "esatta", "omessa"],
                                help="La fascia quinquennale e' clinicamente "
                                     "sufficiente e meno identificante.")
        lingua_p = c3.selectbox("Lingua del quesito", ["it", "en"],
                                format_func=lambda x: "Italiano" if x == "it"
                                else "English")
        c4, c5 = st.columns(2)
        con_bmi = c4.checkbox("Includi il BMI", value=True)
        con_note = c5.checkbox("Includi terapie e note del profilo", value=False,
                               help="Testo libero: e' la parte che piu' "
                                    "facilmente contiene dati identificativi. "
                                    "Rileggila prima di attivarla.")

        quadro = parere.quadro_anonimo(conn, int(quanti), eta=eta_modo,
                                       includi_bmi=con_bmi, includi_note=con_note)

        sintesi = st.session_state.get("sintesi_locale", "")
        c6, c7 = st.columns([1, 2])
        if c6.button("Aggiungi una sintesi locale", icon=":material/auto_awesome:",
                     disabled=not modelli, width="stretch", key="btn_aggiungi_una_sintesi_locale_956"):
            messaggi = [
                {"role": "system", "content": core.SYSTEM},
                {"role": "user", "content": quadro + "\n\nRiassumi in non piu' di "
                 "dieci righe l'esito complessivo e le problematiche riscontrate. "
                 "Solo i fatti che leggi nei dati, nessuna diagnosi."}]
            with st.spinner("Il modello locale sta riassumendo…"):
                try:
                    st.session_state["sintesi_locale"] = "".join(
                        pezzo for tipo, pezzo in
                        core.chat_stream(scelti["analisi"], messaggi, "analisi")
                        if tipo == "testo")
                except core.ErroreOllama as e:
                    st.error(str(e))
            st.rerun()
        c7.caption("Facoltativa. La sintesi viene marcata come prodotta in locale "
                   "e non verificata, cosi' il modello esterno sa di doverla "
                   "controllare invece che darla per buona.")
        if sintesi and c6.button("Rimuovi la sintesi", icon=":material/delete:",
                                 width="stretch", key="btn_rimuovi_la_sintesi_975"):
            st.session_state.pop("sintesi_locale", None)
            st.rerun()

        proposta = parere.componi(quadro, sintesi, lingua_p)

        st.divider()
        st.markdown("**Testo che invieresti** — modificalo liberamente prima di usarlo")
        testo = st.text_area("quesito", proposta, height=420,
                             label_visibility="collapsed", key="quesito_esterno")

        avvisi = parere.verifica(testo, core.leggi_profilo(conn))
        if avvisi:
            for a in avvisi:
                st.error(f":material/privacy_tip: {a}")
        else:
            st.success(":material/verified_user: Nessun dato identificativo "
                       "rilevato dai controlli automatici. Restano controlli "
                       "automatici: la lettura finale spetta a te.")

        st.warning("Da qui in avanti valgono le condizioni del servizio che "
                   "sceglierai, non quelle di AHIA. Quello che invii non torna "
                   "indietro.")
        confermato = st.checkbox("Ho letto il testo qui sopra e confermo di "
                                 "volerlo inviare a un servizio esterno")
        c8, c9 = st.columns(2)
        c8.download_button("Scarica il quesito", testo, "quesito_secondo_parere.md",
                           icon=":material/download:", disabled=not confermato,
                           width="stretch")
        if confermato:
            with c9.popover("Mostra per copiarlo", icon=":material/content_copy:",
                            width="stretch"):
                st.code(testo, language="markdown")
        else:
            c9.button("Mostra per copiarlo", icon=":material/content_copy:",
                      disabled=True, width="stretch", key="btn_mostra_per_copiarlo_1010")

        with st.expander("Cosa viene escluso", icon=":material/shield:"):
            st.markdown(
                "- **Nome o etichetta del profilo**, sempre\n"
                "- **Nome del laboratorio** e nomi dei file, sempre\n"
                "- **Date dei prelievi**: sostituite da intervalli relativi "
                "(T0, +6 mesi…), che conservano l'andamento senza collocarlo "
                "nel tempo\n"
                "- **Altezza e peso**: al loro posto il solo BMI, se lo includi\n"
                "- **Eta' esatta**: per impostazione predefinita solo la fascia\n"
                "- **Terapie e note**: escluse salvo tua scelta esplicita")


# --- Dizionario ------------------------------------------------------------

with tabs[6]:
    st.subheader("Dizionario degli analiti")
    st.caption("Ogni laboratorio scrive gli esami a modo suo: qui le diciture "
               "diverse vengono ricondotte a un nome unico, altrimenti le serie "
               "storiche si spezzano.")

    nomi = [r[0] for r in conn.execute("SELECT DISTINCT nome_referto FROM risultati")]
    aperti = sorted(n for n in nomi if ingest.canonico_di(n, alias) is None)

    if not aperti:
        st.success("Tutte le diciture presenti sono mappate.")
    else:
        st.warning(f"{len(aperti)} diciture non ancora mappate.")
        canonici = sorted(set(alias.values()))

        c1, c2 = st.columns([1, 2])
        if c1.button("Proponi con l'LLM", icon=":material/auto_awesome:",
                     disabled=not modelli, width="stretch", key="btn_proponi_con_l_llm_1043"):
            with st.spinner(f"{scelti['dizionario']} sta analizzando "
                            f"{len(aperti)} diciture…"):
                try:
                    proposte = ingest.proponi_alias(scelti["dizionario"], aperti,
                                                    canonici)
                except core.ErroreOllama as e:
                    st.error(str(e))
                    proposte = {}
                except (ValueError, KeyError) as e:
                    st.error(f"Risposta non interpretabile: {e}")
                    proposte = {}
            if proposte:
                # i widget con key ignorano il parametro value dopo il primo run:
                # la proposta va scritta direttamente nello stato
                for dicitura, dati in proposte.items():
                    st.session_state[f"al_{dicitura}"] = dati["canonico"]
                st.session_state["note_alias"] = {
                    d: v for d, v in proposte.items()}
                st.rerun()
        c2.caption("Il modello propone, tu confermi: il dizionario salvato resta "
                   "l'unica cosa che viene applicata ai dati.")

        note = st.session_state.get("note_alias", {})
        with st.form("alias"):
            scelte = {}
            for n in aperti:
                c1, c2 = st.columns([2, 3])
                c1.markdown(f"`{n}`")
                scelte[n] = c2.text_input("canonico", n.upper(), key=f"al_{n}",
                                          label_visibility="collapsed")
                if info := note.get(n):
                    origine = ("riconosciuto tra i canonici esistenti"
                               if info["esistente"] else "nuovo nome proposto")
                    c2.caption(f":material/auto_awesome: {origine}"
                               + (f" — {info['nota']}" if info["nota"] else ""))
            if st.form_submit_button("Salva e riapplica", type="primary",
                                     icon=":material/sync:"):
                personale = (json.loads(archivio.alias.read_text(encoding="utf-8"))
                             if archivio.alias.exists() else {})
                personale.update({ingest.slug(n): c.strip().upper()
                                  for n, c in scelte.items() if c.strip()})
                archivio.alias.write_text(json.dumps(personale, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
                st.session_state.pop("note_alias", None)
                n_agg = riapplica_alias(ingest.carica_alias(archivio.alias))
                st.success(f"Dizionario aggiornato, {n_agg} righe riallineate.")
                st.rerun()
        st.caption("Nomi canonici gia' in uso: "
                   + ", ".join(sorted(set(alias.values()))[:40]))

    with st.expander("Cosa misura ciascun esame", icon=":material/help:"):
        st.caption("Collegamenti alle schede di labtestsonline.it, il portale "
                   "divulgativo di SIBioC (Societa' Italiana di Biochimica "
                   "Clinica). I contenuti restano sul loro sito: qui ci sono "
                   "solo i collegamenti. Per gli esami senza una scheda "
                   "corrispondente il collegamento apre una ricerca ristretta "
                   "a quel sito: viene inviato il nome dell'esame, nessun "
                   "valore.")
        presenti = core.elenco_analiti(conn) or sorted(set(alias.values()))
        st.dataframe(
            pd.DataFrame([{"Analita": a, "Scheda": riferimenti.scheda(a, alias)}
                          for a in presenti]),
            width="stretch", hide_index=True,
            column_config={"Scheda": st.column_config.LinkColumn(
                "Scheda", display_text="apri")})

    st.divider()
    st.subheader("Catalogo degli intervalli di riferimento")
    st.caption("Molti referti non riportano l'intervallo per ogni esame. Il "
               "catalogo lo completa dove manca, con valori indicativi per "
               "adulti. Gli intervalli stampati sul referto non vengono mai "
               "toccati.")

    attivo = impostazioni.get("catalogo.attivo", "0") == "1"
    profilo = core.leggi_profilo(conn)
    sesso_profilo = profilo.get("sesso") or ""
    senza_riferimento = conn.execute(
        "SELECT COUNT(*) FROM risultati WHERE valore IS NOT NULL "
        "AND range_min IS NULL AND range_max IS NULL").fetchone()[0]
    dal_catalogo = conn.execute(
        "SELECT COUNT(*) FROM risultati WHERE origine_range='catalogo'").fetchone()[0]

    c1, c2 = st.columns([1, 2])
    nuovo_attivo = c1.toggle("Completa gli intervalli mancanti", attivo)
    if nuovo_attivo != attivo:
        core.salva_impostazione(conn, "catalogo.attivo", "1" if nuovo_attivo else "0")
        if nuovo_attivo:
            n = core.applica_catalogo(conn, sesso_profilo, archivio.riferimenti)
            st.success(f"{n} valori completati dal catalogo.")
        else:
            n = core.svuota_catalogo(conn)
            st.info(f"{n} intervalli del catalogo rimossi.")
        st.rerun()

    if not sesso_profilo:
        c2.warning("Sesso non indicato nel profilo: vengono usati gli intervalli "
                   "maschili. Per ferritina, emoglobina, creatinina e altri la "
                   "differenza e' rilevante.")
    else:
        c2.caption(f"Intervalli per: {'uomini' if sesso_profilo == 'M' else 'donne'} "
                   f"· {dal_catalogo} valori completati · {senza_riferimento} "
                   "ancora senza intervallo")

    st.warning("Sono valori indicativi per adulti, non specifici del metodo del "
               "tuo laboratorio. Non valgono per eta' pediatrica, gravidanza o "
               "condizioni particolari, e alcune voci sono soglie decisionali "
               "(colesterolo, vitamina D) piuttosto che intervalli di "
               "riferimento. Nei grafici la banda dal catalogo e' blu invece "
               "che verde, e nelle tabelle e' segnata con un asterisco.")

    with st.expander("Voci del catalogo", icon=":material/list:"):
        st.dataframe(pd.DataFrame(riferimenti.elenco(archivio.riferimenti)),
                     width="stretch",
                     hide_index=True)
        st.caption(f"Per aggiungere o correggere una voce, crea il file "
                   f"`{archivio.riferimenti}` con la stessa struttura: "
                   '`{"ANALITA": {"unita": "mg/dL", "M": [min, max], '
                   '"F": [min, max], "nota": ""}}` — usa `null` per un estremo '
                   "aperto.")


# --- Utenti (solo amministratore) ------------------------------------------

if e_admin:
    with tabs[7]:
        st.subheader("Gestione utenti")
        st.caption("Chi ha un'utenza abilitata vede l'intero archivio: "
                   "l'autenticazione decide chi entra, non separa i dati.")

        righe = utenti.elenco(auth)
        st.dataframe(
            pd.DataFrame([{
                "Utente": u["nome_utente"],
                "Ruolo": "amministratore" if u["ruolo"] == "admin" else "utente",
                "Stato": "attivo" if u["attivo"] else "bloccato",
                "Creato": (u["creato_il"] or "")[:10],
                "Ultimo accesso": (u["ultimo_accesso"] or "mai")[:16],
                "Tentativi falliti": u["tentativi_falliti"],
            } for u in righe]), width="stretch", hide_index=True)

        st.divider()
        with st.expander("Nuovo utente", icon=":material/person_add:"):
            if "pw_suggerita" not in st.session_state:
                st.session_state["pw_suggerita"] = utenti.password_suggerita()
            with st.form("nuovo_utente"):
                c1, c2 = st.columns(2)
                nuovo_nome = c1.text_input("Nome utente")
                nuovo_ruolo = c2.selectbox("Ruolo", ["utente", "admin"],
                                           format_func=lambda r: "amministratore"
                                           if r == "admin" else "utente")
                nuova_pw = st.text_input("Password iniziale",
                                         st.session_state["pw_suggerita"],
                                         help="Verra' chiesto di cambiarla al "
                                              "primo accesso.")
                if st.form_submit_button("Crea", type="primary",
                                         icon=":material/person_add:"):
                    if errore := utenti.crea(auth, nuovo_nome, nuova_pw,
                                             nuovo_ruolo):
                        st.error(errore)
                    else:
                        st.success(f"Utente «{nuovo_nome}» creato. Comunicagli "
                                   f"la password: `{nuova_pw}` — non sara' piu' "
                                   "visibile.")
                        st.session_state["pw_suggerita"] = utenti.password_suggerita()

        st.divider()
        st.markdown("**Modifica un utente**")
        indice = {f"{u['nome_utente']} ({'amministratore' if u['ruolo'] == 'admin' else 'utente'})":
                  u for u in righe}
        scelto = indice[st.selectbox("Utente", list(indice))]
        proprio = scelto["id"] == utente_corrente["id"]
        if proprio:
            st.caption("Stai modificando la tua utenza.")

        c1, c2, c3, c4 = st.columns(4)
        if scelto["attivo"]:
            if c1.button("Blocca", icon=":material/block:", width="stretch",
                         disabled=proprio, key="btn_blocca_1218"):
                if errore := utenti.imposta_stato(auth, scelto["id"], False):
                    st.error(errore)
                else:
                    st.rerun()
        elif c1.button("Riabilita", icon=":material/check:", width="stretch", key="btn_riabilita_1224"):
            if errore := utenti.imposta_stato(auth, scelto["id"], True):
                st.error(errore)
            else:
                st.rerun()

        altro_ruolo = "utente" if scelto["ruolo"] == "admin" else "admin"
        if c2.button(f"Rendi {'utente' if altro_ruolo == 'utente' else 'admin'}",
                     icon=":material/swap_horiz:", width="stretch",
                     disabled=proprio, key="btn_rendi_1231"):
            if errore := utenti.cambia_ruolo(auth, scelto["id"], altro_ruolo):
                st.error(errore)
            else:
                st.rerun()

        if c3.button("Reimposta password", icon=":material/key:", width="stretch", key="btn_reimposta_password_1239"):
            nuova = utenti.password_suggerita()
            if errore := utenti.cambia_password(auth, scelto["id"], nuova, True):
                st.error(errore)
            else:
                st.warning(f"Nuova password di «{scelto['nome_utente']}»: "
                           f"`{nuova}` — dovra' cambiarla al primo accesso.")

        if c4.button("Elimina", icon=":material/delete:", width="stretch",
                     disabled=proprio, type="secondary", key="btn_elimina_1247"):
            st.session_state["conferma_elimina"] = scelto["id"]

        if st.session_state.get("conferma_elimina") == scelto["id"]:
            st.error(f"Eliminare definitivamente «{scelto['nome_utente']}»?")
            anche_dati = st.checkbox(
                "Elimina anche il suo archivio sanitario (referti, profilo, "
                "conversazioni). Irreversibile.")
            c1, c2 = st.columns(2)
            if c1.button("Sì, elimina", type="primary", icon=":material/delete:", key="btn_si_elimina_1257"):
                errore = utenti.elimina(auth, scelto["id"])
                if not errore and anche_dati:
                    utenti.elimina_archivio(scelto["id"])
                st.session_state.pop("conferma_elimina", None)
                if errore:
                    st.error(errore)
                else:
                    st.rerun()
            if c2.button("Annulla", key="btn_annulla_1266"):
                st.session_state.pop("conferma_elimina", None)
                st.rerun()

        st.divider()
        with st.expander("Cambia la tua password", icon=":material/lock_reset:"):
            with st.form("cambio_mia_pw"):
                attuale = st.text_input("Password attuale", type="password")
                n1 = st.text_input("Nuova password", type="password")
                n2 = st.text_input("Ripeti", type="password")
                if st.form_submit_button("Aggiorna", type="primary"):
                    verificato, _ = utenti.verifica(
                        auth, utente_corrente["nome_utente"], attuale)
                    if not verificato:
                        st.error("Password attuale errata.")
                    elif n1 != n2:
                        st.error("Le due password non coincidono.")
                    elif errore := utenti.cambia_password(auth,
                                                          utente_corrente["id"], n1):
                        st.error(errore)
                    else:
                        st.success("Password aggiornata.")
