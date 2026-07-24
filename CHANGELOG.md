# Changelog

Le versioni seguono lo schema `MAJOR.MINOR.PATCH`: cambia il numero centrale
quando arrivano funzionalità nuove, l'ultimo quando si correggono difetti.

## 1.5.2 — 24 luglio 2026

Revisione prima della pubblicazione.

### Sicurezza

- Limite di 25 MB per file caricato: quello predefinito di Streamlit è 200 MB,
  sufficiente a riempire il disco con un singolo caricamento.
- Protezione CSRF sui caricamenti resa esplicita in configurazione, perché su
  un'app che riceve file non venga disattivata per distrazione.

### Prestazioni

- Il conteggio dei valori per documento veniva eseguito con una sottoquery per
  ogni riga: su 300 referti la scheda Referti impiegava 284 ms solo per quello.
  Con un unico raggruppamento e un indice su `risultati.sha256` scende a 2 ms.
- L'archivio mostra i 25 documenti più recenti per tipologia, con una spunta
  per aprirli tutti: ogni documento genera due widget, e con centinaia di
  referti la pagina diventava pesante da rendere.

## 1.5.1 — 24 luglio 2026

- Tema chiaro come predefinito. Resta possibile passare a quello scuro dal menu
  in alto a destra, e la scelta dell'utente ha la precedenza.
- Nome dell'app più grande nella barra laterale.

## 1.5.0 — 24 luglio 2026

### Novità

- **Registro dell'elaborazione.** Caricando un referto si apre un pannello per
  file che racconta cosa sta succedendo, riga per riga e con il tempo
  trascorso: apertura del PDF e sua dimensione, numero di pagine, se ha uno
  strato di testo o va rasterizzato, tipologia riconosciuta con la motivazione
  del modello, modello usato a ogni chiamata con token e velocità, valori
  letti, diciture nuove da mappare, quanti valori sono stati salvati e quanti
  erano già presenti, indicizzazione per la ricerca, intervalli completati dal
  catalogo.

  Al termine il pannello si richiude mostrando in intestazione tipologia, data
  e durata complessiva; i registri restano consultabili in fondo alla scheda
  Referti, accanto alla tabella delle metriche.

## 1.4.4 — 24 luglio 2026

### Correzioni

- **I collegamenti degli esami non mappati portavano all'indice per lettera.**
  Con un dizionario ricco — voci dell'emocromo, PSA, eGFR — capitava spesso, e
  l'indice alfabetico non è una risposta. Ora per gli esami senza una scheda
  corrispondente il collegamento apre una ricerca ristretta a labtestsonline.it,
  che porta alla pagina giusta in un clic. Viene inviato il solo nome
  dell'esame.
- Aggiunte le voci dell'emocromo: emocromo stesso, formula leucocitaria,
  neutrofili, linfociti, monociti, eosinofili, basofili, MCV, MCH, MCHC e RDW
  puntano alla scheda dell'esame emocromocitometrico, che descrive ogni
  componente.

## 1.4.3 — 24 luglio 2026

### Correzioni

- **La chat andava in errore per un amministratore.** Il pulsante «Elimina»
  della conversazione e quello della gestione utenti avevano etichetta e
  parametri identici, e Streamlit ne derivava lo stesso identificativo interno.
  L'errore compariva solo agli amministratori, gli unici a vedere entrambe le
  schede. Tutti i pulsanti hanno ora una chiave esplicita, così
  l'identificativo non dipende più da etichetta e parametri.

## 1.4.2 — 24 luglio 2026

- Licenza AGPL-3.0: avviso in cima a ogni modulo e collegamento al codice
  sorgente nella barra laterale, come richiede l'articolo 13 per chi usa il
  programma attraverso una rete.

## 1.4.1 — 24 luglio 2026

### Correzioni

- **I collegamenti alle schede degli esami finivano quasi sempre sull'indice
  alfabetico.** La ricerca richiedeva il nome canonico esatto, mentre in
  archivio gli analiti hanno spesso la dicitura grezza del laboratorio
  (`S-COLESTEROLO TOTALE`, `Glicemia`, `Azotemia`). Ora il nome viene prima
  risolto attraverso il dizionario degli alias, che conosce sinonimi e prefissi
  di matrice; il ripiego sull'indice resta solo per gli esami davvero
  sconosciuti.
- Aggiunta la scheda della VES, che mancava nella mappa.

- **La schermata di primo avvio non diceva abbastanza chiaramente che
  l'utenza creata è l'amministratore.** Testo e messaggio finale riscritti.

## 1.4.0 — 24 luglio 2026

### Novità

- **Archivi separati per utente.** Ogni utente ha il proprio database, la
  propria cartella di referti, il proprio dizionario e i propri riferimenti
  personali, sotto `~/.ahia/archivi/<id>/`. Le utenze stanno in un database a
  parte.

  L'isolamento è fisico, non logico: non c'è un filtro `WHERE utente_id` da
  ricordarsi in ogni query — sono file diversi, e una query non può
  attraversare il confine nemmeno per errore. Nemmeno l'amministratore vede i
  dati altrui.

  Chi aggiorna da una versione precedente non perde nulla: alla creazione del
  primo amministratore l'archivio esistente viene spostato nella sua cartella.

  Eliminando un utente si può scegliere se cancellare anche il suo archivio.

## 1.3.0 — 24 luglio 2026

### Novità

- **Autenticazione e gestione utenti.** Al primo avvio l'app chiede di creare
  l'utenza amministratore; da lì in poi serve un accesso. L'amministratore ha
  una scheda dedicata per creare, bloccare, riabilitare, eliminare utenti,
  reimpostare password e assegnare il ruolo.

  Le password non vengono mai salvate: si conserva un'impronta scrypt con sale
  casuale per utente, verificata a tempo costante. Cinque tentativi falliti
  sospendono l'accesso per quindici minuti. Un utente creato dall'amministratore
  deve scegliere una password propria al primo accesso. Non è possibile
  bloccare, declassare o eliminare l'ultimo amministratore attivo, né agire
  sulla propria utenza per bloccarla o eliminarla.

  **L'autenticazione decide chi entra, non separa gli archivi**: tutti gli
  utenti abilitati vedono gli stessi referti.

## 1.2.1 — 24 luglio 2026

Revisione del codice e verifica di sicurezza. Nessuna funzionalità nuova.

### Sicurezza

- Rimosso l'unico punto in cui l'interfaccia interpretava HTML grezzo: il nome
  dell'analita, che proviene dai PDF, veniva reso con `unsafe_allow_html`. Un
  referto costruito ad arte poteva iniettare markup nella pagina.
- `OLLAMA_HOST` viene validato: solo `http://` e `https://`. Prima una
  variabile d'ambiente con schema `file://` avrebbe fatto leggere file locali.
- Documentato il modello di rischio nel README, incluso ciò che il codice non
  può risolvere: un PDF ostile può influenzare il modello con istruzioni
  nascoste nel testo.

### Prestazioni

- Il recupero semantico non viene più eseguito a ogni rerun di Streamlit. Era
  una chiamata di embedding a Ollama a ogni interazione con un widget, per un
  risultato identico; ora è memorizzato per dieci minuti.
- Il catalogo dei riferimenti non viene più riletto e riparsato per ogni riga:
  è memorizzato in base alla data di modifica del file.

### Pulizia

- Corrette due chiusure su variabili di ciclo, un import inutilizzato, uno
  `zip()` senza `strict`, una lambda assegnata a variabile. Il codice passa
  ruff con i controlli F, E, W, B, SIM, PERF.

## 1.2.0 — 24 luglio 2026

### Novità

- **Collegamenti alle schede degli esami.** Accanto a ogni indicatore, nei
  grafici e nella tabella delle variazioni, un collegamento alla scheda di
  labtestsonline.it, il portale divulgativo di SIBioC che descrive oltre 300
  esami di laboratorio. Mappati 51 analiti; per quelli non mappati il
  collegamento porta all'indice alfabetico posizionato sulla lettera giusta.

  Nessun contenuto viene copiato — i testi del portale sono coperti da licenza:
  l'app conserva solo gli indirizzi, e la descrizione resta aggiornata alla
  fonte.

## 1.1.0 — 24 luglio 2026

### Novità

- **Catalogo degli intervalli di riferimento.** Quando un referto non riporta
  l'intervallo per un esame, può essere completato con valori indicativi per
  adulti, distinti per sesso dove serve (ferritina, emoglobina, creatinina,
  transaminasi, HDL, acido urico, VES). Si attiva dalla scheda Dizionario.

  Tre garanzie: l'intervallo stampato sul referto non viene mai sostituito; il
  catalogo si applica solo se l'unità di misura coincide, così una PCR in mg/dL
  non viene confrontata con una soglia in mg/L; l'origine resta sempre visibile
  — banda blu invece che verde nei grafici, asterisco nelle tabelle, nota
  esplicita nel contesto passato al modello.

  Il catalogo si riallinea da solo quando cambi il sesso nel profilo, e si può
  estendere con `riferimenti_personali.json` nella cartella dati.

## 1.0.0 — 24 luglio 2026

Prima versione numerata. Comprende tutto il lavoro precedente.

### Correzioni

- **Flag calcolati invece che dichiarati.** Lo stato di un valore (nella norma,
  alto, basso) viene ora calcolato dai limiti di riferimento ogni volta che sono
  disponibili; il flag dichiarato dal modello si usa solo in loro assenza. Il
  modello sbagliava sistematicamente sugli esami dove un valore alto è
  desiderabile, segnalando in rosso un HDL elevato. I dati già archiviati
  vengono riallineati al primo avvio.
- **Asse temporale senza arrotondamenti.** Vega-Lite estendeva il dominio a un
  confine "tondo", facendo comparire una tacca di luglio per un prelievo di fine
  giugno, che si leggeva come una misurazione inesistente. Ora le tacche cadono
  sulle date reali e mostrano il giorno.

### Funzionalità

- Archivio di referti PDF, nativi o scansionati, con estrazione strutturata dei
  valori e classificazione in dieci tipologie
- Grafici temporali con banda di riferimento, confronto normalizzato e mappa
  degli stati
- Analisi e chat con un LLM locale, con ambito selezionabile: tutto l'archivio,
  una tipologia o un singolo referto
- Numeri precalcolati nel contesto e strumenti interrogabili dal modello
- Ricerca full-text (FTS5) e semantica (embedding) sui referti narrativi
- Quesito anonimizzato per un secondo parere da un modello esterno
- Dizionario degli analiti con proposte assistite dall'LLM
- Avvertenza bilingue all'avvio, versionata
- macOS, Linux e Windows
