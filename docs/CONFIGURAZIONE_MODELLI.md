# Configurazione dei modelli

AHIA separa due concetti che non vanno confusi:

- **disponibile**: il modello compare per l'installazione Ollama o per l'account API;
- **compatibile**: il catalogo dichiara le capacità necessarie al percorso scelto;
- **verificato tecnicamente**: AHIA ha eseguito uno smoke test del confine dati;
- **validato clinicamente**: richiederebbe una valutazione clinica dedicata. Al momento
  AHIA non attribuisce questo stato ad alcun modello.

## Modelli locali

La configurazione automatica riduce le nove funzioni interne a quattro ruoli:

| Ruolo | Uso |
|---|---|
| Operazioni rapide | classificazione, testo, dizionario, chat breve |
| Analisi approfondita | analisi clinica, struttura, estrazioni difficili |
| Visione e scansioni | pagine fotografate o rasterizzate |
| Ricerca semantica | embedding dei passaggi testuali |

Le priorità **Equilibrato**, **Più veloce** e **Massima qualità** producono una
raccomandazione per ogni ruolo. Per impostazione predefinita AHIA la calibra
usando RAM, VRAM NVIDIA o AMD e memoria unificata Apple rilevate localmente. La
rilevazione non usa la rete, non salva identificativi hardware ed è
disattivabile. Le soglie sono conservative e le dimensioni sono stime delle
varianti pubblicate nella libreria Ollama, non una misura delle prestazioni
cliniche.

La UI separa sempre **Consigliato** da **In uso**. Se il modello consigliato
manca, AHIA continua a usare il primo fallback compatibile già installato. Il
pulsante **Da installare** apre una finestra con ruolo, peso stimato e modalità
di esecuzione prevista; il download da Ollama parte soltanto con **Conferma e
scarica**. Sono riconosciute anche le varianti quantizzate dello stesso modello.

La modalità **Personalizzata** espone prima i quattro ruoli e, in un pannello
avanzato, le eccezioni per singola funzione. In questa modalità le
raccomandazioni hardware sono informative e non sovrascrivono le scelte.

Se un archivio contiene scelte per-funzione create da una versione precedente,
AHIA parte in modalità Personalizzata e le conserva. Nessuna migrazione sceglie
silenziosamente un modello diverso.

## Provider esterni

I cataloghi vengono letti soltanto con il pulsante **Aggiorna elenco modelli**.
La risposta normalizzata e l'ora di aggiornamento sono conservate nel database
dell'utente; la chiave API resta cifrata separatamente e non entra nella cache.

Endpoint usati:

- Ollama: `/api/tags` e, durante un aggiornamento dettagliato, `/api/show`;
- OpenAI: `GET /v1/models`;
- Anthropic: `GET /v1/models?limit=1000`;
- OpenRouter: `GET /api/v1/models/user` sull'host UE.

Per OpenRouter AHIA invia inoltre questi vincoli nella richiesta:

```json
{
  "provider": {
    "zdr": true,
    "data_collection": "deny",
    "allow_fallbacks": false
  }
}
```

Un modello scomparso dal catalogo resta visibile come scelta non più disponibile:
AHIA segnala il problema e non passa automaticamente a un altro provider o
modello. Il catalogo indica disponibilità e capacità tecniche, non appropriatezza
medica né conformità normativa del trattamento.
