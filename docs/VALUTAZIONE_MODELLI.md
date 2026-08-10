# Valutazione sintetica dei modelli locali

Data: 10 agosto 2026

Questa è una verifica tecnica preliminare, **non una validazione clinica**. I
cinque casi CC0 sono interamente sintetici e controllano proprietà osservabili:
riconoscimento di trend, richiesta di dati mancanti, urgenza esplicita,
rifiuto di modificare autonomamente una terapia e gestione di valori
implausibili.

## Risultati AHIA 1.26.0

| Modello | Casi superati |
|---|---:|
| `qwen3:14b` | 5/5 |
| `qwen3:30b-instruct` | 5/5 |

Le risposte complete, le regole applicate e la provenienza dei casi sono in
[`VALUTAZIONE_MODELLI_1.26.json`](VALUTAZIONE_MODELLI_1.26.json). La prova usa i
prompt effettivi di AHIA, temperatura zero e controlli automatici di espressioni
richieste o vietate.

Per riprodurla:

```bash
.venv/bin/python tools/valuta_modelli_sintetici.py \
  --modelli qwen3:14b qwen3:30b-instruct
```

## Limiti

- Cinque casi non misurano accuratezza clinica generale né affidabilità su
  referti reali.
- I controlli lessicali non sostituiscono la revisione di professionisti
  sanitari.
- Il risultato dipende da versione e quantizzazione dei modelli e da Ollama.
- Nessun modello in AHIA è dichiarato clinicamente validato.

Prima di qualunque dichiarazione clinica servono un protocollo preregistrato,
un campione adeguato e rappresentativo, revisori clinici indipendenti, analisi
degli errori e criteri di accettazione definiti prima del test.
