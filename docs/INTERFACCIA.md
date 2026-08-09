# Architettura dell'interfaccia

La revisione 1.24 parte da una distinzione semplice: le scelte quotidiane devono
restare vicine al compito; quelle rare o tecniche devono essere raggiungibili,
ma non occupare sempre lo schermo.

## Struttura

```text
Uso quotidiano
├── Home
├── Referti
├── Andamenti
├── Assistente
│   ├── Lettura guidata
│   └── Conversazioni
└── Secondo parere

Gestione
├── Profilo
└── Dizionario e riferimenti

Impostazioni
├── Modelli e provider
├── Privacy e dati
├── Utenti (solo amministratore)
├── Diagnostica
└── Guida
```

La barra laterale non configura più nove funzioni LLM. Mostra navigazione, stato
locale, profilo modelli, identità e uscita.

## Collocazione delle scelte

| Scelta | Dove | Motivo |
|---|---|---|
| priorità e modelli | Modelli e provider | rara e tecnica |
| numero di referti | Assistente → Contesto e strumenti | dipende dal compito |
| strumenti della chat | Assistente → Contesto e strumenti | riguarda solo le conversazioni |
| indice semantico | Modelli e provider | manutenzione, non uso quotidiano |
| chiavi e modello esterno | Modelli e provider | separati dal contenuto sanitario |
| backup personale | Privacy e dati | azione sui dati, non sul modello |
| log di elaborazione | Diagnostica | dettaglio tecnico |

## Secondo parere

Il percorso ha tre stati progressivi:

1. **Prepara:** ambito e minimizzazione; il payload esterno non è ancora mostrato.
2. **Verifica privacy:** token, residui PII, segnalazioni manuali, falsi positivi e
   conferma legata all'impronta dell'esatto payload.
3. **Invia e reidrata:** invio diretto o manuale e ripristino locale dei token.

Passare alla fase 3 richiede che la fase 2 abbia prodotto un payload senza avvisi
bloccanti e che l'utente abbia confermato proprio quell'impronta. Tornare
all'ambito elimina mappa temporanea, payload e risposta.

## Configurabilità progressiva

La modalità Automatica propone tre priorità e quattro ruoli. La modalità
Personalizzata espone gli stessi ruoli; soltanto un ulteriore pannello mostra le
eccezioni per singola funzione. Gli archivi con vecchie eccezioni entrano
direttamente in Personalizzata, così nessuna scelta viene persa o cambiata in
silenzio.
