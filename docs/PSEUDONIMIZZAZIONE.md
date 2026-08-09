# Pseudonimizzazione del secondo parere

Stato: specifica di progetto con MVP delle fasi 2-4 implementato

Ambito: funzionalita' **Secondo parere**

Implementazione: `pseudonimizzazione.py`, `presidio_ahia.py` e flusso Secondo
parere in `app.py`

Sono implementati il motore reversibile, i recognizer AHIA, l'adapter Presidio
italiano opzionale, i token opachi, la conferma vincolata all'impronta, la
segnalazione manuale per la richiesta corrente e la reidratazione dei percorsi
diretto e manuale. Restano rinviati le regole personali persistenti, l'export di
casi di miglioramento, la revisione dei falsi positivi e il benchmark completo
con Presidio installato.

## 1. Obiettivo

Prima di inviare a un modello esterno il quesito per il secondo parere, AHIA
deve sostituire localmente i dati identificativi con token casuali opachi. La
mappa fra token e valori originali non deve uscire dal dispositivo. Quando AHIA
riceve la risposta, deve sostituire localmente i token riconosciuti con i valori
originali.

Questa operazione e' una **pseudonimizzazione reversibile**, non
un'anonimizzazione. I dati inviati restano dati personali e, in particolare,
dati sanitari. La pseudonimizzazione riduce l'esposizione degli identificatori
diretti, ma non rende impossibile identificare una persona attraverso il
contesto o la combinazione di informazioni rare.

Presidio e gli altri rilevatori hanno il compito di individuare gli intervalli
di testo sensibili. AHIA resta responsabile di:

- decidere quali entita' proteggere;
- generare token opachi;
- conservare separatamente la mappa reversibile;
- verificare il payload immediatamente prima dell'invio;
- reidratare la risposta esclusivamente sul dispositivo;
- permettere all'utente di correggere falsi negativi.

## 2. Non obiettivi

La prima versione non deve:

- garantire anonimato o conformita' normativa in ogni scenario;
- rimuovere diagnosi, farmaci, dosaggi, procedure o risultati clinici utili;
- consentire la reidentificazione al fornitore del modello esterno;
- archiviare in modo permanente le mappe delle singole richieste;
- correggere in modo euristico token modificati dal modello;
- inviare automaticamente segnalazioni, estratti clinici o telemetria;
- pseudonimizzare i PDF originali o l'intero archivio AHIA.

## 3. Principi di progetto

1. **Minimizzazione prima della pseudonimizzazione.** Non si invia un dato solo
   perche' puo' essere sostituito in seguito.
2. **Locale per impostazione predefinita.** Rilevazione, tokenizzazione, mappa e
   reidratazione avvengono sul dispositivo che esegue AHIA.
3. **Token privi di semantica.** Il token non rivela se rappresenta un paziente,
   un medico, una struttura o un altro tipo di entita'.
4. **Separazione della mappa.** Il payload e la mappa non devono trovarsi nello
   stesso canale, log o oggetto serializzato verso l'esterno.
5. **Conferma legata al contenuto.** La conferma dell'utente vale solo per
   l'esatta versione del payload verificato.
6. **Fail closed sull'invio diretto.** Se la verifica avanzata richiesta dalla
   configurazione non e' disponibile o fallisce, l'invio viene bloccato.
7. **Correzione umana come funzione di sicurezza.** Un falso negativo segnalato
   deve essere corretto prima dell'invio e puo' diventare, su scelta esplicita,
   una regola personale locale.
8. **Nessuna falsa rassicurazione.** L'interfaccia deve distinguere fra
   "nessuna PII rilevata" e "assenza garantita di PII"; la seconda non e'
   dimostrabile.

### 3.1 Sostituzione del meccanismo attuale

La pseudonimizzazione sostituisce, nel secondo parere, l'attuale oscuramento
irreversibile implementato da `oscura_testo()` e il successivo controllo
separato di `verifica()`. Non devono restare due pipeline autonome che
trasformano lo stesso testo in sequenza: renderebbero difficile ricostruire la
mappa, spiegare le modifiche e misurare falsi positivi e falsi negativi.

Le espressioni regolari gia' presenti in AHIA non vengono scartate: diventano
**rilevatori** della nuova pipeline. Invece di sostituire direttamente un valore
con etichette come `[nome]`, `[data]` o `[identificativo]`, restituiscono uno
span tipizzato che il motore centrale tratta secondo la tassonomia: token
reversibile, generalizzazione oppure conservazione.

Resta separata e viene conservata la minimizzazione strutturale che evita di
inserire nel quesito dati non necessari, in particolare nomi di file,
laboratorio, date assolute dei prelievi e data di nascita. Questa logica non e'
una seconda anonimizzazione del testo libero: stabilisce a monte quali dati
servono davvero al secondo parere.

## 4. Flusso funzionale

### 4.1 Preparazione

1. AHIA costruisce il quadro clinico applicando soltanto la minimizzazione
   strutturale: esclusione di nomi di file e laboratori, fascia di eta' e
   timeline relativa. Non applica prima l'oscuramento testuale legacy.
2. Tutti i campi liberi, incluse terapie e note, entrano nell'unica pipeline di
   rilevazione e pseudonimizzazione.
3. I rilevatori producono intervalli, tipo locale, punteggio e fonte.
4. AHIA risolve sovrapposizioni e applica la politica definita in questo
   documento.
5. Le entita' reversibili ricevono token casuali opachi; le altre vengono
   generalizzate o lasciate inalterate.
6. AHIA mostra all'utente l'esatto payload destinato all'esterno.

### 4.2 Revisione e congelamento

1. L'utente puo' modificare il payload e segnalare PII non rilevate.
2. Qualsiasi modifica invalida la conferma precedente.
3. Al comando di invio AHIA riesegue la rilevazione sul testo esatto presente
   nell'editor.
4. Se vengono effettuate nuove sostituzioni, il nuovo payload viene mostrato e
   richiede una nuova conferma; non viene inviato nello stesso gesto.
5. AHIA calcola un'impronta crittografica del payload confermato.
6. L'invio e' consentito soltanto se l'impronta del testo corrente coincide con
   quella confermata.

### 4.3 Risposta e reidratazione

1. AHIA riceve la risposta pseudonimizzata.
2. Estrae tutti i token nel formato riservato.
3. Sostituisce soltanto i token presenti esattamente nella mappa della
   richiesta.
4. Token sconosciuti, duplicati in modo anomalo o apparentemente corrotti
   restano visibili e generano un avviso.
5. La risposta reidratata viene mostrata localmente.
6. La mappa temporanea viene eliminata quando non e' piu' necessaria.

Per il percorso manuale copia/incolla, la mappa puo' vivere nella sola sessione
Streamlit e AHIA deve offrire un campo in cui incollare la risposta. Ricaricare
o chiudere la sessione puo' rendere impossibile la reidratazione; questo limite
deve essere comunicato prima della copia.

## 5. Formato dei token

Il token deve contenere solo entropia casuale e delimitatori riconoscibili, ad
esempio:

```text
[[4E91A75C820DF63B18A05CC7]]
```

Requisiti:

- almeno 96 bit generati con un generatore crittograficamente sicuro;
- nuovo spazio di token per ogni richiesta;
- nessun tipo, ruolo, ID utente o contatore osservabile;
- stesso valore normalizzato -> stesso token nella richiesta corrente;
- lo stesso valore deve ricevere un token diverso in richieste diverse;
- il formato riservato non deve essere accettato nel testo sorgente senza
  escaping o rigenerazione;
- la mappa e' orientata `token -> valore originale`; eventuali indici inversi
  restano esclusivamente in memoria.

Non devono essere usati hash deterministici del valore, perche' permetterebbero
correlazioni fra richieste e attacchi a dizionario su nomi o identificativi.

Il modello esterno puo' sapere soltanto che le sequenze `[[...]]` sono token
opachi da copiare esattamente. Non deve ricevere la loro categoria o la mappa.

## 6. Tassonomia e trattamento

La categoria e' metadato locale: non compare nel token inviato.

| Categoria locale | Esempi | Trattamento predefinito |
|---|---|---|
| `PAZIENTE` | nome, cognome, iniziali riconducibili | token reversibile |
| `PERSONA` | familiare, caregiver, referente | token reversibile |
| `MEDICO` | curante, firmatario, specialista | token reversibile |
| `STRUTTURA` | ospedale, studio, laboratorio | token reversibile |
| `LOCALITA` | comune, citta', luogo di nascita | token reversibile o generalizzazione |
| `INDIRIZZO` | via, civico, CAP | token reversibile |
| `CONTATTO` | telefono, email | token reversibile |
| `CODICE_FISCALE` | codice fiscale italiano | token reversibile; normalmente non necessario |
| `IDENTIFICATIVO_SANITARIO` | tessera, cartella, nosologico, episodio | token reversibile; normalmente non necessario |
| `IDENTIFICATIVO_DOCUMENTO` | referto, pratica, accettazione | token reversibile; normalmente non necessario |
| `DATA_NASCITA` | data di nascita completa | fascia di eta', non reidratare |
| `DATA_CLINICA` | prelievo, ricovero, dimissione | timeline relativa, non reidratare |
| `ETA` | eta' esatta | fascia, salvo scelta motivata dell'utente |
| `ALTRO_PII` | identificatore non classificato | token reversibile e avviso |

Devono essere preservati, salvo decisione esplicita differente:

- patologie, sintomi e storia clinica;
- farmaci, principi attivi, dosaggi e terapie;
- procedure e dispositivi descritti in senso clinico;
- analiti, valori, unita' e intervalli di riferimento;
- sesso biologico quando necessario all'interpretazione;
- intervalli temporali relativi clinicamente utili.

Le entita' mediche rilevabili da modelli NER non devono essere trattate come PII
solo perche' descrivono salute. L'obiettivo del secondo parere richiede che il
contenuto clinico rimanga disponibile.

## 7. Rilevatori e precedenza

Ordine logico iniziale:

1. PII personali ricordate esplicitamente dall'utente;
2. valori e alias noti dal profilo locale;
3. recognizer deterministici AHIA per formati italiani e sanitari;
4. recognizer Presidio configurati per l'italiano;
5. modello NER italiano per persone, luoghi e organizzazioni;
6. correzioni manuali della richiesta corrente.

I recognizer deterministici del punto 3 derivano anche dalle regex di
`parere.py`, ma non effettuano sostituzioni autonome. `oscura_testo()` e
`verifica()` vengono rimossi dal flusso del secondo parere quando la nuova
pipeline raggiunge la parita' funzionale prevista dai criteri di accettazione.

Ogni risultato deve includere almeno:

- `start` ed `end` nel testo originale;
- tipo locale;
- punteggio normalizzato;
- fonte del rilevamento;
- eventuale spiegazione tecnica non contenente il valore in log.

Regole di fusione:

- una correzione esplicita dell'utente ha precedenza;
- un valore noto dal profilo ha precedenza sul NER;
- checksum e formati validati hanno precedenza sui pattern deboli;
- in caso di sovrapposizione si preferisce lo span completo piu' specifico;
- gli intervalli finali non possono sovrapporsi;
- i falsi positivi che eliminerebbero informazione clinica devono poter essere
  deselezionati dall'utente prima dell'invio.

## 8. Segnalazione di PII non rilevata

L'anteprima deve offrire il comando **Segnala un dato non rilevato**.

Procedura:

1. L'utente inserisce o seleziona il valore sfuggito.
2. AHIA verifica che compaia nel testo non ancora inviato.
3. AHIA mostra tutte le occorrenze con un breve contesto locale.
4. L'utente seleziona le occorrenze da proteggere.
5. La categoria e' facoltativa e resta locale.
6. AHIA assegna un token opaco e invalida la conferma precedente.
7. L'utente sceglie l'ambito della segnalazione.

Ambiti:

- **questa richiesta**: regola conservata soltanto nella mappa corrente;
- **questo utente**: valore o alias cifrato e riutilizzato nelle richieste
  successive, modificabile e cancellabile dall'utente;
- **esporta caso di miglioramento**: pacchetto locale, gia' privato del valore
  reale e mostrato integralmente prima del salvataggio manuale.

Non sono consentiti upload o telemetria automatici. Il pacchetto di
miglioramento non deve contenere la PII segnalata. Anche il contesto clinico
residuo puo' essere sensibile: l'esportazione richiede ulteriore revisione e
consenso esplicito.

Per evitare sostituzioni eccessive, stringhe brevi o ambigue richiedono sempre
la selezione delle singole occorrenze. Deve esistere un limite di lunghezza per
impedire di salvare accidentalmente un intero referto come singola PII.

## 9. Ciclo di vita e persistenza

### Mappa della richiesta

- vive nella sessione del singolo utente;
- e' associata a un ID richiesta non predicibile e all'impronta del payload;
- non viene salvata nei messaggi della conversazione o nei log;
- non viene inclusa in export o backup ordinari;
- viene eliminata dopo la reidratazione e quando la richiesta viene annullata;
- non puo' essere riutilizzata da un altro utente o da un'altra richiesta.

### PII personali ricordate

- sono separate per archivio utente;
- richiedono scelta esplicita;
- devono essere cifrate a riposo o soggette almeno allo stesso livello di
  protezione delle altre informazioni identificative dell'archivio;
- devono supportare elenco, modifica, disattivazione ed eliminazione;
- non contengono mappe di risposte precedenti;
- la reimpostazione della password e il recupero devono avere un comportamento
  documentato se la cifratura dipende dalla password.

## 10. Modello delle minacce

| Minaccia | Conseguenza | Contromisure richieste |
|---|---|---|
| Falso negativo del rilevatore | PII inviata in chiaro | rilevatori stratificati, revisione, segnalazione manuale, scansione finale |
| Falso positivo | perdita di utilita' clinica | anteprima, tassonomia, deselezione controllata, corpus negativo |
| Modifica dopo la conferma | invio di testo non verificato | hash del payload e invalidazione automatica |
| Mappa inclusa nel payload/log | reidentificazione esterna | oggetti separati, logging privo di valori, test anti-leak |
| Token semantico | rivelazione del ruolo | token casuale senza categoria o contatore |
| Token deterministico fra richieste | correlazione dell'identita' | casualita' per richiesta |
| Collisione con testo sorgente | sostituzione o reidratazione errata | formato riservato, controllo preventivo, alta entropia |
| Token inventato dall'LLM | sostituzione indebita | allow-list esatta della mappa; sconosciuti lasciati visibili |
| Token modificato dall'LLM | risposta parzialmente non reidratabile | nessun fuzzy matching; avviso e testo originale disponibile |
| Prompt injection nel referto | manipolazione dell'LLM | delimitazione del contenuto, istruzioni sui token, revisione utente |
| Accesso incrociato fra utenti | esposizione della mappa | isolamento per sessione e archivio, nessuna cache globale delle mappe |
| Riutilizzo della mappa | correlazione fra richieste | ID e nonce per richiesta, distruzione a fine ciclo |
| Esportazione di feedback reale | diffusione di PII o dati sanitari | nessun upload automatico, sanitizzazione e anteprima obbligatoria |
| Indisponibilita' di Presidio | protezione degradata senza avviso | stato visibile; blocco in modalita' strict |
| Compromissione del dispositivo | lettura dei dati locali | fuori dalla garanzia del motore; filesystem protetto e controllo accessi |
| Reidentificazione dal quadro clinico raro | identificazione indiretta | minimizzazione, generalizzazione e avvertenza esplicita |

Il fornitore esterno puo' inferire che token diversi rappresentano entita'
diverse e puo' dedurne il ruolo dal contesto (per esempio "visitato da
[[...]]"). Nascondere completamente il ruolo richiederebbe riscrivere il testo
e potrebbe ridurre l'utilita' clinica. La politica predefinita nasconde il
valore e non codifica il ruolo nel token, ma conserva il contesto clinicamente
necessario.

## 11. Esperienza utente richiesta

L'interfaccia deve mostrare:

- motori di rilevazione effettivamente attivi;
- numero di sostituzioni, generalizzazioni e avvisi;
- payload esatto destinato all'esterno;
- comando per mostrare le sostituzioni senza esporre inutilmente la mappa;
- comando per segnalare PII non rilevata;
- stato della conferma e motivo dell'eventuale invalidazione;
- avviso se il percorso manuale perdera' la mappa alla chiusura della sessione;
- avviso che la risposta reidratata e il relativo download contengono di nuovo
  dati personali.

Messaggi vietati:

- "testo anonimo";
- "privacy garantita";
- "nessun dato personale presente".

Formulazioni ammesse:

- "Nessun ulteriore identificatore rilevato dai controlli attivi";
- "Payload pseudonimizzato da rileggere";
- "La pseudonimizzazione non impedisce ogni possibile reidentificazione".

## 12. Errori e comportamento degradato

- Se Presidio non e' installato, AHIA indica chiaramente che sono attivi solo i
  controlli di base.
- In modalita' strict, indisponibilita', timeout o errore del motore bloccano
  l'invio diretto.
- Un errore non deve includere testo clinico, token associati a valori o valori
  originali.
- Se la mappa e' persa, AHIA mostra la risposta pseudonimizzata e dichiara che
  non puo' reidratarla; non tenta ricostruzioni probabilistiche.
- Se la risposta contiene tag alterati, AHIA conserva il testo ricevuto e
  segnala le posizioni sospette.
- Se la scansione finale modifica il payload, l'invio si ferma e richiede una
  nuova conferma.

## 13. Criteri di accettazione della futura implementazione

### Funzionali

- Token senza categoria, ruolo, contatore osservabile o ID utente.
- Stesso valore mappato coerentemente nella singola richiesta.
- Token differenti per lo stesso valore in richieste distinte.
- Reidratazione esatta per tutti i token integri.
- Token sconosciuti mai sostituiti.
- Segnalazione manuale applicata prima dell'invio.
- Conferma invalidata da qualsiasi modifica o nuova segnalazione.
- PII ricordate isolate per utente e cancellabili.

### Privacy e sicurezza

- Nessun valore della mappa nel payload esterno.
- Nessuna mappa nei log, nel database delle conversazioni o negli errori.
- Nessuna telemetria o esportazione automatica.
- Nessuna sostituzione fuzzy in reidratazione.
- Invio bloccato se hash corrente e hash confermato differiscono.
- Modalita' strict chiusa in caso di errore del rilevatore richiesto.

### Utilita' clinica

- Farmaci, dosaggi, diagnosi, analiti, valori e unita' restano invariati.
- Date strutturate continuano a essere rappresentate come timeline relativa.
- Il testo resta grammaticalmente comprensibile quanto ragionevolmente
  possibile dopo la sostituzione.
- I falsi positivi clinicamente distruttivi sono rilevati dal corpus negativo.

### Qualita' misurabile

- 100% di round-trip sui token integri del corpus.
- 100% sui valori esplicitamente noti dal profilo e segnalati dall'utente.
- 100% sui codici fiscali validi inclusi nel corpus sintetico.
- Recall complessiva obiettivo >= 97% sulle entita' identificative annotate.
- Nessuna perdita dei campi inclusi nelle liste `must_preserve` del corpus.
- Zero occorrenze dei valori `must_not_leak` nei payload prodotti.

Le soglie devono essere misurate separatamente per tipo di entita' e su casi
positivi, negativi difficili, rumore OCR e round-trip con risposte simulate.

## 14. Decisioni rinviate

Richiedono una decisione durante le fasi successive:

- modello NLP italiano e soglie di confidenza per tipo;
- cifratura e recupero delle PII personali ricordate;
- durata massima della mappa nel percorso manuale;
- formato definitivo dei token dopo test con i modelli esterni supportati;
- livello di contesto mostrato nell'interfaccia di segnalazione;
- politica su localita' e strutture: token reversibile o generalizzazione;
- eventuale persistenza cifrata di una richiesta manuale fra riavvii;
- modalita' di produzione e revisione dei casi sintetici esportabili.

## 15. Piano di realizzazione successivo

1. Motore reversibile indipendente da Presidio e relativi test.
2. Conversione delle regex legacy da sostituzioni a recognizer senza effetti
   collaterali.
3. Reidratazione esatta e validazione dei token.
4. Corpus sintetico iniziale e test anti-leak.
5. Adapter Presidio con modello italiano e recognizer AHIA.
6. Interfaccia di revisione e segnalazione dei falsi negativi.
7. Congelamento del payload, invio diretto e reidratazione.
8. Rimozione di `oscura_testo()` e `verifica()` dal flusso del secondo parere
   dopo il superamento dei test di parita'.
9. Percorso manuale copia/incolla.
10. Benchmark, tuning, hardening e rilascio graduale.
