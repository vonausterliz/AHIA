# Stato del progetto AHIA

Aggiornato al **13 agosto 2026**.

## Punto raggiunto

La versione corrente è **1.28.1**. Comprende:

- coda seriale dei download Ollama, non bloccante e visibile nel menu;
- persistenza e ripresa dopo il riavvio di AHIA, controllo dello spazio libero,
  annullamento e nuovo tentativo;
- generatore di ZIP portabile con esclusione di dati, segreti, virtualenv e
  cache, più manifest SHA-256;
- matrice CI per Linux, macOS e Windows con Python 3.10 e 3.12;
- hardening di log, errori provider, isolamento multiutente e token alterati;
- riconoscimento più ampio degli identificativi documentali;
- valutazione tecnica preliminare di due modelli locali su casi sintetici.
- corpus a verità nota prodotto da FAKING_MEDDOC, benchmark L2 e collaudi L1/L3;
- avanzamento dei download Ollama visibile anche nella pagina Modelli.

## Verifiche eseguite

- compilazione di tutti i moduli Python: superata;
- suite automatica: **92 test su 92 superati**;
- smoke Streamlit autenticato: superato, inclusi Home, hardware e conferma
  download;
- corpus PII di sviluppo: recall, precisione e tipo 100%, zero leak, zero errori
  di preservazione e round-trip;
- holdout PII congelato: recall 100%, precisione 90,59%, zero leak e zero errori
  di round-trip; restano **8 errori di preservazione**, quindi il gate complessivo
  non è superato;
- OpenAI, Anthropic e OpenRouter: confine dati verificato con client simulati e
  payload esclusivamente pseudonimizzati;
- `qwen3:14b` e `qwen3:30b-instruct`: 5/5 casi sintetici superati con i prompt
  reali di AHIA. È un controllo tecnico, non una validazione clinica;
- `git diff --check`: superato.

## Portabilità

La logica di rilevazione hardware è coperta da test simulati per AMD/Linux,
Apple Silicon e Windows senza GPU. La CI multipiattaforma è pronta, ma i job
remoti saranno eseguiti solo dopo il push. Il riscontro fisico svolto in locale
resta Linux/NVIDIA; Mac, Windows e AMD reali richiedono le rispettive macchine.

Il pacchetto si crea con:

```bash
.venv/bin/python tools/crea_pacchetto.py
```

Su un albero modificato si può produrre soltanto una build dichiaratamente di
test usando `--consenti-modifiche`. Sul computer di destinazione vanno
installati Ollama e i modelli; database e referti non sono inclusi nello ZIP.

## Limiti aperti

- Nessuna chiave di test OpenAI, Anthropic o OpenRouter era disponibile: lo
  smoke live è predisposto ma non è stato eseguito contro servizi reali.
- Nessun modello è clinicamente validato. Servono protocollo preregistrato,
  revisori clinici indipendenti e un campione adeguato.
- Gli otto falsi positivi del holdout PII richiedono ulteriore lavoro basato su
  nuovi casi di sviluppo, senza adattare le regole al corpus congelato.
- Chiudere soltanto la scheda del browser non ferma il server e il download
  continua. Se si arresta il processo AHIA, il trasferimento corrente si ferma
  e viene ripreso al successivo avvio; senza il servizio Ollama non può procedere.

## Decisioni consolidate

- Il Secondo parere usa pseudonimizzazione reversibile, non anonimizzazione.
- La reidratazione avviene soltanto in AHIA e mai per somiglianza approssimata.
- I dettagli liberi non vengono salvati nei log salvo marcatura esplicita come
  sicuri.
- Le raccomandazioni hardware non installano nulla automaticamente e non
  sovrascrivono le configurazioni personalizzate.
