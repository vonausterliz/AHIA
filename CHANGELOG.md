# Changelog

Le versioni seguono lo schema `MAJOR.MINOR.PATCH`: cambia il numero centrale
quando arrivano funzionalità nuove, l'ultimo quando si correggono difetti.

## 1.22.0 — 9 agosto 2026

### Pseudonimizzazione del secondo parere

- **Benchmark italiano riproducibile.** Aggiunto un corpus CC0 interamente
  sintetico di 180 casi, con metriche complessive e per tipo su recall,
  precisione, categoria, leak, conservazione clinica e round-trip. Con Presidio
  e il modello italiano il corpus raggiunge tutti i gate configurati.
- **Tuning di Presidio.** Le soglie possono essere differenziate per entità e
  un filtro strutturale evita che analiti, farmaci e unità vengano scambiati per
  persone o località. Corretto anche un falso positivo del recognizer medico.
- **Regole PII personali.** Un dato sfuggito può essere ricordato per l'utente:
  valori, categorie e stato sono conservati in un unico documento cifrato,
  separato per archivio. Le regole possono essere mostrate, modificate,
  disattivate ed eliminate.
- **Casi di miglioramento senza upload.** Dalla segnalazione manuale si può
  preparare un JSON che esclude il valore reale. Il contesto residuo viene
  mostrato integralmente e il download richiede un consenso esplicito.

## 1.21.0 — 27 luglio 2026

### Novità e correzioni

- **Diagnostica più ricca.** Corretto un difetto per cui le chiamate in chat e
  analisi non registravano i token (apparivano «None»): ora lo streaming
  raccoglie i contatori finali di Ollama. Aggiunte metriche: durata massima,
  token per risposta, velocità di generazione (token/s), numero di elaborazioni.
  Nuova tabella «Per categoria» che mostra dove va il tempo (analisi, chat,
  estrazione) e un grafico dell'andamento delle durate. Anche l'estrazione dei
  referti ora registra token e durata.

## 1.20.1 — 27 luglio 2026

- La scheda **Diagnostica** è ora visibile a ogni utente, non solo
  all'amministratore: ognuno vede le metriche e lo storico del proprio archivio.
  Così la diagnostica è utile a tutti senza intaccare la separazione dei dati —
  nessuno vede le attività altrui, coerentemente con il resto dell'app.

## 1.20.0 — 27 luglio 2026

### Novità

- **Osservabilità: scheda «Diagnostica».** Un registro eventi unico traccia le
  chiamate ai modelli (durata, token), le operazioni (estrazioni) e gli errori.
  La nuova scheda Diagnostica (solo amministratore) mostra metriche di sintesi,
  la tabella degli eventi filtrabile per modelli o errori, l'esportazione in CSV
  e lo svuotamento del registro. Il registro contiene solo metriche e messaggi
  tecnici — mai testo di referti o dati clinici.

## 1.19.0 — 25 luglio 2026

### Novità

- **Analisi più approfondite.** Rivisto il prompt dell'analisi perché il modello:
  colleghi i valori in pattern clinici (più marcatori dello stesso organo, o una
  carenza che spiega più valori) invece di commentarli isolati; ordini i risultati
  per rilevanza, mettendo in cima ciò che conta di più; e contestualizzi i valori
  di poco fuori norma come spesso banali, per non allarmare inutilmente. La
  struttura in quattro sezioni resta invariata.

## 1.18.1 — 25 luglio 2026

### Sicurezza e correzioni

- **Estrazione del testo più robusta.** Alcuni PDF (referti firmati
  digitalmente, layout a colonne) venivano letti con le lettere mescolate
  («firmatoP deigrit…»), rendendo il testo illeggibile e l'anonimizzazione
  inefficace. Ora l'app prova due strategie di estrazione e sceglie quella che
  produce testo più pulito. I referti già in archivio con testo corrotto si
  correggono col pulsante «Ri-estrai».
- **Anonimizzazione: nuovi dati riconosciuti.** Vengono ora rimossi anche il
  nome del medico firmatario («FIRMATO DA…», «Dr./Dott.ssa…»), il numero R.E.A.,
  i siti web e i numeri di telefono/fax in formato fisso. Corretto un caso in cui
  il riconoscimento del medico poteva sconfinare sulla riga successiva e oscurare
  un dato clinico. Verificato con una regressione su 18 tipi di dato sensibile e
  11 di dato clinico: tutti i sensibili rimossi, nessun clinico alterato.

## 1.18.0 — 25 luglio 2026

### Novità

- **Ri-estrazione di un referto già in archivio.** Accanto a ogni documento, nella
  scheda Referti, c'è ora un pulsante «Ri-estrai» che rielabora il referto dal suo
  PDF originale con i modelli attuali, senza doverlo ricaricare a mano. Utile
  quando l'estrazione è migliorata da quando il referto fu caricato: il testo
  salvato viene rigenerato. Serve in particolare per l'anonimizzazione del secondo
  parere, che lavora sul testo salvato al momento del caricamento.

## 1.17.4 — 25 luglio 2026

### Sicurezza

- **Anonimizzazione basata sulle etichette anagrafiche.** Oltre a inseguire il
  nome del profilo, l'oscuramento ora riconosce i valori che seguono le etichette
  tipiche dei referti («Cognome:», «Nome:», «Nato a», «Residente a») e i nomi in
  maiuscolo seguiti da un codice: così vengono rimossi anche cognomi, secondi
  nomi e luoghi che non sono nel profilo dell'utente. Verificato con una batteria
  di regressione che nessun dato clinico (valori, misure, intestazioni come
  «REFERTO ECOGRAFICO ADDOME») venga oscurato per errore.

## 1.17.3 — 25 luglio 2026

### Sicurezza

- **Anonimizzazione dei referti descrittivi ulteriormente rafforzata.** Ora
  vengono rimossi anche: i codici episodio/prestazione (es. «EP2300018443»), i
  codici alfanumerici lunghi, e i nomi delle strutture sanitarie (poliambulatorio,
  ospedale, clinica, ASST, ASL, IRCCS, ecc.). Verificato che i dati clinici —
  valori, misure, prestazioni — restino intatti. Restano non garantiti, come già
  segnalato, i nomi di città isolati e le strutture scritte in forme inconsuete:
  l'avviso nell'app ora lo dice esplicitamente.

## 1.17.2 — 25 luglio 2026

### Correzioni

- Corretto un errore («cannot pickle 'sqlite3.Row' object») che faceva fallire il
  secondo parere scegliendo «Un singolo referto»: il selettore riceveva le righe
  grezze del database, che Streamlit non riesce a serializzare. Ora riceve gli
  identificativi dei referti, con la descrizione gestita a parte.

### Documentazione

- Il README ora include le istruzioni per installare Ollama su macOS, Windows e
  Linux, come primo passo dell'installazione, prima di scaricare i modelli.

## 1.17.1 — 25 luglio 2026

- Rimossi gli avvisi di deprecazione di Streamlit nel log di avvio: sostituito
  `use_container_width=True` con `width="stretch"` nei grafici, e
  `components.html` con `st.html(..., unsafe_allow_javascript=True)` per il
  pulsante di copia del secondo parere. Quest'ultimo, non essendo più dentro un
  iframe, ha ora accesso più diretto agli appunti del browser.

## 1.17.0 — 25 luglio 2026

### Sicurezza

- **Anonimizzazione dei referti descrittivi rafforzata.** Nel secondo parere,
  quando si includeva un referto descrittivo potevano restare il cognome e il
  numero di referto. Ora l'oscuramento riconosce anche: il cognome da solo o in
  ordine invertito (e ogni singola parte del nome del profilo), i numeri di
  referto/protocollo/accettazione/cartella nosologica, gli identificativi
  numerici lunghi (tessera sanitaria), le date scritte a parole, e i nomi
  preceduti da titoli di cortesia. Verificato su un referto realistico completo:
  tutti i dati identificativi strutturati vengono rimossi, i dati clinici
  restano. Resta il limite noto, già segnalato nell'app, che su testo libero
  l'anonimizzazione non è garantita (es. i nomi di città).

### Modifiche

- **Scheda «Analisi» unificata.** La scheda Analisi ora accorpa anche la
  consultazione dei referti e la chat conversazionale che prima stavano nella
  scheda «Referti descrittivi», che è stata rimossa per eliminare la
  sovrapposizione. Oltre alla lettura d'insieme una tantum, da qui si sfogliano i
  referti dell'ambito scelto (tutto, una tipologia, un singolo referto) e ci si
  discute in forma di conversazione.

## 1.16.0 — 25 luglio 2026

### Novità

- **Manuale d'uso.** Aggiunto un manuale completo (`MANUALE.md`) che accompagna
  l'uso quotidiano dell'app scheda per scheda, con spiegazioni semplici e note
  tecniche dove servono. È consultabile anche dentro l'app, nella nuova scheda
  **Guida**, così è sempre a portata senza uscire dall'applicazione.

## 1.15.1 — 25 luglio 2026

- Corretto un errore («No item with that key») che si verificava scegliendo
  «Un singolo referto» nel secondo parere: l'elenco dei documenti non includeva
  la colonna della struttura usata per descriverli nella lista.

## 1.15.0 — 25 luglio 2026

### Novità

- **Secondo parere con ambito selezionabile.** Invece di prendere in blocco un
  numero fisso di prelievi, ora si sceglie cosa includere: tutti i referti, solo
  alcune categorie (selezione multipla — sangue, visite, ecografie…), oppure un
  singolo referto scelto dalla lista. Il quesito viene costruito di conseguenza,
  unendo la tabella dei valori numerici e il testo dei referti descrittivi
  pertinenti.
- **Anonimizzazione dei referti descrittivi.** Quando il parere include referti
  di testo libero (visite, ecografie), il loro contenuto passa da un
  oscuramento automatico che sostituisce codici fiscali, email, telefoni, date,
  indirizzi e il nome del profilo; le date diventano il solo anno. Un avviso
  ricorda che su testo libero l'anonimizzazione non è garantita e che va riletto
  con attenzione. Il controllo pre-invio esistente resta come ultima rete.

## 1.14.0 — 25 luglio 2026

### Novità

- **Fasce fuori norma evidenziate nei grafici.** Nell'andamento di ogni analita,
  le zone fuori dall'intervallo di riferimento sono ora colorate di rosso chiaro
  (sopra il massimo e sotto il minimo): si vede a colpo d'occhio quando un valore
  cade fuori norma, senza dover leggere i numeri. La banda normale resta tenue
  sullo sfondo. La scheda è stata rinominata «Andamento analiti».

- **Nuova scheda «Referti descrittivi».** I referti non numerici — visite,
  ecografie, radiografie, TAC, cardiologia — sono raggruppati per tipo e
  consultabili per categoria, separati dagli esami del sangue. Per ogni categoria
  si vedono i referti in ordine cronologico con sintesi, conclusioni e testo
  completo, e una chat dedicata che ragiona **solo** su quella categoria: si può
  chiedere «come è cambiata la mia situazione oculistica nel tempo?» senza che il
  modello mescoli gli esami del sangue o altre visite.

## 1.13.0 — 24 luglio 2026

### Novità

- **Data e ora di accettazione dell'avvertenza.** Quando l'utente accetta
  l'avvertenza iniziale, oltre alla versione viene ora registrato l'istante
  esatto. Riaprendo l'avvertenza dal pulsante nella barra laterale, in fondo
  compare quando e quale versione è stata accettata. Il dato è per utente.

## 1.12.3 — 24 luglio 2026

- **Avvertenza iniziale rafforzata.** Il disclaimer di non-responsabilità che
  l'utente accetta al primo avvio ora dice esplicitamente che il comportamento
  «nulla esce dal computer» non è garantibile a priori, che bug propri o di terze
  parti o un uso improprio possono far uscire dati, e che chi ha realizzato AHIA
  non si assume responsabilità per dati condivisi, malfunzionamenti o uso errato.
  Aggiunta la nota che l'integrazione API diretta non è testata. In italiano e
  inglese. Il disclaimer viene ripresentato a chi l'aveva già accettato.

## 1.12.2 — 24 luglio 2026

- Documentato — nel README e nell'aiuto dell'interruttore — che il primo referto
  di un laboratorio mai visto viene estratto due volte (una per riconoscere il
  laboratorio, una per applicare la scheda di lettura appena creata) ed è quindi
  più lento; i referti successivi dello stesso laboratorio partono già con la
  scheda, in una sola estrazione. Il comportamento non cambia: viene solo reso
  esplicito.

## 1.12.1 — 24 luglio 2026

- README unico: presentazione, disclaimer, diagramma dell'architettura,
  installazione e dettagli tecnici in un solo file, invece dei due separati di
  prima. Il disclaimer di non-responsabilità e la nota sull'integrazione API non
  testata sono ora ben visibili anche nel README del pacchetto.

## 1.12.0 — 24 luglio 2026

### Novità

- **Disclaimer di non-responsabilità in evidenza** nella scheda Secondo parere e
  nel README: AHIA è fornita così com'è, senza garanzie; chi l'ha realizzata non
  si assume responsabilità per dati personali condivisi con terze parti, per
  bug o malfunzionamenti propri o di componenti di terze parti, né per un uso
  errato. L'app è pensata perché nulla esca dal computer, ma questo non è
  garantibile a priori.
- **Copia negli appunti** del testo del secondo parere con un pulsante dedicato
  che mostra «Copied!» alla conferma.
- Il README segnala esplicitamente che **l'integrazione con i modelli di
  frontiera tramite chiave API non è testata** contro i servizi reali.

## 1.11.2 — 24 luglio 2026

### Correzioni

- **La sintesi locale non compariva nel testo del secondo parere.** Premendo
  «Aggiungi una sintesi locale» la sintesi veniva generata ma il riquadro del
  testo da inviare non si aggiornava: l'area di testo restava agganciata al
  contenuto precedente. Ora aggiungere o rimuovere la sintesi aggiorna subito il
  testo, e le modifiche manuali restano finché non cambi la sintesi o i parametri.

## 1.11.1 — 24 luglio 2026

### Correzioni

- **Doppia estrazione sui laboratori con scheda nota.** Quando un laboratorio
  aveva già una scheda di lettura, il referto veniva classificato ed estratto
  due volte — un raddoppio di tempo inutile. Ora la scheda viene applicata già
  alla prima e unica estrazione: una sola classificazione, una sola estrazione.

- **Errore sui PDF scansionati.** La classificazione di un documento scansionato
  usava per errore il modello di solo testo, che rifiuta le immagini
  («model does not support multimodal requests»). Ora le scansioni vengono
  classificate con il modello vision.

## 1.11.0 — 24 luglio 2026

### Novità

- **Controllo dei modelli prima di elaborare.** Se un modello scelto non è
  installato in Ollama, l'app lo dice subito con il comando per scaricarlo,
  invece di scoprirlo dopo minuti di attesa a metà elaborazione.

- **Segnale di attività nel registro.** Durante le chiamate lunghe al modello,
  il registro batte un colpo ogni 20 secondi con i secondi trascorsi, così si
  vede che il processo è vivo e non bloccato.

### Modifiche

- Il modello predefinito per analisi struttura, diagnosi ed estrazione accurata
  passa da `qwen3:32b` a `qwen3:14b`: sta comodo in memoria su una macchina da
  32 GB e va molto più veloce. Il 32B resta selezionabile per chi ha più
  memoria, ma non è più la scelta automatica.

## 1.10.1 — 24 luglio 2026

### Correzioni

- **`no such table: segreti` aprendo il secondo parere su un archivio non
  recente.** La tabella delle chiavi API non veniva creata sui database nati
  prima della 1.6.0: mancava la sua preparazione all'apertura dell'archivio.
  Ora viene creata se assente, senza toccare i dati esistenti.

## 1.10.0 — 24 luglio 2026

### Aspetto

- **Nuova veste grafica, sobria e più leggibile.** Palette clinica attenuata
  con un blu-verde come colore guida, superfici chiare e testo ad alto
  contrasto; niente colori vivaci, per trasmettere calma e ordine. Larghezza di
  lettura contenuta perché il testo non si stiri sugli schermi larghi, titoli
  più ariosi, schede con sottolineatura sulla voce attiva, tabelle con
  intestazione in tinta, barra laterale separata da un bordo morbido. La scelta
  del tema chiaro/scuro resta all'utente.

- Diagramma dell'architettura aggiunto anche al README tecnico, e tabella dei
  moduli aggiornata a tutti i componenti attuali.

## 1.9.1 — 24 luglio 2026

Revisione di sicurezza e prestazioni dopo le ultime aggiunte.

### Sicurezza

- L'importazione degli archivi zip ora rifiuta i file troppo grandi (difesa da
  zip-bomb), i collegamenti simbolici e i percorsi con backslash oltre a quelli
  con risalite e assoluti già bloccati. Nessun file può essere estratto fuori
  dalla cartella dell'utente.
- Verificato che la chiave API non compaia mai nei messaggi d'errore: resta solo
  nelle intestazioni della richiesta.

### Correzioni

- Corretto un carattere tipografico errato (segno più a doppia larghezza) in
  un'etichetta.

## 1.9.0 — 24 luglio 2026

### Novità

- **Esportazione dell'archivio in zip.** Dalla barra laterale, «I miei dati»
  esporta l'intero archivio personale — referti, valori, profilo, dizionario,
  riferimenti — in un file zip. Serve da backup e per spostarsi su un'altra
  installazione: lo zip è già nel formato che l'app si aspetta.

- **Ripristino da archivio esportato.** L'amministratore può ricreare un utente
  a partire da uno zip esportato, dalla scheda Utenti. Utile per il trasloco su
  hardware diverso. Il ripristino rifiuta zip che non siano archivi AHIA e
  percorsi non sicuri.

- **Cancellazione dati più sicura.** Eliminando un utente, l'amministratore può
  prima esportarne l'archivio, e la conferma ora richiede di riscrivere il nome
  utente — non più un solo clic — data l'irreversibilità dell'operazione.

## 1.8.0 — 24 luglio 2026

### Novità

- **Analisi preventiva della struttura dei referti.** Sul primo referto di un
  laboratorio mai visto, il modello più capace ne studia il layout — dove sono
  i valori, gli intervalli, cosa ignorare — e prepara una scheda di lettura che
  il modello di estrazione usa subito. La scheda viene salvata per laboratorio e
  riutilizzata su tutti i referti successivi dello stesso laboratorio, senza
  ripetere l'analisi: il costo del modello grosso si paga una volta per layout,
  non per referto.

  Attiva di default, disattivabile dalla scheda Referti (`ANALISI_STRUTTURA_AUTO`
  in configurazione). Solo il primo referto di ogni laboratorio è più lento; i
  successivi restano veloci. Tutto in locale.

  Completa il ciclo con il recupero già esistente: l'analisi struttura previene
  gli errori a monte, la diagnosi delle estrazioni difficili li corregge a valle
  quando qualcosa sfugge comunque. Le due condividono le stesse schede di layout.

## 1.7.2 — 24 luglio 2026

- La segnalazione dei possibili errori di lettura durante l'analisi è ora
  opzionale: un interruttore nella scheda Analisi, disattivato di default.
  Chi non lo attiva ottiene l'analisi essenziale senza la sezione aggiuntiva.

## 1.7.1 — 24 luglio 2026

### Novità

- **L'analisi rileva i possibili errori di lettura.** Durante l'analisi dei
  referti, il modello segnala in una sezione dedicata i valori che sospetta mal
  estratti — basandosi su incoerenze (valori impossibili, relazioni interne che
  non tornano, un valore che stona con tutto il quadro), non sul semplice essere
  fuori norma. Ogni sospetto diventa un pulsante che avvia la verifica sul testo
  originale del referto, riusando la pipeline di recupero. Il modello alza la
  mano; la verifica va a controllare la fonte. Nessuna correzione automatica.

## 1.7.0 — 24 luglio 2026

### Novità

- **Recupero delle estrazioni difficili.** Quando un referto viene estratto
  male, un pulsante avvia una pipeline in tre fasi, tutta in locale: il modello
  più capace diagnostica cosa è andato storto e propone un'istruzione mirata al
  layout; il modello normale ritenta con quell'istruzione (numero di tentativi
  configurabile con `RITENTATIVI_ESTRAZIONE`); se non basta, il modello grosso
  prende in carico l'estrazione. Nulla lascia la macchina.

  L'utente vede la vecchia e la nuova estrazione affiancate e decide se
  applicarla. Le istruzioni di layout scoperte vengono salvate per laboratorio
  e riutilizzate sui referti successivi dello stesso laboratorio — e col tempo
  diventano il materiale per migliorare i prompt di base.

- **Segnalazione delle estrazioni sospette.** Ogni referto tabellare mostra
  indizi automatici quando qualcosa non torna: valori senza unità, numeri
  assurdi, intervalli di riferimento mancanti, un conteggio di valori molto
  sotto la media dello stesso laboratorio. Sono indizi, non certezze: indicano
  dove vale la pena guardare.

## 1.6.0 — 24 luglio 2026

### Novità

- **Invio diretto del secondo parere a Claude o ChatGPT.** Oltre a scaricare o
  copiare il quesito, ora è possibile inviarlo a un modello di frontiera con la
  propria chiave API. La risposta compare nell'app, con l'avvertenza che vale
  come le altre risposte — supporto alla comprensione, non parere medico.

  Il momento di verifica resta intatto: l'invio è il terzo gesto dopo aver
  letto il testo e confermato, mai automatico. La chiave API è cifrata con una
  chiave derivata dalla password dell'utente e salvata nel suo archivio — non
  leggibile senza la password, nemmeno dall'amministratore; reimpostando la
  password va reinserita. Le chiamate consumano il credito del proprio account
  presso il fornitore.

  Con questa funzione, quando la usi, i dati anonimizzati lasciano la macchina
  e valgono le condizioni del servizio scelto: è scritto nell'app, prima
  dell'invio.

## 1.5.3 — 24 luglio 2026

### Migliorie

- **Quesito del secondo parere più efficace.** Il testo generato per il modello
  esterno ora assegna un ruolo esplicito (medico internista che commenta per un
  collega), chiede letture d'insieme e pattern tra esami invece di commenti
  valore per valore, pone vincoli precisi — niente diagnosi né terapie,
  distinguere i dati dalle ipotesi, non drammatizzare né rassicurare oltre
  quanto i numeri consentono — e specifica la struttura della risposta con le
  domande per il medico in chiusura. Sono gli accorgimenti che fanno la
  differenza nella qualità di una risposta da un modello di frontiera.

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
