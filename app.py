"""AHIA — archivio, andamenti e lettura assistita dei referti, tutto offline.

Avvio:  streamlit run app.py
"""

# AHIA — archivio e lettura dei referti medici, in locale.
# Copyright (C) 2026  vonausterliz
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

import datetime as dt
import json
import time

import pandas as pd
import streamlit as st

import config
import configurazione_modelli
import ui_impostazioni
import ui_diagnostica
import ui_modelli_locali
import ui_navigazione
import core
import grafici
import ingest
import parere
import presidio_ahia
import pseudonimizzazione as pseudo
import regole_pii
import riferimenti
import semantica
import segreti
import strumenti
import utenti
from config import (BRANI_NEL_CONTESTO, DISCLAIMER, DISCLAIMER_VERSIONE,
                    TIPI, e_tabellare,
                    etichetta)

st.set_page_config(page_title="AHIA — referti e andamenti",
                   page_icon=":material/monitor_heart:", layout="wide")

st.markdown("""<style>
/* --- AHIA, foglio di stile: sobrio, leggibile, da strumento clinico --- */

/* Larghezza di lettura contenuta: il testo non si stira su schermi larghi */
.block-container { max-width: 1180px; padding-top: 2.4rem; padding-bottom: 4rem; }

/* Titoli piu' ariosi e con meno peso, per un tono calmo */
h1, h2, h3 { letter-spacing: -0.01em; font-weight: 650; }
h2 { margin-top: 0.6rem; padding-bottom: 0.3rem;
     border-bottom: 1px solid rgba(47,109,106,0.14); }
h3 { color: #2f6d6a; }

/* Schede: piu' spazio, sottolineatura netta su quella attiva */
.stTabs [data-baseweb="tab-list"] { gap: 0.4rem; }
.stTabs [data-baseweb="tab"] {
    padding: 0.5rem 0.9rem; border-radius: 8px 8px 0 0; }
.stTabs [aria-selected="true"] {
    background: rgba(47,109,106,0.08);
    border-bottom: 2px solid #2f6d6a; }

/* Pulsanti: angoli morbidi, transizione discreta */
.stButton button, .stDownloadButton button {
    border-radius: 8px; font-weight: 550; transition: all 0.15s ease; }
.stButton button:hover { transform: translateY(-1px); }

/* Riquadri e contenitori con bordo piu' leggero */
[data-testid="stExpander"], div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 10px; }

/* Tabelle: intestazione in tinta, righe piu' respirate */
[data-testid="stDataFrame"] thead tr th {
    background: #eef4f4 !important; font-weight: 600; }

/* Metriche: numero grande in tinta guida */
[data-testid="stMetricValue"] { color: #2f6d6a; font-weight: 680; }

/* Barra laterale: separazione morbida dal contenuto */
section[data-testid="stSidebar"] {
    background: #f4f8f8; border-right: 1px solid rgba(47,109,106,0.10); }
section[data-testid="stSidebar"] h1 {
    font-size: 2.6rem; font-weight: 700; letter-spacing: 0.04em;
    color: #2f6d6a; padding-bottom: 0.1rem; }
section[data-testid="stSidebar"] h1 span[data-testid="stIconMaterial"] {
    font-size: 2.2rem; vertical-align: -3px; }

/* Logo di prodotto: più presente in testa al menu, compatto a sidebar chiusa */
section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {
    min-height: 4.7rem; align-items: flex-start; }
section[data-testid="stSidebar"] img.stLogo {
    height: 52px !important; max-height: 52px !important;
    width: auto !important; max-width: 100% !important; }

/* Avvisi piu' morbidi, meno "allarme" visivo */
[data-testid="stAlert"] { border-radius: 9px; }
</style>""", unsafe_allow_html=True)


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


def _pannello_diagnosi(conn, archivio, doc, modelli, alias):
    """Diagnosi e recupero di un'estrazione, con l'utente che decide se applicare."""
    sha = doc["sha256"]
    with st.container(border=True):
        testo = core.leggi_testo(conn, sha)
        if not testo.strip():
            st.warning("Di questo referto non è stato conservato il testo grezzo "
                       "(caricato con una versione precedente, o scansione). "
                       "La diagnosi lavora sul testo: ricaricalo per usarla.")
            if st.button("Chiudi", key=f"chiudi_diag_notesto_{sha}"):
                st.session_state.pop("diagnostica_sha", None)
                st.rerun()
            return

        attuali = [dict(r) for r in conn.execute(
            "SELECT nome_referto, valore_testo AS valore, unita, range_min, "
            "range_max FROM risultati WHERE sha256 = ?", (sha,)).fetchall()]
        lab = doc["struttura"] or ""

        chiave_esiti = f"esiti_diag_{sha}"
        if chiave_esiti not in st.session_state:
            righe_log = []
            with st.status("Analisi in corso…", expanded=True) as stato:
                try:
                    esiti = ingest.recupera_estrazione(
                        conn, sha, testo, attuali, lab, modelli,
                        progress=lambda m: (righe_log.append(m), stato.write(m)))
                    st.session_state[chiave_esiti] = esiti
                    stato.update(label="Analisi completata", state="complete")
                except core.ErroreOllama as e:
                    stato.update(label="Errore", state="error")
                    st.error(str(e))
                    if st.button("Chiudi", key=f"chiudi_err_{sha}"):
                        st.session_state.pop("diagnostica_sha", None)
                        st.rerun()
                    return

        esiti = st.session_state.get(chiave_esiti)
        if not esiti:
            return

        st.markdown(f"**Problema rilevato** — {esiti['diagnosi'].get('problema', 'n/d')}")
        if esiti["istruzione"]:
            st.caption(f"Istruzione per questo layout: {esiti['istruzione']}")

        if esiti["fase"] in ("nessun cambiamento",):
            st.info("L'estrazione attuale sembra già la migliore possibile: "
                    "non è stata cambiata.")
        else:
            st.success(f"Proposta una nuova estrazione ({esiti['fase']}): "
                       f"da {len(attuali)} a {len(esiti['esami'])} valori.")
            col_a, col_b = st.columns(2)
            with col_a:
                st.caption("**Attuale**")
                st.dataframe(pd.DataFrame(attuali)[["nome_referto", "valore", "unita"]],
                             hide_index=True, height=200)
            with col_b:
                st.caption("**Proposta**")
                st.dataframe(pd.DataFrame(esiti["esami"])[
                    [c for c in ("nome_referto", "valore", "unita")
                     if c in (esiti["esami"][0] if esiti["esami"] else {})]],
                    hide_index=True, height=200)

        c1, c2, c3 = st.columns(3)
        applicabile = esiti["fase"] not in ("nessun cambiamento",)
        if c1.button("Applica la nuova estrazione", type="primary",
                     icon=":material/check:", disabled=not applicabile,
                     key=f"applica_diag_{sha}", width="stretch"):
            righe = [r for e in esiti["esami"]
                     if (r := ingest.normalizza(e, alias, set()))]
            core.sostituisci_valori(conn, sha, righe)
            if esiti["istruzione"]:
                core.salva_istruzione_layout(conn, lab,
                                             esiti["diagnosi"].get("problema", ""),
                                             esiti["istruzione"])
            st.session_state.pop("diagnostica_sha", None)
            st.session_state.pop(chiave_esiti, None)
            st.success("Estrazione aggiornata.")
            st.rerun()

        if esiti["istruzione"] and c2.button(
                "Salva solo l'istruzione", icon=":material/bookmark:",
                key=f"salva_istr_{sha}", width="stretch",
                help="Conserva l'istruzione per i prossimi referti di questo "
                     "laboratorio, senza toccare i valori attuali."):
            core.salva_istruzione_layout(conn, lab,
                                         esiti["diagnosi"].get("problema", ""),
                                         esiti["istruzione"])
            st.session_state.pop("diagnostica_sha", None)
            st.session_state.pop(chiave_esiti, None)
            st.rerun()

        if c3.button("Chiudi senza applicare", key=f"chiudi_diag_{sha}",
                     width="stretch"):
            st.session_state.pop("diagnostica_sha", None)
            st.session_state.pop(chiave_esiti, None)
            st.rerun()


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


def _dimentica_secondo_parere(*, includi_widget_pii: bool = True) -> None:
    """Elimina mappa, payload e risposta dalla sessione corrente."""
    sessione = st.session_state.get("parere_sessione_pseudo")
    if isinstance(sessione, pseudo.SessionePseudonimi):
        sessione.dimentica()
    chiavi = {
        "quesito_base", "quesito_origine_pseudo", "quesito_esterno",
        "quesito_esterno_prossimo",
        "parere_sessione_pseudo", "parere_stato_presidio",
        "parere_avvisi_pseudo", "parere_hash_visto",
        "parere_hash_confermato", "conferma_parere_payload",
        "parere_risposta", "parere_risposta_pseudonima",
        "parere_avvisi_risposta", "risposta_manual_pseudo",
    }
    if includi_widget_pii:
        chiavi.update(k for k in st.session_state if k.startswith("pii_"))
    for chiave in chiavi:
        st.session_state.pop(chiave, None)


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
                _dimentica_secondo_parere()
                st.session_state["utente"] = utente
                # serve per cifrare/decifrare le chiavi API; resta solo in
                # sessione, in memoria, non viene mai persistita
                st.session_state["chiave_sessione"] = password
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
                st.session_state["chiave_sessione"] = pw1
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
segreti.prepara(conn)  # crea la tabella se manca (archivi anteriori alla 1.6.0)
alias = ingest.carica_alias(archivio.alias)

CHIAVE_DISCLAIMER = "disclaimer.versione_accettata"
CHIAVE_DISCLAIMER_QUANDO = "disclaimer.accettato_il"


@st.dialog("Prima di usare AHIA — Before using AHIA", width="large")
def avvertenza(bloccante: bool = True):
    lingua = st.segmented_control("Lingua", ["Italiano", "English"],
                                  default="Italiano", label_visibility="collapsed")
    st.markdown(DISCLAIMER["en" if lingua == "English" else "it"])
    if not bloccante:
        quando = core.leggi_impostazioni(conn).get(CHIAVE_DISCLAIMER_QUANDO)
        versione = core.leggi_impostazioni(conn).get(CHIAVE_DISCLAIMER)
        if quando:
            istante = quando.replace("T", " alle ")
            st.caption(f":material/history: Avvertenza (versione {versione}) "
                       f"accettata il {istante}.")
        return
    letto = st.checkbox("Ho letto e compreso quanto sopra / "
                        "I have read and understood the above")
    if st.button("Accetto e prosegui / Accept and continue", type="primary",
                 icon=":material/check:", disabled=not letto, key="btn_accetto_e_prosegui_accept_and_cont_182"):
        core.salva_impostazione(conn, CHIAVE_DISCLAIMER, DISCLAIMER_VERSIONE)
        core.salva_impostazione(conn, CHIAVE_DISCLAIMER_QUANDO,
                                dt.datetime.now().isoformat(timespec="seconds"))
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
    import time as _time
    import json as _json
    avvio = _time.monotonic()
    metriche = {}
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
                elif tipo == "metriche":
                    metriche = _json.loads(pezzo)
                else:
                    if not testo:
                        stato.update(label="Ragionamento concluso", state="complete")
                    testo += pezzo
                    segnaposto.markdown(testo)
        except core.ErroreOllama as e:
            stato.update(label="Errore", state="error")
            st.error(str(e))
            core.registra_evento(conn, "errore", categoria=funzione,
                                  esito="errore", modello=model,
                                  durata_s=round(_time.monotonic() - avvio, 1),
                                  dettaglio=str(e))
            return ""
        if not testo:
            stato.update(label="Nessuna risposta", state="error")
            st.warning("Il modello non ha prodotto testo. Se e' un modello con "
                       "ragionamento, potrebbe aver esaurito il contesto: riduci "
                       "i referti nel contesto o disattiva `think` in config.py.")
        else:
            stato.update(label="Completato", state="complete")
        core.registra_evento(
            conn, "modello", categoria=funzione,
            esito="ok" if testo else "vuoto", modello=model,
            durata_s=metriche.get("durata_s")
            or round(_time.monotonic() - avvio, 1),
            token_in=metriche.get("token_in"),
            token_out=metriche.get("token_out"))
        return testo


# --- Navigazione e stato compatto ------------------------------------------

def _esci_dalla_sessione():
    _dimentica_secondo_parere()
    st.session_state.pop("utente", None)
    st.session_state.pop("chiave_sessione", None)
    st.rerun()


pagina, impostazioni, scelti, emb, nuovo_tool, n_referti, modelli = ui_navigazione.costruisci(
    conn, utente_corrente, e_admin,
    esci=_esci_dalla_sessione,
    mostra_avvertenza=lambda: avvertenza(bloccante=False),
)

# Il pull continua in background ed è visibile in ogni sezione.
with st.sidebar:
    ui_modelli_locali.mostra_stato_download()


if pagina == "home":
    documenti = core.elenco_documenti(conn)
    n_documenti = len(documenti)

    if not documenti:
        st.title("Inizia dal tuo primo referto")
        st.write(
            "Carica un PDF: AHIA ne estrae i valori, te li fa controllare e "
            "costruisce nel tempo uno storico consultabile."
        )
        if st.button(
            "Carica un referto", type="primary",
            icon=":material/upload_file:", key="home_primo_referto",
        ):
            st.switch_page(ui_navigazione.PAGINA_REFERTI)
        st.caption(
            ":material/lock: Il documento e i dati estratti restano su questo computer."
        )
    else:
        st.title("Il tuo archivio")
        n_prelievi = core.numero_prelievi(conn)
        c1, c2 = st.columns(2)
        c1.metric("Referti", n_documenti)
        c2.metric("Prelievi", n_prelievi)

        azioni = st.columns(3)
        if azioni[0].button(
            "Carica un referto", icon=":material/upload_file:",
            width="stretch", key="home_carica_referto",
        ):
            st.switch_page(ui_navigazione.PAGINA_REFERTI)
        if azioni[1].button(
            "Esplora gli andamenti", icon=":material/trending_up:",
            width="stretch", key="home_andamenti",
        ):
            st.switch_page(ui_navigazione.PAGINA_ANDAMENTI)
        if azioni[2].button(
            "Apri l’assistente", icon=":material/assistant:",
            width="stretch", key="home_assistente",
        ):
            st.switch_page(ui_navigazione.PAGINA_ASSISTENTE)

        st.markdown("### Referti recenti")
        st.dataframe(pd.DataFrame([{
            "Data": r["data_documento"] or "",
            "Tipo": etichetta(r["tipo"]),
            "Titolo": r["titolo"] or r["nome_file"],
        } for r in documenti[:5]]), hide_index=True, width="stretch")


# --- Profilo ---------------------------------------------------------------

if pagina == "profilo":
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

if pagina == "referti":
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

    analisi_auto = st.checkbox(
        "Analizza la struttura dei laboratori nuovi",
        value=st.session_state.get("analisi_auto", config.ANALISI_STRUTTURA_AUTO),
        key="analisi_auto",
        help="Sul primo referto di un laboratorio mai visto, il modello "
             "studia il layout e prepara una scheda di lettura, riusata "
             "sui referti successivi dello stesso laboratorio. Il primo referto "
             "di ogni laboratorio viene quindi estratto due volte (una per "
             "capire il laboratorio, una con la scheda) ed è più lento; i "
             "successivi partono già con la scheda, in una sola estrazione. "
             "Disattivala per estrarre sempre una volta sola, senza schede.")

    if caricati and st.button("Elabora", type="primary",
                              icon=":material/play_arrow:", key="btn_elabora_442"):
        # verifica a monte che i modelli scelti siano installati: meglio dirlo
        # subito che scoprirlo dopo minuti di attesa a metà elaborazione
        richiesti = dict(scelti)
        if analisi_auto:
            richiesti["analisi_struttura"] = scelti.get("analisi_struttura", "")
        mancanti = core.modelli_mancanti(richiesti)
        if mancanti:
            st.error("Modelli non installati: " + ", ".join(f"`{m}`" for m in mancanti)
                     + ". Scaricali con `ollama pull <nome>` oppure scegline "
                     "altri nella barra laterale, poi riprova.")
            st.stop()
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
                    # Se il laboratorio è già noto, la sua scheda viene applicata
                    # subito nell'unica estrazione (callback qui sotto). Se è nuovo
                    # e l'analisi struttura è attiva, la scheda si crea dopo e si
                    # ri-estrae una volta per applicarla.
                    doc = ingest.elabora_documento(
                        percorso, scelti, tipo_scelto, progress=annota,
                        scheda_per_lab=lambda lab: core.istruzione_layout_per(
                            conn, lab))
                    lab = doc.get("struttura", "")

                    gia_nota = bool(lab and core.istruzione_layout_per(conn, lab))
                    if (not gia_nota and analisi_auto and lab
                            and e_tabellare(doc.get("tipo", ""))
                            and doc.get("testo", "").strip()):
                        annota(f"Laboratorio «{lab}» mai visto: "
                               f"{scelti['analisi_struttura']} ne studia la "
                               "struttura…")
                        scheda = ingest.analizza_struttura(
                            scelti["analisi_struttura"], doc["testo"])
                        if scheda:
                            core.salva_istruzione_layout(
                                conn, lab, "Scheda di lettura iniziale del layout",
                                scheda)
                            annota("Scheda pronta: verifico se migliora "
                                   "l'estrazione.")
                            doc = ingest.riestrai_se_migliora(
                                percorso, doc, scheda, scelti, progress=annota)

                    st.session_state["log"] += [{"file": up.name, **r}
                                                for r in doc["log"]]
                except core.ErroreOllama as e:
                    annota(f"**Errore:** {e}")
                    riquadro.update(label=f"{up.name} — errore Ollama",
                                    state="error")
                    core.registra_evento(conn, "errore", categoria="estrazione",
                                          esito="errore", dettaglio=str(e))
                    doc = None
                except Exception as e:  # JSON malformato, PDF illeggibile
                    annota(f"**Errore:** {type(e).__name__}: {e}")
                    riquadro.update(label=f"{up.name} — elaborazione fallita",
                                    state="error")
                    core.registra_evento(
                        conn, "errore", categoria="estrazione", esito="errore",
                        dettaglio=f"{type(e).__name__}: {e}")
                    doc = None

                if doc:
                    log_doc = doc.get("log", [])
                    tok_in = sum(m.get("token_in", 0) or 0 for m in log_doc)
                    tok_out = sum(m.get("token_out", 0) or 0 for m in log_doc)
                    dur = sum(m.get("totale_s", 0) or 0 for m in log_doc)
                    core.registra_evento(
                        conn, "operazione", categoria="estrazione", esito="ok",
                        modello=scelti.get("estrazione", ""),
                        durata_s=round(dur, 1) if dur else None,
                        token_in=tok_in or None, token_out=tok_out or None)
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
                                        emb)
            except core.ErroreOllama as e:
                st.error(str(e))
                brani = []
            if not brani:
                st.info("Nessun risultato: forse l'indice semantico non e' ancora "
                        "stato costruito in Impostazioni → Modelli e provider.")
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
                    c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
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
                    if c3.button("Ri-estrai", key=f"rex_{d['sha256']}",
                                 icon=":material/refresh:", width="stretch",
                                 help="Rielabora il referto dal PDF originale con "
                                      "i modelli attuali, utile se l'estrazione è "
                                      "migliorata da quando fu caricato."):
                        mancanti = core.modelli_mancanti(scelti)
                        if mancanti:
                            st.error("Modelli non installati: "
                                     + ", ".join(f"`{m}`" for m in mancanti))
                        else:
                            with st.status("Rielaborazione…", expanded=True) as st_:
                                try:
                                    ingest.riestrai_referto(
                                        conn, d["sha256"], archivio, scelti,
                                        progress=st.write)
                                    st_.update(label="Rielaborato",
                                               state="complete")
                                    st.rerun()
                                except FileNotFoundError as e:
                                    st_.update(label="PDF non disponibile",
                                               state="error")
                                    st.error(str(e))
                    if c4.button("Elimina", key=f"del_{d['sha256']}",
                                 icon=":material/delete:", width="stretch"):
                        core.elimina_referto(conn, d["sha256"])
                        st.rerun()

                    if d["sintesi"]:
                        with st.container(border=True):
                            st.write(d["sintesi"])
                            if d["conclusioni"]:
                                st.markdown(f"**Conclusioni:** {d['conclusioni']}")

                    # segnalazione automatica e recupero dell'estrazione
                    if e_tabellare(d["tipo"]):
                        sospetti = core.estrazione_sospetta(conn, d["sha256"])
                        if sospetti:
                            with st.container(border=True):
                                st.caption(":material/warning: Questa estrazione "
                                           "potrebbe avere problemi:")
                                for indizio in sospetti:
                                    st.caption(f"• {indizio}")
                        if st.button("Diagnostica e correggi l'estrazione",
                                     icon=":material/healing:",
                                     key=f"diag_{d['sha256']}",
                                     disabled=not modelli,
                                     help="Il modello più capace analizza perché "
                                          "l'estrazione è venuta male, riprova con "
                                          "le istruzioni che scopre e, se serve, "
                                          "rifà lui l'estrazione. Tutto in locale."):
                            st.session_state["diagnostica_sha"] = d["sha256"]

                    if st.session_state.get("diagnostica_sha") == d["sha256"]:
                        _pannello_diagnosi(conn, archivio, d, scelti, alias)

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


# --- Andamenti -------------------------------------------------------------

if pagina == "andamenti":
    st.subheader("Andamento analiti")
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
                                        width="stretch")
            elif vista == "Confronto normalizzato":
                st.caption("Ogni valore e' rapportato al proprio intervallo di "
                           "riferimento: dentro la fascia verde significa nella "
                           "norma, fuori significa fuori range, qualunque sia "
                           "l'unita' di misura. Per gli esami con il solo limite "
                           "inferiore (HDL, vitamina D…) l'indice scende quando "
                           "il valore migliora.")
                st.altair_chart(grafici.grafico_comparativo(df), width="stretch")
            else:
                st.caption("Una riga per indicatore, una colonna per prelievo.")
                st.altair_chart(grafici.heatmap_stati(df), width="stretch")

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

# --- Assistente -------------------------------------------------------------

if pagina == "assistente":
    st.subheader("Assistente sui tuoi dati")
    vista_assistente = st.segmented_control(
        "Modalità", ["Lettura guidata", "Conversazioni"],
        default="Lettura guidata", label_visibility="collapsed")
    with st.popover("Contesto e strumenti", icon=":material/tune:"):
        disponibili_contesto = max(core.numero_prelievi(conn), 1)
        nuovo_n = st.slider(
            "Referti nel contesto", 1, max(disponibili_contesto, n_referti),
            min(n_referti, max(disponibili_contesto, n_referti)))
        if nuovo_n != n_referti:
            core.salva_impostazione(conn, "contesto.n_referti", str(nuovo_n))
            st.rerun()
        strumenti_scelti = st.toggle(
            "Strumenti nelle conversazioni", value=nuovo_tool,
            help="Permette al modello di interrogare serie, conteggi e referti.")
        if strumenti_scelti != nuovo_tool:
            core.salva_impostazione(
                conn, "chat.strumenti", "1" if strumenti_scelti else "0")
            st.rerun()
        token_contesto = core.stima_token(core.costruisci_contesto(conn, n_referti))
        st.caption(f"Contesto stimato: {token_contesto:,} token".replace(",", "."))
        ctx_min = min(config.FUNZIONI[f]["num_ctx"] for f in ("analisi", "chat"))
        if token_contesto / ctx_min > 0.6:
            st.warning(
                f"Il contesto usa circa {token_contesto / ctx_min:.0%} della finestra: "
                "riduci i referti per evitare troncamenti.")

# --- Analisi ---------------------------------------------------------------

if pagina == "assistente" and vista_assistente == "Lettura guidata":
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

    emb_scelto = emb
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

    cerca_incoerenze = st.toggle(
        "Segnala possibili errori di lettura",
        value=st.session_state.get("cerca_incoerenze", False),
        key="cerca_incoerenze",
        help="Il modello aggiunge una sezione con i valori che sospetta mal "
             "estratti dal PDF (per incoerenza, non per il solo essere fuori "
             "norma), ciascuno con un pulsante per verificarlo sull'originale. "
             "Allunga un po' l'analisi.")

    if st.button("Genera analisi", type="primary", icon=":material/auto_awesome:",
                 disabled=not modelli, key="btn_genera_analisi_819"):
        coda = core.PROMPT_INCOERENZE if cerca_incoerenze else ""
        istruzione = core.PROMPT_ANALISI + coda
        if sha_scelto:
            istruzione = ("Analizza il referto qui sopra. Se ci sono numeri gia' "
                          "calcolati sull'intero archivio, usali per collocare "
                          "questi valori nell'andamento nel tempo.\n\n"
                          + core.PROMPT_ANALISI + coda)
        elif tipo_scelto_an:
            istruzione = (f"Analizza i referti di tipo "
                          f"'{etichetta(tipo_scelto_an)}' qui sopra.\n\n"
                          + core.PROMPT_ANALISI + coda)
        messaggi = [{"role": "system", "content": core.SYSTEM},
                    {"role": "user", "content": f"{contesto}\n\n{istruzione}"}]
        st.session_state["analisi"] = mostra_risposta(
            scelti["analisi"], messaggi, "analisi")

    if st.session_state.get("analisi"):
        st.download_button("Scarica l'analisi (Markdown)", st.session_state["analisi"],
                           "analisi_referti.md", icon=":material/download:")

        # il modello puo' aver segnalato valori sospetti di cattiva estrazione:
        # ognuno diventa una verifica sul testo grezzo del referto che lo contiene
        sospetti = core.sospetti_da_analisi(st.session_state["analisi"])
        if sospetti:
            st.divider()
            st.markdown("##### :material/rule: Valori da verificare")
            st.caption("L'analisi ha notato incoerenze che potrebbero essere "
                       "errori di lettura del PDF, non valori reali. Verifica "
                       "controlla il testo originale del referto.")
            for i, sos in enumerate(sospetti):
                riga = core.referto_con_analita(conn, sos["analita"])
                with st.container(border=True):
                    st.markdown(f"**{sos['analita']}** — {sos['motivo']}")
                    if not riga:
                        st.caption("Non trovo a quale referto appartiene: "
                                   "verificalo a mano nella scheda Referti.")
                    elif st.button("Verifica sul referto originale",
                                   icon=":material/healing:", key=f"verif_{i}",
                                   disabled=not modelli):
                        st.session_state["diagnostica_sha"] = riga["sha256"]
                        st.info(f"Apri la scheda **Referti** e cerca il referto "
                                f"del {riga['data_prelievo'] or 'documento'}: "
                                "la verifica è pronta lì.")

    st.caption("Strumento di lettura, non di diagnosi: i valori vanno interpretati "
               "dal medico alla luce della storia clinica.")

    # --- Consultazione dei referti e chat sull'ambito scelto ---------------
    # Sotto l'analisi una tantum: sfoglia i referti dell'ambito selezionato e
    # discutine in forma conversazionale. Per una tipologia o un referto
    # specifico la chat ragiona solo su quello; per tutto l'archivio, su tutto.
    st.divider()

    if tipo_scelto_an:
        da_mostrare = core.documenti_di_tipo(conn, tipo_scelto_an)
        titolo_ambito = etichetta(tipo_scelto_an).lower()
    elif sha_scelto:
        da_mostrare = [r for r in core.documenti_di_tipo_qualunque(conn)
                       if r["sha256"] == sha_scelto]
        titolo_ambito = "questo referto"
    else:
        da_mostrare = core.documenti_di_tipo_qualunque(conn)
        titolo_ambito = "tutti i referti"

    if da_mostrare:
        with st.expander(f"Sfoglia i referti · {titolo_ambito} "
                         f"({len(da_mostrare)})", icon=":material/folder_open:"):
            for r in da_mostrare:
                data = core.normalizza_data(r["data_documento"]) or "data ignota"
                intest = f"**{data}**"
                if r["struttura"]:
                    intest += f" · {r['struttura']}"
                st.markdown(intest)
                if r["titolo"]:
                    st.markdown(f"*{r['titolo']}*")
                if r["sintesi"]:
                    st.markdown(r["sintesi"])
                if r["conclusioni"]:
                    st.markdown(f"**Conclusioni:** {r['conclusioni']}")
                if r["testo"]:
                    with st.expander("Testo completo"):
                        st.text(r["testo"])
                st.divider()

    st.markdown(f"**Discuti {titolo_ambito}**")
    st.caption("Domande in forma di conversazione sull'ambito selezionato qui "
               "sopra. Ogni domanda è indipendente dalle precedenti.")
    if not modelli:
        st.warning(f"Il modello «{scelti['chat']}» non è installato.")
    elif domanda_an := st.chat_input(
            f"Chiedi qualcosa su {titolo_ambito}…", key="chat_analisi"):
        if sha_scelto:
            contesto_chat = core.contesto_referto(conn, sha_scelto)
        elif tipo_scelto_an:
            contesto_chat = core.contesto_categoria(conn, tipo_scelto_an)
        else:
            contesto_chat = core.costruisci_contesto(conn, n_referti, "")
        with st.chat_message("user"):
            st.markdown(domanda_an)
        sistema_chat = (
            "Sei un assistente che aiuta a leggere referti medici. Rispondi solo "
            "sulla base dei referti forniti. Non inventare valori o diagnosi; se "
            "un'informazione non è nei referti, dillo. Non sostituisci il medico.")
        messaggi_an = [
            {"role": "system", "content": sistema_chat + "\n\nReferti:\n\n"
             + contesto_chat},
            {"role": "user", "content": domanda_an}]
        mostra_risposta(scelti["chat"], messaggi_an, "chat")

# --- Chat ------------------------------------------------------------------

if pagina == "assistente" and vista_assistente == "Conversazioni":
    st.subheader("Chat sui propri dati")
    st.caption(f"Modello in uso: `{scelti['chat']}`")

    conversazioni = {f"{c['id']} · {c['titolo']}": c["id"]
                     for c in core.elenco_conversazioni(conn)}
    c1, c2 = st.columns([3, 1])
    scelta = c1.selectbox("Conversazione", ["+ nuova", *conversazioni])
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
            emb_chat = emb
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

if pagina == "secondo-parere":
    st.subheader("Secondo parere da un modello esterno")
    st.caption("Prepara un quesito pseudonimizzato da sottoporre a un modello "
               "di frontiera. I dati riconosciuti vengono sostituiti in locale "
               "con token opachi e casuali.")

    fase_parere = int(st.session_state.get("parere_fase", 1))
    nomi_fasi = ["1 · Prepara", "2 · Verifica privacy", "3 · Invia e reidrata"]
    colonne_fasi = st.columns(3)
    for indice_fase, nome_fase in enumerate(nomi_fasi, 1):
        colonne_fasi[indice_fase - 1].markdown(
            f"**{nome_fase}**" if indice_fase == fase_parere else nome_fase)
    st.progress(fase_parere / 3)
    if fase_parere > 1 and st.button(
            "Modifica ambito", icon=":material/arrow_back:", key="parere_torna_ambito"):
        _dimentica_secondo_parere()
        st.session_state["parere_fase"] = 1
        st.rerun()
    if fase_parere == 3 and st.button(
            "Torna alla verifica privacy", icon=":material/arrow_back:",
            key="parere_torna_privacy"):
        st.session_state["parere_fase"] = 2
        st.rerun()

    st.error(
        ":material/gpp_maybe: **Nessuna garanzia e nessuna responsabilità.** "
        "AHIA è progettata perché nulla lasci il tuo computer senza un tuo gesto "
        "esplicito, e perché il testo del secondo parere sia pseudonimizzato — "
        "ma "
        "questo **non può essere garantito a priori**. Un bug dell'applicazione, "
        "di una libreria di terze parti o del servizio esterno, un errore di "
        "rilevazione o un uso improprio possono far sì che dati personali "
        "escano dal tuo computer o vengano condivisi con terze parti. Usando "
        "questa funzione accetti che chi ha realizzato AHIA **non si assume "
        "alcuna responsabilità** per dati personali condivisi, per malfunzionamenti "
        "propri o di componenti di terze parti, né per un utilizzo errato "
        "dell'applicazione. Rileggi sempre il testo prima di inviarlo e valuta "
        "tu se è privo di dati che non vuoi condividere.")

    if not core.numero_prelievi(conn):
        st.info("Carica almeno un referto.")
    else:
        if fase_parere == 1:
            # Ambito del parere: tutto, categorie selezionate, o un singolo referto.
            ambito = st.radio(
                "Cosa includere nel parere",
                ["Tutti i referti", "Solo alcune categorie", "Un singolo referto"],
                horizontal=True, key="ambito_parere")

            tipi_scelti: list[str] | None = None
            sha_scelto: str | None = None
            gruppi_p = core.documenti_per_tipo(conn)

            if ambito == "Solo alcune categorie":
                disponibili = [(t, TIPI[t]["label"]) for t in TIPI if gruppi_p.get(t)]
                etichette = st.multiselect(
                    "Categorie da includere",
                    [lab for _, lab in disponibili],
                    help="Puoi combinare più categorie: esami del sangue, visite, "
                         "ecografie…")
                tipi_scelti = [t for t, lab in disponibili if lab in etichette]
                if not tipi_scelti:
                    st.info("Seleziona almeno una categoria.")
            elif ambito == "Un singolo referto":
                tutti = core.elenco_documenti(conn)
                # Il selectbox deve ricevere opzioni serializzabili: gli oggetti
                # sqlite3.Row non lo sono. Passiamo gli sha (stringhe) e teniamo le
                # descrizioni in un dizionario per format_func.
                descrizioni = {}
                for r in tutti:
                    data = core.normalizza_data(r["data_documento"]) or "data ignota"
                    lab = TIPI.get(r["tipo"], {}).get("label", "Referto")
                    chiavi = r.keys()
                    strut = (f" · {r['struttura']}"
                             if "struttura" in chiavi and r["struttura"] else "")
                    descrizioni[r["sha256"]] = f"{data} — {lab}{strut}"
                if tutti:
                    sha_scelto = st.selectbox(
                        "Scegli il referto", list(descrizioni.keys()),
                        format_func=lambda s: descrizioni.get(s, s),
                        key="referto_singolo_p")
                else:
                    st.info("Nessun referto disponibile.")

            c1, c2, c3 = st.columns(3)
            eta_modo = c1.selectbox("Eta'", ["fascia", "esatta", "omessa"],
                                    help="La fascia quinquennale e' clinicamente "
                                         "sufficiente e meno identificante.")
            lingua_p = c2.selectbox("Lingua del quesito", ["it", "en"],
                                    format_func=lambda x: "Italiano" if x == "it"
                                    else "English")
            con_bmi = c3.checkbox("Includi il BMI", value=True)
            con_note = st.checkbox("Includi terapie e note del profilo", value=False,
                                   help="Testo libero: e' la parte che piu' "
                                        "facilmente contiene dati identificativi. "
                                        "Rileggila prima di attivarla.")
        else:
            dati_fase = st.session_state.get("parere_config", {})
            ambito = dati_fase.get("ambito", "Tutti i referti")
            tipi_scelti = dati_fase.get("tipi_scelti")
            sha_scelto = dati_fase.get("sha_scelto")
            eta_modo = dati_fase.get("eta_modo", "fascia")
            lingua_p = dati_fase.get("lingua_p", "it")
            con_bmi = dati_fase.get("con_bmi", True)
            con_note = dati_fase.get("con_note", False)
            gruppi_p = core.documenti_per_tipo(conn)

        # Costruzione del quadro secondo l'ambito, unendo parte numerica e
        # parte descrittiva quando entrambe sono pertinenti.
        n_tot = core.numero_prelievi(conn)
        parti_quadro = []
        if ambito == "Tutti i referti":
            parti_quadro.append(parere.quadro_minimizzato(
                conn, n_tot, eta=eta_modo, includi_bmi=con_bmi,
                includi_note=con_note))
            parti_quadro.append(parere.quadro_descrittivi(
                conn, tipi=[t for t in TIPI if not e_tabellare(t) and gruppi_p.get(t)]))
        elif ambito == "Solo alcune categorie" and tipi_scelti:
            tab = [t for t in tipi_scelti if e_tabellare(t)]
            desc = [t for t in tipi_scelti if not e_tabellare(t)]
            if tab:
                parti_quadro.append(parere.quadro_minimizzato(
                    conn, n_tot, eta=eta_modo, includi_bmi=con_bmi,
                    includi_note=con_note, tipi=tab))
            if desc:
                parti_quadro.append(parere.quadro_descrittivi(conn, tipi=desc))
        elif ambito == "Un singolo referto" and sha_scelto:
            parti_quadro.append(parere.quadro_minimizzato(
                conn, n_tot, eta=eta_modo, includi_bmi=con_bmi,
                includi_note=con_note, sha_singolo=sha_scelto))
            parti_quadro.append(parere.quadro_descrittivi(
                conn, sha_singolo=sha_scelto))

        quadro = "\n\n".join(p for p in parti_quadro if p)

        # I referti descrittivi sono testo libero: la pseudonimizzazione automatica
        # è meno affidabile che sulla tabella dei valori. Segnaliamolo.
        include_descrittivi = "Referti descrittivi" in quadro
        if include_descrittivi:
            st.warning(
                ":material/warning: Il parere include referti descrittivi (testo "
                "libero). La pseudonimizzazione automatica protegge i dati "
                "riconoscibili "
                "— nome, codici fiscali, email, telefoni, date, indirizzi, numeri "
                "di referto ed episodio, nomi di strutture sanitarie — ma su testo "
                "libero non è garantita: possono restare nomi di città, nomi di "
                "medici, o strutture scritte in forme inconsuete. Rileggi il testo "
                "con particolare attenzione prima di inviarlo.")

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

        if fase_parere == 1:
            st.session_state["parere_config"] = {
                "ambito": ambito, "tipi_scelti": tipi_scelti,
                "sha_scelto": sha_scelto, "eta_modo": eta_modo,
                "lingua_p": lingua_p, "con_bmi": con_bmi, "con_note": con_note,
            }
            ambito_valido = bool(quadro.strip())
            if st.button(
                    "Prepara e verifica la privacy", type="primary",
                    icon=":material/arrow_forward:", disabled=not ambito_valido,
                    key="parere_prepara_privacy"):
                st.session_state["parere_fase"] = 2
                st.rerun()
            if not ambito_valido:
                st.info("Completa la selezione: non ci sono ancora dati da preparare.")
            st.stop()

        st.divider()
        st.markdown("**Payload pseudonimizzato** — modificalo liberamente e "
                    "rileggilo prima di usarlo")

        profilo_parere = core.leggi_profilo(conn)
        if st.session_state.pop("pii_reset_gestione", False):
            for chiave_gestione in list(st.session_state):
                if chiave_gestione.startswith("pii_gestione_"):
                    st.session_state.pop(chiave_gestione, None)
        password_regole = st.session_state.get("chiave_sessione")
        regole_memorizzate: list[regole_pii.RegolaPII] = []
        errore_caricamento_regole = ""
        if password_regole:
            try:
                regole_memorizzate = regole_pii.carica(
                    conn, utente_corrente["id"], password_regole)
            except regole_pii.ErroreRegole as exc:
                errore_caricamento_regole = str(exc)
        valori_regole_attive = regole_pii.attive(regole_memorizzate)
        # Una nuova proposta genera sempre una nuova mappa e un nuovo spazio di
        # token. La mappa resta nell'oggetto di sessione e non viene serializzata.
        if st.session_state.get("quesito_origine_pseudo") != proposta:
            precedente = st.session_state.get("parere_sessione_pseudo")
            if isinstance(precedente, pseudo.SessionePseudonimi):
                precedente.dimentica()
            rilevate, stato_presidio = presidio_ahia.rileva(
                proposta, profilo_parere, valori_regole_attive)
            esito = pseudo.pseudonimizza(proposta, rilevate)
            payload = esito.testo + "\n\n---\n\n" + pseudo.ISTRUZIONI_TOKEN
            esito.sessione.impronta_payload = pseudo.impronta(payload)
            st.session_state["quesito_origine_pseudo"] = proposta
            st.session_state["quesito_esterno"] = payload
            st.session_state["parere_sessione_pseudo"] = esito.sessione
            st.session_state["parere_stato_presidio"] = stato_presidio
            st.session_state["parere_avvisi_pseudo"] = esito.avvisi
            st.session_state["parere_hash_visto"] = ""
            st.session_state["parere_hash_confermato"] = None
            st.session_state["conferma_parere_payload"] = False
            for chiave_stato in (
                    "parere_risposta", "parere_risposta_pseudonima",
                    "parere_avvisi_risposta", "risposta_manual_pseudo"):
                st.session_state.pop(chiave_stato, None)

        sessione_pseudo = st.session_state.get("parere_sessione_pseudo")
        stato_presidio = st.session_state.get("parere_stato_presidio")
        if not isinstance(sessione_pseudo, pseudo.SessionePseudonimi):
            # Recupero difensivo per sessioni aperte durante un aggiornamento.
            st.session_state.pop("quesito_origine_pseudo", None)
            st.warning("La mappa temporanea non è più disponibile: rigenero il "
                       "quesito prima di consentire l'invio.")
            st.rerun()

        if stato_presidio and stato_presidio.attivo:
            st.success(":material/security: Controlli attivi: regole AHIA e "
                       f"Presidio italiano (`{stato_presidio.modello}`).")
        else:
            dettaglio = (stato_presidio.dettaglio if stato_presidio else
                         "Stato di Presidio non disponibile.")
            st.warning(":material/shield: Sono attivi i controlli di base AHIA; "
                       f"Presidio italiano non è attivo. {dettaglio}")
        if presidio_ahia.modalita_strict() and not (
                stato_presidio and stato_presidio.attivo):
            st.error("La modalità strict è attiva: l'invio diretto resta "
                     "bloccato finché Presidio italiano non è disponibile.")
        if errore_caricamento_regole:
            st.error(":material/key_off: "
                     f"{errore_caricamento_regole} Gestiscile nel pannello "
                     "«Regole PII personali» prima di inviare.")
        elif valori_regole_attive:
            st.info(":material/bookmark: "
                    f"{len(valori_regole_attive)} regole PII personali attive; "
                    "i valori sono stati decifrati soltanto in questa sessione.")

        if "quesito_esterno_prossimo" in st.session_state:
            st.session_state["quesito_esterno"] = st.session_state.pop(
                "quesito_esterno_prossimo")
        if st.session_state.pop("pii_reset_falsi_positivi", False):
            st.session_state.pop("pii_falso_positivo_scelte", None)
            st.session_state.pop("pii_falso_positivo_mostra", None)
        testo = st.text_area("quesito", height=420,
                             label_visibility="collapsed", key="quesito_esterno")

        sostituzioni = sum(testo.count(token)
                           for token in sessione_pseudo.token_a_valore)
        st.caption(f"{sostituzioni} occorrenze protette con "
                   f"{len(sessione_pseudo.token_a_valore)} token opachi. I token "
                   "non contengono il tipo del dato né un contatore.")
        if sessione_pseudo.token_a_tipo:
            riepilogo_tipi: dict[str, int] = {}
            for tipo_locale in sessione_pseudo.token_a_tipo.values():
                riepilogo_tipi[tipo_locale] = riepilogo_tipi.get(tipo_locale, 0) + 1
            with st.expander("Riepilogo locale delle sostituzioni",
                             icon=":material/find_in_page:"):
                st.caption("Le categorie qui sotto restano in AHIA e non sono "
                           "codificate nei token inviati.")
                for tipo_locale, numero in sorted(riepilogo_tipi.items()):
                    st.write(f"- {tipo_locale.replace('_', ' ').title()}: {numero}")

        token_presenti = [
            token for token in sessione_pseudo.token_a_valore
            if token in testo
        ]
        if token_presenti:
            with st.expander("Rivedi possibili falsi positivi",
                             icon=":material/rule:"):
                st.caption("Puoi ripristinare un valore che non è una PII. "
                           "AHIA lo ignorerà soltanto in questa richiesta; la "
                           "scelta non viene salvata né inviata al modello.")
                mostra_falsi_positivi = st.checkbox(
                    "Mostra i valori rilevati in chiaro su questo schermo",
                    key="pii_falso_positivo_mostra")
                if mostra_falsi_positivi:
                    st.warning("Ripristina soltanto termini clinici o altri "
                               "falsi positivi: il valore tornerà nel payload "
                               "destinato al servizio esterno.")
                    selezionati_fp = st.multiselect(
                        "Valori da mantenere in chiaro",
                        token_presenti,
                        format_func=lambda token: (
                            f"{sessione_pseudo.token_a_tipo[token].replace('_', ' ').title()}"
                            f" · {sessione_pseudo.token_a_valore[token]}"),
                        key="pii_falso_positivo_scelte")
                    if st.button(
                            "Ripristina i valori selezionati",
                            icon=":material/undo:", disabled=not selezionati_fp,
                            key="btn_ripristina_falsi_positivi"):
                        ripristino = pseudo.ripristina_falsi_positivi(
                            testo, sessione_pseudo, selezionati_fp)
                        st.session_state["quesito_esterno_prossimo"] = (
                            ripristino.testo)
                        st.session_state["parere_sessione_pseudo"] = (
                            sessione_pseudo)
                        st.session_state["parere_hash_confermato"] = None
                        st.session_state.pop("parere_risposta", None)
                        st.session_state["pii_reset_falsi_positivi"] = True
                        st.rerun()
                else:
                    st.caption("I valori originali non vengono inviati al "
                               "browser finché non scegli di mostrarli.")
        if sessione_pseudo.valori_consentiti:
            st.info(":material/check_circle: "
                    f"{len(sessione_pseudo.valori_consentiti)} valori "
                    "classificati come falsi positivi in questa richiesta.")

        # La scansione e' ripetuta sull'esatto testo dell'editor. Se trova nuovi
        # intervalli, li mostra e richiede un gesto separato per sostituirli.
        rilevate_finali, stato_scansione = presidio_ahia.rileva(
            testo, profilo_parere, valori_regole_attive)
        rilevate_finali = pseudo.filtra_falsi_positivi(
            testo, rilevate_finali, sessione_pseudo)
        residue = pseudo.risolvi_sovrapposizioni(testo, rilevate_finali)
        avvisi_payload = list(st.session_state.get("parere_avvisi_pseudo", []))
        avvisi_payload.extend(pseudo.verifica_payload(testo, sessione_pseudo))
        if errore_caricamento_regole:
            avvisi_payload.append(
                "Le regole PII personali non sono disponibili.")
        avvisi_payload = sorted(set(avvisi_payload))

        if residue:
            tipi_residui: dict[str, int] = {}
            for entita_residua in residue:
                tipi_residui[entita_residua.tipo] = (
                    tipi_residui.get(entita_residua.tipo, 0) + 1)
            descrizione_residui = ", ".join(
                f"{tipo.replace('_', ' ').lower()}: {numero}"
                for tipo, numero in sorted(tipi_residui.items()))
            st.error(":material/privacy_tip: I controlli rilevano nuovi dati "
                     f"da proteggere ({descrizione_residui}).")
            if st.button("Pseudonimizza i nuovi dati rilevati",
                         icon=":material/encrypted:",
                         key="btn_pseudonimizza_residui"):
                aggiornato = pseudo.pseudonimizza(
                    testo, residue, sessione=sessione_pseudo)
                st.session_state["quesito_esterno_prossimo"] = aggiornato.testo
                st.session_state["parere_sessione_pseudo"] = aggiornato.sessione
                st.session_state["parere_avvisi_pseudo"] = aggiornato.avvisi
                st.session_state["parere_hash_confermato"] = None
                st.session_state.pop("parere_risposta", None)
                st.rerun()

        for avviso in avvisi_payload:
            st.error(f":material/privacy_tip: {avviso}")
        if not residue and not avvisi_payload:
            st.success(":material/verified_user: Nessun ulteriore identificatore "
                       "rilevato dai controlli attivi. Non è una garanzia di "
                       "anonimato: la lettura finale spetta a te.")

        if messaggio_regola := st.session_state.pop(
                "pii_messaggio_regola", None):
            st.success(messaggio_regola)

        with st.popover("Segnala un dato non rilevato",
                        icon=":material/report:", width="stretch"):
            st.caption("Inserisci il valore esatto e scegli se proteggerlo "
                       "soltanto ora o ricordarlo cifrato per questo utente.")
            valore_sfuggito = st.text_input(
                "Dato da proteggere", max_chars=160,
                key="pii_non_rilevata_valore",
                placeholder="Nome, luogo, codice o altro identificatore")
            tipo_sfuggito = st.selectbox(
                "Categoria locale (facoltativa)",
                ["ALTRO_PII", "PAZIENTE", "PERSONA", "MEDICO", "STRUTTURA",
                 "LOCALITA", "INDIRIZZO", "CONTATTO",
                 "CODICE_FISCALE", "IDENTIFICATIVO_SANITARIO",
                 "IDENTIFICATIVO_DOCUMENTO", "DATA_CLINICA"],
                format_func=lambda t: t.replace("_", " ").title(),
                key="pii_non_rilevata_tipo")
            occorrenze = pseudo.trova_occorrenze(testo, valore_sfuggito)
            etichette_occorrenze: list[str] = []
            if valore_sfuggito and not occorrenze:
                st.info("Il valore non compare nel payload corrente.")
            for indice, (inizio, fine) in enumerate(occorrenze):
                contesto = testo[max(0, inizio - 28):min(len(testo), fine + 28)]
                contesto = contesto.replace("\n", " ")
                etichette_occorrenze.append(f"{indice + 1}. …{contesto}…")
            scelte_occorrenze = st.multiselect(
                "Occorrenze da proteggere", etichette_occorrenze,
                default=etichette_occorrenze,
                key="pii_non_rilevata_occorrenze")
            ambito_regola = st.radio(
                "Ambito",
                ["Solo questa richiesta", "Ricorda per questo utente"],
                key="pii_non_rilevata_ambito")
            prepara_export = st.checkbox(
                "Prepara anche un caso di miglioramento sanitizzato",
                key="pii_non_rilevata_export",
                help="Non viene caricato né inviato automaticamente: dopo la "
                     "protezione vedrai l'intero JSON prima del download.")
            if st.button("Proteggi le occorrenze selezionate",
                         icon=":material/encrypted:",
                         disabled=not scelte_occorrenze,
                         key="btn_proteggi_pii_segnalata"):
                indici_scelti = [etichette_occorrenze.index(etichetta)
                                 for etichetta in scelte_occorrenze]
                span_scelti = [occorrenze[indice] for indice in indici_scelti]
                errore_azione = ""
                candidato_nuovo = None
                if prepara_export:
                    try:
                        candidato_nuovo = regole_pii.crea_caso_miglioramento(
                            testo, valore_sfuggito, tipo_sfuggito, span_scelti)
                    except regole_pii.ErroreRegole as exc:
                        errore_azione = str(exc)
                if ambito_regola == "Ricorda per questo utente":
                    if not password_regole:
                        errore_azione = (
                            "Riaccedi prima di salvare una regola cifrata.")
                    elif not errore_azione:
                        try:
                            regole_pii.salva(
                                conn, utente_corrente["id"], password_regole,
                                valore_sfuggito, tipo_sfuggito)
                            st.session_state["pii_messaggio_regola"] = (
                                "Regola personale salvata e cifrata.")
                        except regole_pii.ErroreRegole as exc:
                            errore_azione = str(exc)
                if errore_azione:
                    st.error(errore_azione)
                else:
                    if candidato_nuovo:
                        st.session_state["pii_export_candidato"] = (
                            candidato_nuovo)
                        st.session_state["pii_export_consenso"] = False
                    manuali = pseudo.rileva_valore(
                        testo, valore_sfuggito, tipo_sfuggito, span_scelti)
                    aggiornato = pseudo.pseudonimizza(
                        testo, manuali, sessione=sessione_pseudo)
                    st.session_state["quesito_esterno_prossimo"] = (
                        aggiornato.testo)
                    st.session_state["parere_sessione_pseudo"] = (
                        aggiornato.sessione)
                    st.session_state["parere_avvisi_pseudo"] = aggiornato.avvisi
                    st.session_state["parere_hash_confermato"] = None
                    st.session_state.pop("parere_risposta", None)
                    st.rerun()

        candidato_export = st.session_state.get("pii_export_candidato")
        if candidato_export:
            with st.expander("Caso di miglioramento da revisionare",
                             icon=":material/data_object:", expanded=True):
                st.warning("Il valore segnalato è stato rimosso, ma il contesto "
                           "può ancora contenere informazioni sanitarie o altre "
                           "PII. Controlla integralmente il JSON: AHIA non lo "
                           "invia e il download resta una tua scelta.")
                testo_export = json.dumps(
                    candidato_export, ensure_ascii=False, indent=2)
                st.code(testo_export, language="json")
                consenso_export = st.checkbox(
                    "Ho revisionato l'intero caso e scelgo di salvarlo "
                    "localmente", key="pii_export_consenso")
                c_export, c_scarto = st.columns(2)
                c_export.download_button(
                    "Scarica il caso JSON", testo_export,
                    "caso_miglioramento_pii.json", mime="application/json",
                    icon=":material/download:", disabled=not consenso_export,
                    width="stretch")
                if c_scarto.button(
                        "Scarta", icon=":material/delete:", width="stretch",
                        key="pii_export_scarto"):
                    st.session_state.pop("pii_export_candidato", None)
                    st.rerun()

        with st.expander("Regole PII personali",
                         icon=":material/bookmarks:"):
            st.caption("Le regole sono isolate in questo archivio e salvate "
                       "come un unico documento cifrato con la password. "
                       "Reimpostando la password non saranno più decifrabili.")
            if not password_regole:
                st.warning("Riaccedi per gestire le regole cifrate.")
            elif errore_caricamento_regole:
                st.error(errore_caricamento_regole)
                st.caption("Puoi eliminare il documento non decifrabile e "
                           "ricreare le regole con la password corrente.")
                if st.button(
                        "Elimina tutte le regole non decifrabili",
                        icon=":material/delete_forever:",
                        key="pii_elimina_regole_indecifrabili"):
                    regole_pii.elimina_tutte(conn, utente_corrente["id"])
                    _dimentica_secondo_parere(includi_widget_pii=False)
                    st.session_state["pii_reset_gestione"] = True
                    st.rerun()
            elif not regole_memorizzate:
                st.info("Non hai ancora regole personali.")
            else:
                attive_numero = sum(r.attiva for r in regole_memorizzate)
                st.write(f"{len(regole_memorizzate)} regole, "
                         f"{attive_numero} attive.")
                mostra_valori = st.checkbox(
                    "Mostra i valori in chiaro su questo schermo",
                    key="pii_gestione_mostra")
                opzioni_regole = {r.id: r for r in regole_memorizzate}
                regola_id = st.selectbox(
                    "Regola da gestire", list(opzioni_regole),
                    format_func=lambda rid: (
                        f"{opzioni_regole[rid].tipo.replace('_', ' ').title()} "
                        f"· {'attiva' if opzioni_regole[rid].attiva else 'spenta'} "
                        f"· {rid[:6]}"),
                    key="pii_gestione_id")
                scelta_regola = opzioni_regole[regola_id]
                if mostra_valori:
                    valore_regola = st.text_input(
                        "Valore della regola", value=scelta_regola.valore,
                        max_chars=regole_pii.LUNGHEZZA_MASSIMA,
                        key=f"pii_gestione_valore_{regola_id}")
                else:
                    st.caption("Il valore non viene inviato al browser finché "
                               "non scegli di mostrarlo.")
                    valore_regola = scelta_regola.valore
                indice_tipo = regole_pii.TIPI_AMMESSI.index(
                    scelta_regola.tipo)
                tipo_regola = st.selectbox(
                    "Categoria", regole_pii.TIPI_AMMESSI, index=indice_tipo,
                    format_func=lambda t: t.replace("_", " ").title(),
                    key=f"pii_gestione_tipo_{regola_id}")
                regola_attiva = st.checkbox(
                    "Regola attiva", value=scelta_regola.attiva,
                    key=f"pii_gestione_attiva_{regola_id}")
                c_salva, c_elimina = st.columns(2)
                if c_salva.button(
                        "Salva modifiche", icon=":material/save:",
                        width="stretch", key="pii_gestione_salva"):
                    try:
                        regole_pii.aggiorna(
                            conn, utente_corrente["id"], password_regole,
                            regola_id, valore=valore_regola, tipo=tipo_regola,
                            attiva=regola_attiva)
                    except regole_pii.ErroreRegole as exc:
                        st.error(str(exc))
                    else:
                        _dimentica_secondo_parere(includi_widget_pii=False)
                        st.session_state["pii_reset_gestione"] = True
                        st.rerun()
                if c_elimina.button(
                        "Elimina regola", icon=":material/delete:",
                        width="stretch", key="pii_gestione_elimina"):
                    regole_pii.elimina(
                        conn, utente_corrente["id"], password_regole, regola_id)
                    _dimentica_secondo_parere(includi_widget_pii=False)
                    st.session_state["pii_reset_gestione"] = True
                    st.rerun()

        st.warning("La pseudonimizzazione riduce l'esposizione degli "
                   "identificatori, ma il quadro clinico può restare "
                   "reidentificabile. Da qui in avanti valgono anche le "
                   "condizioni del servizio esterno scelto.")
        hash_corrente = pseudo.impronta(testo)
        if st.session_state.get("parere_hash_visto") != hash_corrente:
            st.session_state["parere_hash_visto"] = hash_corrente
            st.session_state["parere_hash_confermato"] = None
            st.session_state["conferma_parere_payload"] = False
            for chiave_risposta in (
                    "parere_risposta", "parere_risposta_pseudonima",
                    "parere_avvisi_risposta", "risposta_manual_pseudo"):
                st.session_state.pop(chiave_risposta, None)
        flag_conferma = st.checkbox(
            "Ho letto questo esatto payload e confermo di volerlo inviare a "
            "un servizio esterno", key="conferma_parere_payload",
            disabled=bool(residue or avvisi_payload))
        if flag_conferma:
            st.session_state["parere_hash_confermato"] = hash_corrente
        confermato = (flag_conferma and
                      st.session_state.get("parere_hash_confermato") == hash_corrente)
        pronto = confermato and not residue and not avvisi_payload

        c8, c9 = st.columns(2)
        c8.download_button(
            "Scarica il quesito", testo, "quesito_secondo_parere.md",
            icon=":material/download:", disabled=not pronto, width="stretch")
        if pronto:
            with c9.popover("Mostra per copiarlo", icon=":material/content_copy:",
                            width="stretch"):
                st.caption("La mappa vive soltanto in questa sessione. Se chiudi "
                           "AHIA, la risposta esterna non potrà essere "
                           "reidratata automaticamente.")
                st.code(testo, language="markdown")
                testo_js = json.dumps(testo)
                st.html(f"""
                <button id="cp-parere" style="padding:6px 12px;border:1px solid
                  #2f6d6a;border-radius:8px;background:#f1f5f5;color:#2f6d6a;
                  font-weight:550;cursor:pointer">📋 Copia negli appunti</button>
                <script>
                  const b = document.getElementById('cp-parere');
                  b.onclick = async () => {{
                    try {{
                      await navigator.clipboard.writeText({testo_js});
                      b.textContent = '✅ Copiato';
                    }} catch (e) {{ b.textContent = 'Copia non riuscita'; }}
                  }};
                </script>
                """, unsafe_allow_javascript=True)
        else:
            c9.button("Mostra per copiarlo", icon=":material/content_copy:",
                      disabled=True, width="stretch",
                      key="btn_mostra_per_copiarlo_pseudo")

        if fase_parere == 2:
            if pronto and st.button(
                    "Continua a invio e reidratazione", type="primary",
                    icon=":material/arrow_forward:", key="parere_continua_invio"):
                st.session_state["parere_fase"] = 3
                st.rerun()
            elif not pronto:
                st.info("Risolvi gli avvisi e conferma l’esatto payload per continuare.")
            st.stop()

        # --- Invio diretto a un modello di frontiera ---
        fornitori_pronti = segreti.fornitori_configurati(conn,
                                                         utente_corrente["id"])
        st.divider()
        if not fornitori_pronti:
            st.caption(":material/key_off: Per inviare direttamente il quesito, "
                       "configura una chiave API nel pannello «Chiavi API» qui "
                       "sotto. Senza, resta il percorso manuale: scarica o "
                       "copia, e incolla nel servizio che preferisci.")
        else:
            scelta = st.selectbox(
                "Invia a", fornitori_pronti,
                format_func=lambda f: (
                    f"{segreti.FORNITORI[f]['nome']} · "
                    f"{impostazioni.get(f'modello.esterno.{f}', segreti.FORNITORI[f]['modello'])}"),
                key="parere_fornitore")
            pw_sessione = st.session_state.get("chiave_sessione")
            invia_ora = st.button(
                f"Invia a {segreti.FORNITORI[scelta]['nome']}",
                type="primary", icon=":material/send:",
                disabled=(not pronto or not pw_sessione or
                          (presidio_ahia.modalita_strict() and
                           not stato_scansione.attivo)),
                key="btn_invia_parere",
                help=None if pronto else "Completa i controlli e conferma "
                                          "l'esatto payload prima di inviare.")
            if invia_ora and pw_sessione:
                # Ultimo controllo sull'esatto testo, anche se il pulsante era
                # stato renderizzato in stato valido nel run precedente.
                hash_invio = pseudo.impronta(testo)
                finali, stato_finale = presidio_ahia.rileva(
                    testo, profilo_parere, valori_regole_attive)
                finali = pseudo.filtra_falsi_positivi(
                    testo, finali, sessione_pseudo)
                residui_finali = pseudo.risolvi_sovrapposizioni(testo, finali)
                errori_finali = pseudo.verifica_payload(testo, sessione_pseudo)
                if (hash_invio != st.session_state.get(
                        "parere_hash_confermato") or residui_finali or
                        errori_finali or
                        (presidio_ahia.modalita_strict() and
                         not stato_finale.attivo)):
                    st.error("Il payload non coincide più con quello verificato "
                             "oppure richiede nuovi controlli. Rileggilo e "
                             "confermalo di nuovo.")
                else:
                    sessione_pseudo.impronta_payload = hash_invio
                    chiave = segreti.leggi_chiave(
                        conn, utente_corrente["id"], pw_sessione, scelta)
                    if not chiave:
                        st.error("Non riesco a decifrare la chiave API. Se hai "
                                 "reimpostato la password di recente, "
                                 "reinseriscila nel pannello «Chiavi API» qui "
                                 "sotto.")
                    else:
                        with st.spinner(
                                f"Invio a {segreti.FORNITORI[scelta]['nome']}…"):
                            try:
                                risposta_pseudo = segreti.invia(
                                    scelta, chiave, testo,
                                    modello=impostazioni.get(f"modello.esterno.{scelta}") or None)
                                reidratata = pseudo.reidrata(
                                    risposta_pseudo, sessione_pseudo)
                                st.session_state["parere_risposta_pseudonima"] = (
                                    risposta_pseudo)
                                st.session_state["parere_risposta"] = reidratata.testo
                                st.session_state["parere_avvisi_risposta"] = (
                                    reidratata.token_sconosciuti,
                                    reidratata.token_malformati)
                            except segreti.ErroreAPI as e:
                                st.session_state["parere_risposta"] = None
                                st.error(str(e))

        # Anche il percorso manuale puo' usare la stessa mappa finche' la
        # sessione Streamlit resta aperta.
        with st.expander("Incolla e reidrata una risposta ottenuta manualmente",
                         icon=":material/find_replace:"):
            st.caption("Incolla la risposta che contiene i token opachi. AHIA "
                       "ripristina solo i token esatti appartenenti a questa "
                       "richiesta; il testo non viene inviato altrove.")
            risposta_manual = st.text_area(
                "Risposta pseudonimizzata", height=220,
                key="risposta_manual_pseudo")
            if st.button("Reidrata localmente", icon=":material/lock_open:",
                         disabled=not risposta_manual.strip(),
                         key="btn_reidrata_risposta_manual"):
                reidratata = pseudo.reidrata(risposta_manual, sessione_pseudo)
                st.session_state["parere_risposta_pseudonima"] = risposta_manual
                st.session_state["parere_risposta"] = reidratata.testo
                st.session_state["parere_avvisi_risposta"] = (
                    reidratata.token_sconosciuti, reidratata.token_malformati)

        if st.session_state.get("parere_risposta"):
            st.markdown("#### Risposta reidratata localmente")
            st.info("Contiene di nuovo i dati personali sostituiti. Viene da un "
                    "modello esterno: è un supporto alla comprensione, non un "
                    "parere medico. Portala al tuo medico, non usarla per "
                    "decidere da solo.")
            sconosciuti, malformati = st.session_state.get(
                "parere_avvisi_risposta", ([], []))
            if sconosciuti:
                st.warning(f"La risposta contiene {len(sconosciuti)} token "
                           "integri ma sconosciuti, lasciati invariati.")
            if malformati:
                st.warning(f"La risposta contiene {len(malformati)} token "
                           "malformati, lasciati invariati senza correzioni.")
            st.markdown(st.session_state["parere_risposta"])
            st.download_button(
                "Scarica la risposta con i dati ripristinati",
                st.session_state["parere_risposta"],
                "risposta_secondo_parere.md", icon=":material/download:",
                key="btn_scarica_risposta")

        st.info("Configura chiavi e modelli in **Impostazioni → Modelli e provider**.")

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

if pagina == "dizionario":
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


# --- Impostazioni ----------------------------------------------------------

if pagina == "modelli":
    ui_impostazioni.mostra_modelli(
        conn, utente_corrente, st.session_state.get("chiave_sessione"))

if pagina == "privacy":
    ui_impostazioni.mostra_privacy(conn, utente_corrente)


# --- Guida -----------------------------------------------------------------

if pagina == "guida":
    st.subheader("Guida all'uso")
    manuale = config.DIR_APP / "MANUALE.md"
    if manuale.exists():
        st.markdown(manuale.read_text(encoding="utf-8"))
    else:
        st.info("Il file MANUALE.md non è presente accanto all'applicazione.")


# --- Diagnostica -----------------------------------------------------------

if pagina == "diagnostica":
    st.subheader("Diagnostica")
    st.caption("Osservabilità tecnica dell'app: prestazioni dei modelli, "
               "errori e storico delle tue operazioni. Riguarda solo il tuo "
               "archivio. Nessun dato clinico è registrato qui — solo metriche "
               "e messaggi tecnici.")

    stat = core.statistiche_eventi(conn)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Chiamate ai modelli", stat.get("chiamate", 0))
    c2.metric("Errori", stat.get("errori", 0))
    c3.metric("Durata media", f"{stat.get('durata_media') or 0:g} s")
    c4.metric("Durata max", f"{stat.get('durata_max') or 0:g} s")

    c5, c6, c7, c8 = st.columns(4)
    tok_tot = (stat.get("tok_in", 0) or 0) + (stat.get("tok_out", 0) or 0)
    c5.metric("Token totali", f"{tok_tot:,}".replace(",", "."))
    c6.metric("Token/risposta", f"{stat.get('tok_out_medio') or 0:g}")
    c7.metric("Velocità", f"{stat.get('token_s') or 0:g} tok/s"
              if stat.get("token_s") else "—")
    c8.metric("Elaborazioni", stat.get("operazioni", 0))

    # Dove va il tempo: ripartizione per categoria
    per_cat = core.eventi_per_categoria(conn)
    if per_cat:
        st.divider()
        st.markdown("**Per categoria**")
        import pandas as pd
        dfc = pd.DataFrame([{
            "Categoria": r["categoria"],
            "Eventi": r["n"],
            "Durata media (s)": r["durata_media"],
            "Token generati": r["tok_out"],
            "Errori": r["errori"],
        } for r in per_cat])
        st.dataframe(dfc, width="stretch", hide_index=True)

    # Andamento delle durate nel tempo
    eventi_modello = core.leggi_eventi(conn, limite=50, tipo="modello")
    durate = [(e["quando"], e["durata_s"]) for e in reversed(eventi_modello)
              if e["durata_s"]]
    if len(durate) >= 2:
        st.markdown("**Andamento durate delle chiamate**")
        import pandas as pd
        dfd = pd.DataFrame(durate, columns=["quando", "durata"])
        st.line_chart(dfd.set_index("quando"), height=180)

    st.divider()
    vista = st.radio("Mostra", ["Tutto", "Solo modelli", "Solo errori"],
                     horizontal=True, label_visibility="collapsed")
    filtro = {"Solo modelli": "modello", "Solo errori": "errore"}.get(vista)
    eventi = core.leggi_eventi(conn, limite=300, tipo=filtro)

    if not eventi:
        st.info("Nessun evento registrato finora. Le metriche compaiono qui "
                "man mano che usi i modelli — analisi, chat, caricamenti.")
    else:
        import pandas as pd
        righe = []
        for e in eventi:
            righe.append({
                "Quando": e["quando"],
                "Tipo": e["tipo"],
                "Categoria": e["categoria"] or "",
                "Esito": e["esito"] or "",
                "Modello": e["modello"] or "",
                "Durata (s)": e["durata_s"],
                "Token in": e["token_in"],
                "Token out": e["token_out"],
                "Dettaglio": e["dettaglio"] or "",
            })
        st.dataframe(pd.DataFrame(righe), width="stretch", hide_index=True)

        st.download_button(
            "Esporta il registro (CSV)",
            pd.DataFrame(righe).to_csv(index=False).encode(),
            "diagnostica-ahia.csv", "text/csv", icon=":material/download:")

    ui_diagnostica.mostra_log_sessione()

    st.divider()
    if st.button("Svuota il registro", icon=":material/delete_sweep:"):
        core.azzera_eventi(conn)
        st.rerun()


# --- Utenti (solo amministratore) ------------------------------------------

if e_admin:
    if pagina == "utenti":
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

        with st.expander("Ripristina da un archivio esportato",
                         icon=":material/restore:"):
            st.caption("Carica uno zip esportato da un'altra installazione per "
                       "ricreare l'utente con i suoi dati. Utile quando ti "
                       "sposti su hardware diverso.")
            nome_rip = st.text_input("Nome del nuovo utente", key="nome_ripristino")
            zip_caricato = st.file_uploader("Archivio (zip)", "zip",
                                            key="zip_ripristino")
            if zip_caricato and st.button("Ripristina",
                                          icon=":material/restore:",
                                          key="btn_ripristina"):
                pw_prov = utenti.password_suggerita()
                errore = utenti.crea(auth, nome_rip, pw_prov, "utente")
                if errore:
                    st.error(errore)
                else:
                    nuovo_uid = auth.execute(
                        "SELECT id FROM utenti WHERE nome_utente=?",
                        (nome_rip,)).fetchone()["id"]
                    ok, msg = utenti.importa_archivio(nuovo_uid,
                                                      zip_caricato.getvalue())
                    if ok:
                        st.success(f"Utente «{nome_rip}» ripristinato. Password "
                                   f"provvisoria: `{pw_prov}` — da cambiare al "
                                   "primo accesso.")
                    else:
                        utenti.elimina(auth, nuovo_uid)
                        st.error(f"Ripristino non riuscito: {msg}")

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

            zip_utente = utenti.esporta_archivio(scelto["id"])
            if zip_utente:
                import datetime as _dt
                st.caption("Prima di cancellare, puoi salvare i suoi dati — utile "
                           "per spostarli su un'altra macchina o tenerne copia.")
                st.download_button(
                    "Esporta il suo archivio (zip)", zip_utente,
                    f"ahia_{scelto['nome_utente']}_"
                    f"{_dt.date.today().isoformat()}.zip",
                    mime="application/zip", icon=":material/download:",
                    key="btn_esporta_prima_elimina")

            anche_dati = st.checkbox(
                "Elimina anche il suo archivio sanitario (referti, profilo, "
                "conversazioni). Irreversibile.", key="chk_anche_dati")
            conferma = st.text_input(
                "Per confermare, scrivi il nome utente "
                f"«{scelto['nome_utente']}»", key="conferma_nome_elimina")
            c1, c2 = st.columns(2)
            pronto = conferma.strip() == scelto["nome_utente"]
            if c1.button("Sì, elimina", type="primary", icon=":material/delete:",
                         disabled=not pronto, key="btn_si_elimina_1257"):
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
