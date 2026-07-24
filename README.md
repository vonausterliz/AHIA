# AHIA

*Archivio e lettura dei tuoi referti.*

App web locale per archiviare i propri referti di laboratorio, seguirne
l'andamento nel tempo e ragionarci sopra con un LLM che gira sulla stessa
macchina. Nessun dato esce dal computer: niente API esterne, niente telemetria.

## Versioni

La versione corrente è indicata nella barra laterale e in `config.py` (`VERSIONE`).
Le modifiche di ciascun rilascio sono in `CHANGELOG.md`.

## Requisiti

- Python 3.10+
- [Ollama](https://ollama.com) in esecuzione in locale
- GPU consigliata (con 12 GB di VRAM i modelli sotto girano interamente in memoria video)

Funziona su macOS, Linux e Windows. Tutte le dipendenze hanno wheel
precompilate per i tre sistemi, quindi l'installazione non compila nulla.

> [!NOTE]
> Sviluppato e collaudato su macOS. Su Linux dovrebbe funzionare senza
> problemi — condivide con macOS le fondamenta Unix — ma non l'ho ancora
> verificato di persona. Il supporto Windows è implementato (script `.bat`,
> percorsi portabili, nomi file sanificati) ma non provato su un sistema
> reale. Riscontri su Linux e Windows sono benvenuti nella
> [issue dedicata](../../issues).


## Installazione

Scompatta l'archivio, entra nella cartella e lancia lo script, che crea il
virtualenv, installa le dipendenze e avvia l'app.

**macOS e Linux**

```bash
cd ahia && ./avvia.sh
```

**Windows** — doppio clic su `avvia.bat`, oppure da prompt:

```bat
cd ahia && avvia.bat
```

A mano, se preferisci:

```bash
cd ahia && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && streamlit run app.py
```

```bat
cd ahia && python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt && streamlit run app.py
```

I modelli vanno scaricati una volta sola. Puoi farlo dal terminale:

```bash
ollama pull qwen3:14b && ollama pull qwen2.5vl:7b
```

oppure dall'app: se un modello selezionato non risulta installato, sotto al
selettore compare un pulsante **⬇︎ Scarica** che esegue il pull via API
mostrando l'avanzamento. Non parte da solo — un modello può pesare parecchi
gigabyte, quindi la decisione resta tua.

L'app risponde su `http://localhost:8501`.

## Struttura

| File | Ruolo |
|---|---|
| `app.py` | interfaccia Streamlit, sei schede |
| `core.py` | SQLite, profilo, impostazioni, contesto per l'LLM, client Ollama |
| `ingest.py` | lettura PDF, estrazione strutturata, normalizzazione |
| `grafici.py` | serie storiche e grafici Altair |
| `config.py` | percorsi, funzioni LLM, conversioni di unità, dizionario di base |
| `avvia.sh` | crea il venv, installa, avvia |

## Dove finiscono i dati

Tutto in `~/.ahia` — su Windows `C:\Users\<utente>\.ahia` — modificabile con
la variabile d'ambiente `AHIA_DATA_DIR`.
Se esiste una cartella `~/.salute-locale` della versione precedente,
viene rinominata automaticamente al primo avvio, quindi non perdi nulla:

| File | Contenuto |
|---|---|
| `salute.db` | SQLite: profilo, risultati, conversazioni |
| `referti/` | copia dei PDF caricati |
| `alias_analiti.json` | dizionario personale delle diciture |

Per il backup basta copiare questa cartella. Se la macchina è condivisa,
valuta un filesystem cifrato: il database non è protetto da password.

## Come funziona

**Tipologie.** Ogni documento viene prima classificato: analisi del sangue,
delle urine, altri esami di laboratorio, ecografia, radiografia, TAC/risonanza,
cardiologia, visita specialistica, ricovero, altro. La distinzione che conta è
tra referti *tabellari*, da cui si estraggono i valori numerici, e referti
narrativi, di cui si conserva una sintesi con le conclusioni. La tipologia si
può forzare al caricamento o correggere dopo, dall'archivio: la classificazione
automatica sbaglia, e correggerla non richiede di rileggere il PDF.

Le sintesi dei referti narrativi entrano nel contesto dell'analisi, così il
modello legge i valori di laboratorio sapendo che c'è stata un'ecografia con
certe conclusioni.

**Estrazione.** Ogni PDF viene classificato automaticamente: se ha uno strato
di testo utile lo legge `pdfplumber` e passa il testo al modello testuale, se è
una scansione viene rasterizzato a 300 DPI e dato in pasto al modello vision,
una pagina per chiamata. In entrambi i casi l'estrazione è vincolata a uno
schema JSON con `temperature: 0`.

**Dizionario assistito.** Nella scheda Dizionario il pulsante *Proponi con
l'LLM* fa suggerire al modello a quale nome canonico ricondurre le diciture
nuove, riusando quelli già in uso quando l'esame è lo stesso. Le proposte
compaiono precompilate nei campi, con una nota dove il modello ha un dubbio: le
correggi e le salvi tu. Il dizionario salvato resta l'unica cosa applicata ai
dati, così le serie storiche non cambiano da sole tra un caricamento e l'altro.

**Normalizzazione.** Le diciture dei laboratori vengono ricondotte a nomi
canonici tramite il dizionario; le unità note (mmol/L, µmol/L…) vengono
convertite insieme ai range di riferimento. Le diciture nuove non bloccano
nulla: finiscono nella scheda *Dizionario*, dove le mappi e riapplichi la
mappatura alle righe già salvate senza rilanciare l'estrazione.

**Idempotenza.** SHA-256 sul file e vincolo unico su (data, laboratorio,
analita, dicitura): puoi ricaricare gli stessi PDF quante volte vuoi.

**Andamenti.** Scegli gli indicatori da tracciare. Cosa compare all'apertura
si imposta dal pulsante *All'avvio*: gli indicatori fuori norma nell'ultimo
referto, gli ultimi che avevi aperto, oppure un elenco fisso che decidi tu e
resta quello. La scelta è salvata nel database e li vedi in tre modalità: un grafico per indicatore
con la banda di riferimento in trasparenza e i punti colorati per stato; un
confronto normalizzato che rapporta ogni valore al proprio intervallo, così
indicatori con unità diverse stanno sullo stesso asse; una mappa
indicatore × prelievo per cogliere a colpo d'occhio quando le cose si sono
mosse. Sotto, la tabella delle variazioni rispetto al prelievo precedente e al
primo disponibile, esportabile in CSV.

**Ragionamento (thinking).** I modelli che ragionano prima di rispondere
(qwen3, deepseek-r1) emettono il ragionamento nel campo `thinking`, separato dal
testo finale: durante quella fase il riquadro della risposta resterebbe vuoto
anche per minuti. L'app lo mostra in un pannello "Il modello sta ragionando…"
che si chiude quando comincia la risposta vera. Il parametro `think` è definito
per funzione in `config.py` — attivo per l'analisi, spento per estrazioni e
chat, dove la latenza pesa più della qualità. Sui modelli che non lo supportano
la chiamata viene rifatta automaticamente senza il parametro.

**Ricerca e recupero.** Il testo estratto da ogni documento viene conservato:
è la base sia della ricerca sia dell'indice, e senza di esso l'unica traccia di
un'ecografia sarebbe la sintesi del modello, per definizione parziale.

Sopra ci sono due meccanismi. *Parole* usa l'indice FTS5 di SQLite: esatto,
istantaneo, nessuna dipendenza aggiuntiva, e trova tutte le occorrenze.
*Significato* usa gli embedding: trova "steatosi epatica" cercando "fegato
grasso", cosa che in italiano medico capita spesso. Richiede un modello di
embedding multilingue — `bge-m3` è quello consigliato — e un'indicizzazione una
tantum dalla barra laterale.

I valori di laboratorio **non** vengono vettorizzati. Le domande che si fanno ai
numeri sono ordinamenti, confronti e differenze, cioè SQL; e una ricerca
vettoriale restituisce i k risultati più simili senza garantire di averli
trovati tutti, il che su una serie storica è esattamente il difetto da evitare.

Quando l'indice esiste, il contesto di *Analisi* e *Chat* non include più le
sintesi generiche degli ultimi N referti narrativi ma i passaggi più pertinenti:
per l'analisi guidati dai valori fuori norma, per la chat dalla domanda posta.
Sono più mirati e più fedeli, perché sono il testo originale invece di un
riassunto. Sotto una soglia di affinità non viene incluso nulla, così una
ricerca a vuoto non riempie il contesto di rumore.

**Numeri già calcolati.** Il contesto include una tabella con differenze
assolute e percentuali, minimo, massimo, numero di misurazioni e quante volte
ogni esame è uscito dal range — calcolati in Python su tutto l'archivio, non
solo sui referti nel contesto. È la classe di errori più comune quando si
chiede a un modello di fare aritmetica su una tabella: qui non deve farla.

**Strumenti nella chat.** Se attivi (interruttore nella barra laterale), il
modello può interrogare l'archivio invece di limitarsi a ciò che vede:
`serie_analita`, `confronta_date`, `conta_fuori_range`, `cerca_nei_referti`.
Nessuno strumento accetta SQL libero, i nomi degli esami vengono risolti contro
il dizionario e contro quelli realmente presenti ("glicemia" diventa
`GLUCOSIO`), e i calcoli li fa la funzione: il modello riceve risultati, non
dati da elaborare. Il ciclo si ferma dopo tre giri e chiede comunque una
risposta, così un modello che gira a vuoto non blocca la chat. Ogni
interrogazione è visibile in un pannello sotto la risposta.

Vanno disattivati sui modelli che non supportano il tool calling, e conviene
disattivarli su macchine lente: ogni giro è una generazione completa.

**Catalogo dei riferimenti.** Facoltativo, dalla scheda Dizionario. Completa
gli intervalli che il laboratorio non ha stampato, con valori indicativi per
adulti distinti per sesso. Non tocca mai gli intervalli del referto, si applica
solo a parità di unità di misura, e l'origine resta visibile ovunque: banda blu
nei grafici, asterisco nelle tabelle, nota nel contesto del modello. Estendibile
con `riferimenti_personali.json` nella cartella dati.

**Cosa misura un esame.** Accanto a ogni indicatore c'è un collegamento alla
scheda di [labtestsonline.it](https://labtestsonline.it), il portale
divulgativo di SIBioC. L'app conserva solo gli indirizzi: i contenuti sono
coperti da licenza e restano sul sito della fonte, sempre aggiornati.

**Log.** In fondo alla scheda Referti ci sono due pannelli. *Metriche
dell'ultima elaborazione* riporta, per ogni chiamata al modello, durata totale,
tempo di caricamento, token in ingresso e uscita, velocità di generazione ed
esami estratti — utile per capire se un'estrazione lenta dipende dal modello,
dal caricamento in memoria o da pagine rasterizzate troppo grandi. *Log del
server Ollama* mostra la coda di `~/.ollama/logs/server.log` quando il file
esiste; con systemd il log sta nel journal e il pannello indica il comando da
usare.

**Modelli per funzione.** Nella barra laterale ogni funzione ha il proprio
modello, e la scelta viene salvata nel database: estrazione da PDF nativi,
estrazione da scansioni (solo modelli multimodali), analisi e chat. Anche
`temperature` e `num_ctx` sono definiti per funzione in `config.py` — 0 per le
estrazioni, che devono trascrivere, più alti per analisi e chat. Aggiungere una
funzione significa aggiungere una voce a `FUNZIONI`.

Su una macchina con memoria abbondante la configurazione tipica è un modello
medio e veloce per le estrazioni e il più capace disponibile per l'analisi, che
gira una volta sola e può permettersi di essere lenta.

**Analisi e chat.** Il contesto passato al modello è una tabella compatta con
profilo, ultimo valore, range e valori precedenti per ogni analita — non i PDF
grezzi. Lo vedi per intero nell'expander prima di generare, e il numero di
referti inclusi si regola dalla barra laterale.

## Avvertenza

Al primo avvio l'app mostra un'avvertenza che va letta e accettata prima di
poter fare qualsiasi cosa: AHIA è uno strumento sperimentale, non un dispositivo
medico, non fornisce diagnosi e non sostituisce il parere del medico. Il testo
resta consultabile dal pulsante *Avvertenza e limiti d'uso* nella barra
laterale.

L'accettazione è registrata con il numero di versione del testo
(`DISCLAIMER_VERSIONE` in `config.py`): alzandolo, l'avvertenza viene
ripresentata anche a chi l'aveva già accettata.

## Secondo parere

Un modello locale da 14B non regge il confronto con un modello di frontiera su
compiti di ragionamento clinico. La scheda *Secondo parere* prepara un quesito
da sottoporre a un modello esterno passando il minimo indispensabile:

- nome del profilo, laboratorio e nomi dei file: **sempre esclusi**
- date dei prelievi: sostituite da intervalli relativi (T0, +12 mesi…), che
  conservano l'andamento senza collocarlo nel tempo
- età: per impostazione predefinita solo la fascia quinquennale
- altezza e peso: al loro posto il solo BMI, se scelto
- terapie e note del profilo: escluse salvo scelta esplicita, perché sono testo
  libero ed è lì che finiscono nomi, luoghi e dettagli identificativi

Il testo finale è **modificabile e va confermato**: un controllo automatico
segnala codici fiscali, email, telefoni, date in chiaro, indirizzi e il nome
del profilo, ma l'ultima lettura spetta a chi invia. Finché la conferma non è
spuntata, i pulsanti per scaricarlo o copiarlo restano disabilitati. Nulla parte
automaticamente: il trasferimento è un gesto manuale.

Facoltativamente si può allegare una sintesi prodotta dal modello locale,
etichettata come non verificata proprio perché il modello esterno la controlli
invece di darla per buona.

## Sicurezza

L'accesso richiede un'utenza. Al primo avvio viene chiesto di creare
l'amministratore; in alternativa si possono usare le variabili d'ambiente
`AHIA_ADMIN_USER` e `AHIA_ADMIN_PASSWORD` per un'installazione automatizzata.

Le password sono conservate come impronta scrypt con sale casuale per utente,
mai in chiaro. Cinque tentativi falliti sospendono l'accesso per quindici
minuti. La sessione vive nella scheda del browser: chiudendola o ricaricando la
pagina si torna alla schermata di accesso.

**Ogni utente vede solo i propri dati.** Non per via di un filtro nelle query,
ma perché ogni utente ha un database e una cartella di referti propri, sotto
`~/.ahia/archivi/<id>/`. Un errore in una query non può far trapelare i dati di
un altro: sono file diversi. Questo vale anche per l'amministratore, che
gestisce le utenze ma non accede ai loro archivi.

L'app ascolta solo su `localhost` (`.streamlit/config.toml`). Esporla in rete
richiede almeno HTTPS davanti: il login viaggerebbe altrimenti in chiaro.

Il database non è cifrato. Chiunque abbia accesso all'utente del sistema legge
l'archivio: se la macchina è condivisa, usa un filesystem cifrato e punta
`AHIA_DATA_DIR` lì.

I PDF sono dati non fidati. Il testo estratto finisce nel database, nei grafici
e nel prompt del modello, quindi vale la pena sapere che:

- i nomi dei file vengono sanificati prima di essere scritti su disco;
- tutte le query usano parametri, mai concatenazione di stringhe;
- l'interfaccia non interpreta HTML proveniente dai dati estratti;
- **un PDF costruito ad arte può però influenzare il modello** con istruzioni
  nascoste nel testo. L'effetto è limitato — il modello non esegue codice e gli
  strumenti accettano solo query predefinite — ma una sintesi può essere
  manipolata. Carica referti che provengono dal tuo laboratorio.

`OLLAMA_HOST` accetta solo `http://` e `https://`, così una variabile
d'ambiente ostile non può far leggere file locali.

## Limiti da tenere presenti

Se un modello manca, l'errore lo dice esplicitamente (`model not found`) invece
di mostrare un codice HTTP: il messaggio del server viene tradotto e riportato
nell'interfaccia.

L'estrazione va verificata sul primo referto di ogni laboratorio nuovo: i
layout cambiano e un valore letto male entra nel database senza segnalarlo.

Il modello non fa diagnosi. Non conosce la storia clinica, il motivo della
prescrizione né l'esame obiettivo, e su un 14B le interpretazioni cliniche sono
plausibili ma non affidabili. È uno strumento per vedere gli andamenti e
arrivare preparati dal medico.

