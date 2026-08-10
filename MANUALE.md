# Manuale d'uso di AHIA

Questa è la guida all'uso quotidiano di AHIA. Presuppone che l'app sia già
installata e avviata; per l'installazione, vedi il `README`.

Ogni sezione inizia con una spiegazione semplice e, dove serve, chiude con
qualche nota più tecnica per chi vuole capire cosa succede sotto.

> **Ricorda sempre.** AHIA non è un dispositivo medico e non sostituisce il
> medico. Serve a tenere in ordine i tuoi referti e a ragionarci sopra, non a
> ricevere diagnosi. Ogni valore estratto va confrontato con il referto
> originale, e ogni dubbio clinico va portato al tuo medico.

---

## Primo avvio

La prima volta che apri AHIA ti viene chiesto di **creare un utente
amministratore** — scegli un nome e una password. Questa password non protegge
solo l'accesso: serve anche a cifrare le eventuali chiavi API che userai per il
secondo parere, quindi scegline una che ricordi.

Subito dopo compare l'**avvertenza**, che devi leggere e accettare per
proseguire. Descrive i limiti dell'app e le tue responsabilità nell'usarla. La
data e l'ora della tua accettazione vengono registrate; puoi rileggere
l'avvertenza in qualsiasi momento dal pulsante nella barra laterale.

**Nota.** Ogni volta che ricarichi la pagina o chiudi il browser, ti verrà
richiesto di accedere di nuovo. È voluto: l'accesso non lascia traccia sul
dispositivo, cosa opportuna per un'app che tratta dati sanitari.

---

## Il menu in breve

AHIA usa un menu laterale raggruppato per attività. Logo, nome e versione sono
sempre in testa; sotto trovi le pagine e, in coda, soltanto lo stato di Ollama,
il profilo modelli e l’utente corrente.

- **Uso quotidiano:** Home, Referti, Andamenti, Assistente e Secondo parere.
- **Gestione:** Profilo, Dizionario e riferimenti.
- **Impostazioni:** Modelli e provider, Privacy e dati, Diagnostica, Guida e, per l’amministratore, Utenti.

**Assistente** riunisce la lettura guidata e le conversazioni persistenti. Le opzioni per numero di referti e strumenti si trovano nel pannello contestuale della stessa pagina, non nella barra globale.

---

## Profilo

**A cosa serve.** Un valore "alto" o "basso" dipende da chi sei: gli intervalli
di riferimento cambiano con l'età e il sesso. Compilando il profilo, AHIA
contestualizza meglio i tuoi esami.

Inserisci quello che vuoi condividere: età (anno di nascita), sesso biologico, e
facoltativamente altezza e peso (da cui l'app calcola il BMI). C'è anche uno
spazio per terapie e note.

> **Attenzione al campo "Terapie e note".** È testo libero, ed è la parte che più
> facilmente contiene dati personali. Viene incluso nel secondo parere solo se lo
> chiedi esplicitamente. Scrivici solo ciò che ti serve per l'analisi.

---

## Referti: caricare ed elaborare

**A cosa serve.** È il cuore dell'app: qui trasformi un PDF in dati leggibili e
ricercabili.

**Come si fa.** Trascina o seleziona uno o più PDF, poi premi **Elabora**. Per
ogni file AHIA:

1. legge il testo (o, se è una scansione, "guarda" le pagine come immagini);
2. riconosce di che tipo di documento si tratta;
3. se è un referto con valori (analisi del sangue, urine), ne estrae gli esami;
4. se è descrittivo (una visita, un'ecografia), ne conserva il testo e una
   sintesi.

Durante l'elaborazione, un **registro** mostra passo per passo cosa sta
succedendo, con un segnale ogni venti secondi per farti sapere che sta
lavorando anche quando un passaggio è lungo.

**Il primo referto di un laboratorio nuovo è più lento.** La prima volta che
incontra un laboratorio mai visto, AHIA ne studia l'impaginazione e prepara una
"scheda di lettura" che riuserà per i referti successivi di quello stesso
laboratorio. Per questo il primo referto viene elaborato due volte ed è più
lento; i successivi partono già con la scheda e sono rapidi. Puoi disattivare
questo comportamento dall'interruttore nella scheda, se preferisci
un'elaborazione sempre singola.

> **Verifica sempre il primo referto di ogni laboratorio.** L'estrazione può
> sbagliare — spostare una virgola, attribuire un intervallo di riferimento alla
> riga sbagliata. Confronta i valori estratti con il PDF originale, almeno la
> prima volta per ogni nuovo laboratorio.

**Ri-estrarre un referto già in archivio.** Accanto a ogni documento, nella lista
per tipologia, c'è un pulsante **Ri-estrai**: rielabora quel referto dal suo PDF
originale con i modelli attuali, senza doverlo ricaricare a mano. Serve quando
l'estrazione è migliorata da quando l'avevi caricato — per esempio dopo un
aggiornamento dell'app — e vuoi che anche i referti vecchi ne beneficino. Il PDF
originale deve essere ancora in archivio (lo è, salvo che tu non abbia cancellato
la cartella dei dati).

*Nota tecnica.* Il testo di un referto viene estratto e salvato al momento del
caricamento, con la versione di allora. Migliorare l'estrazione non cambia i
testi già salvati: la ri-estrazione li rigenera. È utile in particolare per la
pseudonimizzazione del secondo parere, che lavora sul testo salvato.

*Nota tecnica.* Prima di elaborare, AHIA controlla che i modelli scelti siano
installati in Ollama. I modelli si configurano in **Impostazioni → Modelli e
provider**: se manca un consiglio, premi **Da installare**, controlla dimensione
e modalità di esecuzione previste e conferma il download. La modalità automatica
usa quattro ruoli; le eccezioni per singola funzione restano disponibili nel
pannello avanzato.

---

## Andamento analiti

**A cosa serve.** Vedere come un valore si muove nel tempo, a colpo d'occhio.

Scegli un analita e AHIA disegna la sua serie storica. La cosa più importante da
capire è il colore: le **zone fuori dall'intervallo di riferimento sono in rosso
chiaro** — sopra il valore massimo e sotto il minimo. Se un punto cade nel
rosso, è fuori norma; se resta nella banda tenue centrale, è nella norma. Non
devi leggere i numeri per accorgertene.

C'è anche un confronto normalizzato che mette sullo stesso grafico esami con
unità diverse, e una tabella delle variazioni che puoi esportare.

*Nota tecnica.* La banda normale è verde se l'intervallo lo dichiara il
laboratorio, azzurra se invece proviene dal catalogo interno dell'app: la
differenza ti dice quanto fidarti dell'intervallo mostrato.

---

## Assistente

**A cosa serve.** È il posto dove leggi e discuti i tuoi referti — di ogni tipo,
numerici e descrittivi. Fa tre cose:

*Una lettura d'insieme.* Scegli l'ambito — tutto l'archivio, una tipologia (per
esempio solo le visite oculistiche), o un singolo referto — e il modello locale
produce un commento complessivo con un pulsante.

*Consulta i referti.* Sotto l'analisi, un pannello ti lascia sfogliare i referti
dell'ambito scelto, ciascuno con sintesi, conclusioni e testo completo.

*Discuti in conversazione.* Una chat ti lascia fare domande sull'ambito
selezionato: con una tipologia scelta, ragiona solo su quella ("come è cambiata
la mia situazione oculistica nel tempo?") senza mescolare gli altri referti; con
un referto singolo, solo su quello; con tutto l'archivio, su tutto.

Ricorda che è un modello che gira sul tuo computer: utile per orientarti, ma non
è un medico.

*Nota tecnica.* I calcoli (differenze, percentuali) non li fa il modello: gli
arrivano già pronti, così non può sbagliarli. **Lettura guidata** offre anche
domande rapide sull’ambito corrente; **Conversazioni** mantiene invece uno
storico persistente. Il testo dei referti resta consultabile per controllare la fonte.


---

## Secondo parere

**A cosa serve.** Un modello locale è limitato; su un ragionamento clinico
complesso, un modello di frontiera (come quelli dietro Claude o ChatGPT) fa
molto meglio. Questa pagina guida in tre fasi e prepara un testo da sottoporre a uno di questi
modelli riducendo l'esposizione degli identificatori riconosciuti.

**Come si fa.**

1. Scegli **cosa includere**: tutti i referti, solo alcune categorie (le
   selezioni con le caselle), oppure un singolo referto dalla lista.
2. Scegli quanto dettaglio dare sull'età e se includere il BMI.
3. AHIA minimizza i dati non necessari e sostituisce gli identificatori
   riconosciuti con token casuali come `[[4E91A75C820DF63B18A05CC7]]`. Il token
   non indica se rappresenta un paziente, un medico o una struttura.
4. **Rileggi il payload.** Se noti un dato sfuggito, usa **Segnala un dato non
   rilevato** e scegli le occorrenze. Puoi limitarlo alla richiesta oppure
   ricordarlo come regola cifrata per questo utente. Se invece AHIA ha protetto
   per errore un termine clinico, apri **Rivedi possibili falsi positivi**,
   scegli esplicitamente di mostrare i valori e ripristina soltanto quello
   errato: l'eccezione vale per questa richiesta e non viene salvata.
5. Conferma l'esatto testo mostrato. Qualsiasi modifica o nuova sostituzione
   invalida la conferma e richiede una nuova lettura.
6. Dopo il passaggio alla fase **Invia e reidrata**, copia o scarica il payload,
   oppure invialo direttamente se hai configurato chiave e modello in
   **Impostazioni → Modelli e provider**.
7. Incolla in AHIA la risposta ottenuta manualmente, oppure attendi quella
   dell'invio diretto: i token integri vengono sostituiti localmente con i valori
   originali. La risposta reidratata contiene di nuovo dati personali.

> **Il punto più delicato dell'app.** AHIA è progettata perché nulla esca dal
> tuo computer senza un tuo gesto, e perché gli identificatori rilevati siano
> pseudonimizzati. Ma questo **non è garantito**: un errore o un bug possono
> lasciar passare qualcosa. La pseudonimizzazione non rende anonimo un quadro
> clinico raro o riconoscibile dal contesto. Rileggi sempre, con particolare
> attenzione quando includi visite o ecografie.
>
> La mappa dei token vive soltanto nella sessione corrente. Se chiudi AHIA prima
> di incollare la risposta manuale, non potrà essere ricostruita.
>
> Le regole personali sono invece persistenti, isolate per utente e cifrate con
> una chiave derivata dalla password. Nel pannello **Regole PII personali** puoi
> mostrarle, modificarle, disattivarle o eliminarle. Reimpostando la password
> non saranno più decifrabili.
>
> Puoi preparare un caso JSON per migliorare i rilevatori: AHIA rimuove il valore
> segnalato, non effettua upload e mostra l'intero contenuto prima di abilitare
> il download. Il contesto può comunque contenere dati sanitari o altre PII e
> deve essere revisionato.
>
> **L'invio diretto tramite chiave API non è testato.** Il percorso sicuro e
> collaudato è quello manuale: copi il testo e lo incolli tu, dopo averlo letto.

*Nota tecnica.* Le chiavi API, se le inserisci, sono cifrate con una chiave
derivata dalla tua password. Se reimposti la password, dovrai reinserirle.

---

## Modelli e provider

Per l’uso normale scegli soltanto una priorità: **Equilibrato**, **Più veloce**
o **Massima qualità**. AHIA rileva localmente RAM, VRAM NVIDIA o AMD e memoria
unificata Apple, quindi propone modelli proporzionati alla macchina per quattro
ruoli: operazioni rapide, analisi approfondita, visione e ricerca semantica. La
rilevazione non usa la rete, non salva identificativi hardware ed è disattivabile.

Il modello consigliato e quello in uso sono distinti. Se il consiglio non è
ancora presente, AHIA usa il miglior fallback compatibile già installato e
mostra **Da installare**. Il pulsante apre una conferma con peso stimato e
modalità di esecuzione prevista; soltanto **Conferma e scarica** contatta Ollama.
Una quantizzazione compatibile dello stesso modello viene riconosciuta come già
installata. La modalità Personalizzata mantiene le eccezioni per singola
funzione e mostra i consigli senza sovrascriverle.

Per OpenAI, Anthropic e OpenRouter la lista viene letta dal provider soltanto quando premi **Aggiorna elenco modelli** e resta in cache locale. La presenza nella lista indica disponibilità per l’account, non validazione clinica. Se un modello scelto scompare, AHIA avvisa e non effettua fallback silenziosi.

Con OpenRouter AHIA usa l’endpoint UE e richiede zero data retention, nessuna raccolta dati e nessun fallback. Questi vincoli riducono l’esposizione, ma non rendono anonima una storia clinica pseudonimizzata.

---

## Dizionario

**A cosa serve.** Ogni laboratorio scrive gli esami a modo suo: "Glicemia",
"S-Glucosio", "GLUCOSIO SIERICO" sono lo stesso esame. Se AHIA non li unificasse,
avresti tre serie storiche spezzate invece di una.

La maggior parte delle unificazioni avviene da sola. Quando AHIA incontra una
dicitura che non riconosce, la segnala qui: puoi collegarla all'esame giusto,
con una proposta suggerita dal modello che confermi tu.

---

## Diagnostica

**A cosa serve.** Mostra come sta lavorando l'app sul tuo archivio: quante volte
ha interrogato i modelli, quanto tempo ci mette in media, quanti errori ci sono
stati e uno storico delle tue operazioni. Utile per capire se qualcosa è lento o
non va, e per avere un'idea del carico di lavoro.

In cima ci sono quattro numeri di sintesi (chiamate ai modelli, errori, durata
media, token totali). Sotto, la tabella degli eventi, filtrabile per vedere solo
le chiamate ai modelli o solo gli errori. Puoi esportare tutto in CSV o svuotare
il registro. Qui trovi anche il registro e le metriche dell’ultima elaborazione e il log di Ollama, rimossi dalla pagina Referti.

> **Riguarda solo il tuo archivio.** Ogni utente vede la diagnostica delle
> proprie attività, non di quelle altrui: come per tutti i dati, gli archivi
> restano separati. E il registro contiene solo metriche tecniche (tempi,
> modelli, token) e messaggi d'errore — mai il testo dei referti né i valori.

---

## Utenti (solo amministratore)

**A cosa serve.** Se più persone usano la stessa installazione — per esempio in
famiglia — ognuna ha il proprio accesso e il proprio archivio, separato dagli
altri.

L'amministratore crea e rimuove gli utenti, ma **non vede i loro dati**: ogni
archivio è un insieme di file separati. Questo vale anche per l'amministratore
stesso.

Da qui si esporta o importa l'intero archivio di un utente come file zip — utile
per fare un backup o spostare i dati su un altro computer.

---

## Privacy e dati

Tutto ciò che AHIA salva sta sul tuo computer, in una cartella nascosta chiamata
`.ahia` dentro la tua cartella utente. Non c'è nessun cloud e nessun backup
automatico: se vuoi una copia di sicurezza, usa **Privacy e dati → Esporta il mio archivio**. L’amministratore può inoltre importare o esportare un archivio dalla pagina Utenti.

> **Il database non è cifrato.** Chiunque abbia accesso al tuo utente del
> computer può leggere l'archivio. Se il computer è condiviso, valuta un disco o
> una cartella cifrata. Le sole informazioni cifrate sono le chiavi API.

---

## Domande frequenti

**Perché il primo referto di un laboratorio ci mette tanto?**
Perché AHIA sta imparando l'impaginazione di quel laboratorio per i referti
futuri. Vedi la sezione *Referti*.

**Perché ogni volta devo rifare l'accesso?**
Per non lasciare traccia dell'accesso sul dispositivo. Vedi *Primo avvio*.

**Il secondo parere è sicuro?**
Riduce l'esposizione degli identificatori, ma nessuna rilevazione automatica è
perfetta e il contesto clinico può restare reidentificabile. Rileggi sempre il
payload prima di inviarlo. Vedi *Secondo parere*.

**Un valore estratto è sbagliato. Cosa faccio?**
Confrontalo con il PDF originale. L'estrazione può sbagliare, soprattutto su
layout nuovi. Segnala il problema se pubblichi su un repository condiviso.

**AHIA può dirmi se sto bene?**
No. Può aiutarti a organizzare e leggere i tuoi esami, ma l'interpretazione
clinica spetta al medico. Nessuna risposta dell'app è un parere sanitario.
