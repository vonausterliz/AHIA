# AHIA

**Archivio e lettura dei referti medici, interamente in locale.**

AHIA prende i PDF dei tuoi referti, ne estrae i valori, li mette in serie
storica e ti lascia ragionarci sopra con un modello linguistico che gira sulla
tua macchina. Per impostazione predefinita nessun dato lascia il computer: i modelli ordinari girano in locale e non c’è telemetria. Solo il Secondo parere può inviare un payload pseudonimizzato a un provider esterno, dopo revisione e conferma esplicita.

Nasce come banco di prova per capire cosa un LLM locale sappia realmente fare
su documenti sanitari. È scritto per referti italiani: virgola decimale,
prefissi di matrice (`S-`, `P-`, `U-`), diciture che cambiano da laboratorio a
laboratorio, elettroforesi proteica.

La versione corrente è indicata nella barra laterale e in `config.py`
(`VERSIONE`); le modifiche di ciascun rilascio sono in `CHANGELOG.md`.

---

## Cosa fa

**Archivia i referti.** Carichi i PDF — nativi o scansionati — e l'app
riconosce di che documento si tratta: analisi del sangue, urine, ecografia,
radiografia, TAC, visita specialistica, ricovero. Dai referti con valori
numerici estrae gli analiti; da quelli descrittivi conserva il testo e una
sintesi con le conclusioni.

**Normalizza le diciture.** Ogni laboratorio scrive gli esami a modo suo:
`Glicemia`, `S-Glucosio`, `GLUCOSIO SIERICO` sono lo stesso esame. Un dizionario
li riconduce a un nome unico, altrimenti le serie storiche si spezzano. Le
diciture nuove si mappano a mano, con proposte suggerite dal modello che
confermi tu.

**Mostra gli andamenti.** Grafici temporali con l'intervallo di riferimento in
trasparenza, i punti colorati per stato, un confronto normalizzato che mette
sullo stesso asse esami con unità diverse, e una tabella di variazioni
esportabile.

**Legge i referti con un LLM locale.** Analisi complessiva o su un singolo
referto, e una chat che risponde sui tuoi dati. I calcoli non li fa il modello:
differenze, percentuali e conteggi arrivano già pronti, oppure il modello li
chiede a funzioni che interrogano l'archivio.

**Cerca nell'archivio.** Ricerca esatta e ricerca per significato, perché in
italiano medico cercare "fegato grasso" deve trovare "steatosi epatica".

**Prepara un secondo parere pseudonimizzato.** Un modello locale da 14 miliardi di
parametri non regge il confronto con uno di frontiera sul ragionamento clinico.
L'app compone un quesito da sottoporre a un modello esterno passando il minimo:
niente nome, niente laboratorio, date sostituite da intervalli relativi, età
ridotta a fascia. Gli identificatori riconosciuti diventano token casuali e
opachi; la mappa resta nella sessione locale e AHIA può ripristinare i valori
nella risposta. Il testo parte soltanto dopo una conferma legata al suo esatto
contenuto.

**Gestisce più persone.** Ogni utente ha credenziali proprie e un archivio
fisicamente separato. Nemmeno l'amministratore accede ai dati altrui.

---

## Cosa non fa

Vale la pena essere espliciti, perché è la parte che di solito manca.

**Non è un dispositivo medico.** Non è certificato né validato clinicamente.
Non fornisce diagnosi, prognosi o indicazioni terapeutiche, e nessuna sua
risposta va intesa come parere sanitario.

**Non sostituisce il medico e non deve ritardarne il consulto.** Interpretare
un esame richiede la storia clinica, il motivo della prescrizione, le terapie
in corso e l'esame obiettivo: cose che l'app non ha.

**Non garantisce che l'estrazione sia corretta.** Un modello può spostare una
virgola decimale o attribuire a una riga l'intervallo di riferimento di
un'altra. I valori estratti vanno confrontati con il referto originale, almeno
la prima volta per ogni laboratorio nuovo.

**Non sincronizza niente.** Nessun cloud, nessun backup automatico. La cartella
dei dati è tua da copiare.

**Non è un gestionale sanitario.** Non dialoga con il Fascicolo Sanitario
Elettronico, non importa da provider FHIR, non gestisce prescrizioni o
appuntamenti.

---

## ⚠️ Nessuna garanzia, nessuna responsabilità

> **AHIA è fornita "così com'è", senza garanzie di alcun tipo.**
>
> L'applicazione è progettata perché **nulla lasci il tuo computer** senza un
> tuo gesto esplicito, e perché il quesito del secondo parere sia pseudonimizzato
> prima di qualunque invio. **Questo comportamento non è garantito a priori.**
> Un bug dell'applicazione, di una libreria di terze parti, del motore di
> inferenza o di un servizio esterno, un errore di rilevazione, o un uso
> improprio possono far sì che dati personali — compresi dati sanitari — escano
> dal computer o vengano condivisi con terze parti.
>
> Chi ha realizzato AHIA **non si assume alcuna responsabilità** per dati
> personali condivisi con terze parti, per malfunzionamenti o bug propri o di
> componenti di terze parti, per errori dell'applicazione, né per un utilizzo
> errato o improprio. L'utilizzo avviene **a rischio esclusivo** di chi usa
> l'applicazione. Rileggi sempre ciò che stai per inviare.
>
> L'integrazione con OpenAI, Anthropic e OpenRouter è verificata con provider
> simulati e payload sintetici, ma **non è ancora collaudata contro i servizi
> reali**: potrebbe non funzionare o comportarsi in modo inatteso. Il percorso
> più prudente resta quello manuale — copi il testo e lo incolli tu.

---

## Cosa serve

L'app si appoggia a [Ollama](https://ollama.com) per eseguire i modelli in
locale, e funziona su macOS, Linux e Windows. Serve inoltre Python 3.10 o
successivo; tutte le dipendenze hanno wheel precompilate per i tre sistemi,
quindi l'installazione non compila nulla.

### Modelli

| Modello | A cosa serve | Peso |
|---|---|---|
| `qwen3:8b` / `qwen3:14b` | operazioni rapide e analisi approfondita | ~5 / ~9 GB |
| `qwen3-vl:8b` | lettura delle scansioni (multimodale) | ~6 GB |
| `bge-m3` | ricerca per significato, facoltativa | ~1,2 GB |
| `qwen3:30b-instruct` | analisi più impegnative, se la macchina lo regge | ~19 GB |

In **Impostazioni → Modelli e provider** la modalità automatica rileva localmente
RAM, VRAM o memoria unificata e propone quattro modelli proporzionati alla
macchina. Se un consiglio non è presente, **Da installare** apre un riepilogo e
richiede conferma prima di accodare il download con Ollama. La finestra si
chiude subito; avanzamento e coda restano nel menu mentre continui a usare AHIA.
Le richieste incomplete ripartono al riavvio dell'app, purché Ollama sia attivo.
Nel frattempo AHIA continua a usare un modello compatibile già installato. Sono disponibili tre
priorità: Equilibrato, Più veloce e Massima qualità; la modalità Personalizzata
mantiene la scelta per ruolo e le eccezioni per singola funzione.

OpenAI, Anthropic e OpenRouter espongono il loro elenco aggiornato soltanto su richiesta esplicita. Disponibilità, compatibilità tecnica e validazione clinica restano stati distinti; i dettagli sono in [Configurazione dei modelli](docs/CONFIGURAZIONE_MODELLI.md).

La nuova organizzazione delle pagine e la collocazione delle opzioni sono descritte in [Architettura dell’interfaccia](docs/INTERFACCIA.md).

### Hardware

Il fattore che conta è la memoria disponibile per il modello: se ci sta
interamente, la velocità è accettabile; se deve essere ripartito sulla CPU,
crolla.

| | Memoria | Cosa aspettarsi |
|---|---|---|
| **Minimo** | 16 GB di RAM, solo CPU | Funziona, ma l'estrazione di un referto richiede diversi minuti e la chat è impraticabile. Utile per provare l'app, non per usarla. |
| **Consigliato** | 12 GB di VRAM (es. RTX 3060) oppure 16 GB di memoria unificata su Apple Silicon | I modelli consigliati stanno interamente in memoria: 20-30 token al secondo, estrazione di un referto in 30-60 secondi. |
| **Comodo** | 24 GB di VRAM o 32 GB di memoria unificata | Permette il modello da 32 miliardi di parametri per l'analisi, tenendo quello più piccolo e veloce per estrazione e chat. |

**Spazio su disco**: circa 16 GB per i modelli, più pochi megabyte per
l'archivio — un database con anni di referti resta sotto i 50 MB, i PDF
originali a parte.

Su GPU NVIDIA i modelli girano in CUDA senza configurazione; su Apple Silicon
in Metal, con una resa più bassa nella lettura delle scansioni.

---

## Installazione

### 1. Installa Ollama

AHIA usa [Ollama](https://ollama.com) per eseguire i modelli in locale. Va
installato per primo.

**macOS** — scarica l'app da [ollama.com/download](https://ollama.com/download),
aprila e trascinala nelle Applicazioni. Al primo avvio si installa da sé e resta
attiva nella barra dei menu. In alternativa, con [Homebrew](https://brew.sh):

```bash
brew install ollama
```

**Windows** — scarica l'installer da
[ollama.com/download](https://ollama.com/download) ed eseguilo. Ollama parte
automaticamente e resta nell'area di notifica.

**Linux** — un comando solo:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Per verificare che Ollama sia attivo, apri un terminale e digita `ollama list`:
se risponde (anche con una lista vuota), è pronto. Ollama espone un servizio
locale su `http://localhost:11434`; AHIA vi si collega da sé.

> Su Windows e macOS l'app di Ollama va lasciata in esecuzione mentre usi AHIA.
> Su Linux, se non parte da solo, avvialo con `ollama serve`.

### 2. Scarica i modelli

Una volta sola, dal terminale:

```bash
ollama pull qwen3:14b && ollama pull qwen2.5vl:7b
```

Facoltativo, per la ricerca semantica:

```bash
ollama pull bge-m3
```

Puoi anche non scaricarli ora: se apri AHIA e un modello selezionato non è
installato, l'app te lo segnala con il comando esatto per scaricarlo.

### 3. Avvia AHIA

Scompatta l'archivio, entra nella cartella e lancia lo script, che crea il
virtualenv, installa le dipendenze Python e avvia l'app.

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

L'app risponde su `http://localhost:8501`.

### Spostare AHIA su un altro computer

Per creare uno ZIP del solo programma, senza virtualenv, database, referti,
chiavi o cache locali:

```bash
.venv/bin/python tools/crea_pacchetto.py
```

Trasferisci il file prodotto in `builds/`, installa Ollama sul computer di
destinazione, scompatta lo ZIP e usa `avvia.sh` oppure `avvia.bat`. I modelli
Ollama vanno riscaricati sulla nuova macchina. Il manifest incluso riporta gli
SHA-256 dei file; per sicurezza lo script rifiuta un albero Git con modifiche
non salvate, salvo l'opzione esplicita `--consenti-modifiche` per build di test.

### Presidio italiano (facoltativo ma consigliato)

AHIA funziona anche con i soli recognizer di base. Per aggiungere il NER
italiano e i recognizer di [Presidio](https://github.com/data-privacy-stack/presidio),
installa nel virtualenv il gruppo opzionale e il modello spaCy:

```bash
.venv/bin/python -m pip install -r requirements-presidio.txt
.venv/bin/python -m spacy download it_core_news_lg
```

Su Windows sostituisci `.venv/bin/python` con
`.venv\Scripts\python.exe`. Lo stato effettivo dei motori è mostrato nella
pagina *Secondo parere*. Le variabili `AHIA_PRESIDIO_MODEL` e
`AHIA_PRESIDIO_SCORE` cambiano rispettivamente modello e soglia; con
`AHIA_PRESIDIO_STRICT=1` l'invio diretto è bloccato se Presidio non è attivo.
Una soglia specifica per entità si imposta, per esempio, con
`AHIA_PRESIDIO_SCORE_PERSON` o `AHIA_PRESIDIO_SCORE_LOCATION`.

Il benchmark sintetico completo si esegue con:

```bash
.venv/bin/python tools/benchmark_pii.py --verifica-obiettivi
```

Il benchmark dell’estrazione da testo sintetico si esegue con `.venv/bin/python tools/benchmark_estrazione.py`. Usa tre coppie testo/manifest prodotte realmente da FAKING_MEDDOC 0.2.22. I casi manuali per alias, unità, flag e serie storiche sono conservati in un corpus distinto e testati senza LLM. Provenienza, flusso e risultati misurati sono descritti in [`docs/INTEGRAZIONE_FAKING_MEDDOC.md`](docs/INTEGRAZIONE_FAKING_MEDDOC.md).

Il corpus indipendente, congelato e mai usato per il tuning si esegue
separatamente:

```bash
.venv/bin/python tools/benchmark_pii.py --holdout
```

Il primo risultato e la relativa impronta sono nel
[rapporto holdout](docs/VALIDAZIONE_PII_HOLDOUT.md). Lo smoke test live del
confine Ollama si esegue senza dati reali:

```bash
.venv/bin/python tools/smoke_ollama_pii.py --model qwen3:30b-instruct
```

La scelta del modello, la licenza e i risultati misurati sulla macchina di
sviluppo sono nel [rapporto Ollama](docs/VALIDAZIONE_OLLAMA.md).

---

## Come funziona

Quando carichi un referto, AHIA:

1. salva una copia del PDF nel tuo archivio personale;
2. estrae il testo se il PDF lo contiene, altrimenti converte le pagine in immagini;
3. riconosce il tipo di documento;
4. estrae analiti e valori dai referti tabellari oppure produce una sintesi dei referti narrativi;
5. normalizza nomi, unità e flag;
6. salva i risultati nel database SQLite del tuo utente;
7. usa il database per grafici, serie storiche, ricerca e chat.

Il PDF resta disponibile per verificare l’estrazione e per rielaborarlo in futuro, ma le funzioni dell’applicazione lavorano sui dati archiviati.

I modelli ordinari girano con Ollama in locale. L’unico percorso verso un
provider esterno è il Secondo parere: parte soltanto dopo pseudonimizzazione,
revisione del payload e conferma esplicita.

La pipeline completa, i confini dei componenti, la giuntura
`converti()`/`elabora()` e le schede di layout sono in
[`docs/ARCHITETTURA.md`](docs/ARCHITETTURA.md).

---

## Dove finiscono i dati

Tutto in `~/.ahia` — su Windows `C:\Users\<utente>\.ahia` — modificabile con
la variabile d'ambiente `AHIA_DATA_DIR`. Ogni utente ha un archivio fisicamente
separato sotto `~/.ahia/archivi/<id>/`:

| File | Contenuto |
|---|---|
| `salute.db` | SQLite: profilo, risultati, conversazioni |
| `referti/` | copia dei PDF caricati |
| `alias_analiti.json` | dizionario personale delle diciture |

Per il backup basta copiare la cartella, oppure usare l'esportazione in zip
dalla pagina **Privacy e dati**. Se la macchina è condivisa, valuta un filesystem cifrato:
il database non è protetto da password.

---

## Privacy e sicurezza

L'accesso richiede un'utenza. Al primo avvio viene chiesto di creare
l'amministratore; in alternativa si possono usare le variabili d'ambiente
`AHIA_ADMIN_USER` e `AHIA_ADMIN_PASSWORD` per un'installazione automatizzata.

Le password sono conservate come impronta scrypt con sale casuale per utente,
mai in chiaro. Cinque tentativi falliti sospendono l'accesso per quindici
minuti. La sessione vive nella scheda del browser: chiudendola o ricaricando la
pagina si torna alla schermata di accesso — comportamento voluto, perché
l'accesso non lasci traccia sul dispositivo.

**Ogni utente vede solo i propri dati.** Non per via di un filtro nelle query,
ma perché ogni utente ha un database e una cartella di referti propri. Un errore
in una query non può far trapelare i dati di un altro: sono file diversi. Questo
vale anche per l'amministratore, che gestisce le utenze ma non accede ai loro
archivi.

L'app ascolta solo su `localhost` (`.streamlit/config.toml`). Esporla in rete
richiede almeno HTTPS davanti: il login viaggerebbe altrimenti in chiaro.

Il database non è cifrato. Chiunque abbia accesso all'utente del sistema legge
l'archivio: se la macchina è condivisa, usa un filesystem cifrato e punta
`AHIA_DATA_DIR` lì. Le chiavi API del secondo parere fanno eccezione: sono
cifrate con una chiave derivata dalla password dell'utente.

I PDF sono documenti medici reali e sensibili. AHIA li apre comunque con cautele tecniche, perché il formato può contenere strutture anomale e il testo estratto finisce nel database, nei grafici e nel prompt del modello. Di conseguenza:

- i nomi dei file vengono sanificati prima di essere scritti su disco;
- tutte le query usano parametri, mai concatenazione di stringhe;
- l'interfaccia non interpreta HTML proveniente dai dati estratti;
- **un PDF costruito ad arte può però influenzare il modello** con istruzioni
  nascoste nel testo. L'effetto è limitato — il modello non esegue codice e gli
  strumenti accettano solo query predefinite — ma una sintesi può essere
  manipolata. Carica referti che provengono dal tuo laboratorio.

`OLLAMA_HOST` accetta solo `http://` e `https://`, così una variabile
d'ambiente ostile non può far leggere file locali.

La pseudonimizzazione reversibile del secondo parere — token opachi, mappa solo
locale, reidratazione, segnalazione manuale e regole personali cifrate — è
implementata e descritta nella
[specifica di progetto](docs/PSEUDONIMIZZAZIONE.md).

---

## Stato del progetto

Software sperimentale, in evoluzione, nato per un uso personale. Funziona ed è
collaudato sui casi che ho incontrato, ma incontrerà sicuramente layout di
referti che non gestisce bene: i formati dei laboratori italiani sono molti e
tutti diversi.

L'estrazione va verificata sul primo referto di ogni laboratorio nuovo: i
layout cambiano e un valore letto male entra nel database senza segnalarlo.

Segnalazioni e contributi sono benvenuti, soprattutto se accompagnati dalla
descrizione del referto che ha creato problemi — non dal referto stesso.

Lo stato tecnico verificato e i limiti aperti sono mantenuti in
[`docs/STATO_PROGETTO.md`](docs/STATO_PROGETTO.md).

## Documentazione

- [`docs/ARCHITETTURA.md`](docs/ARCHITETTURA.md): componenti, fasi di elaborazione e flussi dei dati.
- [`docs/INTEGRAZIONE_FAKING_MEDDOC.md`](docs/INTEGRAZIONE_FAKING_MEDDOC.md): percorso testuale end-to-end, corpus e risultati misurati.
- [`docs/INTERFACCIA.md`](docs/INTERFACCIA.md): organizzazione e comportamento dell’interfaccia.
- [`docs/PSEUDONIMIZZAZIONE.md`](docs/PSEUDONIMIZZAZIONE.md): confine del Secondo parere.
- [`docs/CONFIGURAZIONE_MODELLI.md`](docs/CONFIGURAZIONE_MODELLI.md): scelta e ruoli dei modelli.
- [`docs/STATO_PROGETTO.md`](docs/STATO_PROGETTO.md): versione verificata, test e limiti aperti.

## Ringraziamenti

Le descrizioni degli esami sono collegate a
[labtestsonline.it](https://labtestsonline.it), il portale divulgativo di
SIBioC — Società Italiana di Biochimica Clinica e Biologia Molecolare Clinica.
L'app conserva solo i collegamenti: i contenuti restano sul loro sito.

## Licenza

[GNU Affero General Public License v3.0](LICENSE).

In breve: puoi usare, studiare, modificare e ridistribuire il programma
liberamente, a condizione che le versioni modificate restino sotto la stessa
licenza. La particolarità dell'AGPL rispetto alla GPL è che l'obbligo vale
anche per chi non distribuisce alcun file ma offre il programma come servizio
attraverso una rete: anche in quel caso gli utenti hanno diritto al sorgente.

Per un'app che tratta referti medici mi sembra la scelta giusta: chi affida i
propri dati sanitari a un programma dovrebbe poter vedere cosa quel programma
ne fa.

Il progetto usa PyMuPDF, a sua volta distribuita sotto AGPL-3.0.

---

### In English

AHIA is a fully local medical records tool: it extracts values from lab report
PDFs, tracks them over time, and lets you discuss them with a language model
running on your own machine. Nothing leaves the computer.

It is built specifically for **Italian** lab reports — decimal commas, sample
matrix prefixes, laboratory-specific naming — so its usefulness outside that
context is limited. The interface is in Italian; the usage disclaimer is
available in both Italian and English.

It is experimental software, not a medical device, and does not replace a
physician. It is provided "as is", without warranty of any kind, and the author
accepts no liability for any data shared with third parties, for malfunctions of
the software or third-party components, or for improper use. The OpenAI, Anthropic and OpenRouter data boundary is covered by simulated
tests, but the integrations have not yet been exercised against live services.
