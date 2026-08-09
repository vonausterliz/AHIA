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

Le priorità **Equilibrato**, **Più veloce** e **Massima qualità** cambiano l'ordine
con cui AHIA cerca i modelli già installati. Non avviano download. La modalità
**Personalizzata** espone prima i quattro ruoli e, in un pannello avanzato, le
eccezioni per singola funzione.

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
