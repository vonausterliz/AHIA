# Stato del progetto AHIA

Aggiornato al **10 agosto 2026**.

## Punto raggiunto

La versione corrente è **1.25.0**. Succede alla revisione `86dc7ae`, che aveva
introdotto la nuova interfaccia e i cataloghi modelli della v1.24.0. La 1.25.0
comprende:

- rilevazione locale di RAM, VRAM NVIDIA/AMD e memoria unificata Apple;
- raccomandazioni Ollama diverse per macchina e per priorità (Equilibrato,
  Più veloce, Massima qualità);
- distinzione tra modello consigliato e modello effettivamente in uso, con
  fallback verso un modello compatibile già installato;
- riconoscimento delle varianti quantizzate già presenti;
- pulsante **Da installare** con conferma esplicita, peso stimato e modalità di
  esecuzione prevista prima del download;
- logo orizzontale AHIA, descrizione e versione nello slot nativo Streamlit
  sopra il menu;
- documentazione e changelog aggiornati.

Sulla macchina di sviluppo AHIA rileva circa **60 GB di RAM** e una
**NVIDIA GeForce RTX 3060 con 12 GB di VRAM**. Con il profilo Equilibrato
propone:

| Ruolo | Modello consigliato |
|---|---|
| Operazioni rapide | `qwen3:8b` |
| Analisi approfondita | `qwen3:14b` |
| Visione e scansioni | `qwen3-vl:8b` |
| Ricerca semantica | `bge-m3` |

## Verifiche già eseguite

- compilazione Python dei moduli modificati: superata;
- suite automatica: **56 test su 56 superati**;
- smoke test Streamlit: bootstrap, accesso, menu, Home, raccomandazioni
  hardware e apertura della conferma di download superati;
- nessun modello è stato scaricato durante lo smoke test;
- `git diff --check`: superato.

## Controllo manuale di domani

1. Riavviare Streamlit e ricaricare la pagina senza cache.
2. Verificare che logo, nome AHIA, descrizione e versione siano realmente
   **sopra** le sezioni del menu.
3. Aprire **Impostazioni → Modelli e provider** e controllare leggibilità e
   allineamento delle quattro raccomandazioni.
4. Premere **Da installare** e verificare che il primo clic apra soltanto la
   conferma; **Annulla** non deve avviare traffico o download.
5. Se si desidera collaudare un pull reale, confermare un solo modello mancante
   e verificare avanzamento, completamento, aggiornamento dello stato e fallback.
6. Cambiare priorità tra Equilibrato, Più veloce e Massima qualità e controllare
   che i consigli cambino senza download automatici.
7. Passare a Personalizzata e verificare che i consigli restino informativi e
   non sovrascrivano le scelte dell'utente.

## Verifiche successive alla 1.25.0

- completare il controllo manuale sopra;
- decidere se eseguire un download Ollama reale (lo smoke verifica la conferma,
  non il trasferimento completo);
- correggere eventuali dettagli visivi emersi dal controllo.

## Lavoro successivo consigliato

### Privacy e qualità clinica

- Migliorare il corpus holdout congelato della pseudonimizzazione: l'ultimo
  rapporto registra recall **88,46%**, precisione **87,18%**, 9 leak sintetici
  e 9 errori di conservazione. Il corpus principale da 180 casi supera invece
  tutti i gate.
- Eseguire una valutazione clinica dedicata dei modelli. AHIA distingue
  disponibilità e compatibilità tecnica dalla validazione clinica e, al
  momento, non dichiara clinicamente validato alcun modello.
- Collaudare end-to-end OpenAI, Anthropic e OpenRouter con account di test e
  dati esclusivamente sintetici. L'integrazione è implementata, ma non è stata
  ancora verificata contro i servizi reali.

### Robustezza e portabilità

- Verificare la rilevazione hardware su macchine reali Apple Silicon, AMD,
  Windows e sistemi senza GPU; questi casi sono coperti da test simulati, mentre
  il riscontro reale attuale è NVIDIA/Linux.
- Aggiungere, come hardening, un controllo dello spazio libero prima del pull e
  una gestione più esplicita dell'interruzione di un download in corso.
- Considerare un benchmark locale facoltativo: oggi le raccomandazioni sono
  conservative e basate soprattutto sulla memoria, non sulla velocità misurata.

## Decisioni consolidate

- Il Secondo parere usa **pseudonimizzazione reversibile**, non anonimizzazione.
- I token inviati al modello sono opachi e non rivelano ruolo o categoria della
  persona; la reidratazione avviene soltanto in AHIA.
- L'utente può segnalare PII non rilevate e gestire regole personali cifrate.
- La storia clinica minimizzata può comunque essere identificante: il controllo
  umano del payload e la scelta del provider restano obbligatori.
- Le raccomandazioni hardware non installano nulla automaticamente e non
  modificano le configurazioni personalizzate.
