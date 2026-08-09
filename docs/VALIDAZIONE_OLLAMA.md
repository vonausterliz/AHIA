# Validazione Ollama del secondo parere

Data: 9 agosto 2026

## Scelta del modello

Per questa macchina la prima scelta è `qwen3:30b-instruct`, corrispondente a
Qwen3-30B-A3B-Instruct-2507. La
[scheda ufficiale](https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507)
indica 30,5 miliardi di parametri totali, 3,3 miliardi attivi per token,
contesto nativo 262.144 e licenza Apache-2.0. Il
[pacchetto Ollama](https://ollama.com/library/qwen3/tags) Q4_K_M occupa circa
19 GB.

La verifica locale dopo il download ha confermato:

- architettura `qwen3moe`, 30,5B;
- quantizzazione `Q4_K_M`;
- contesto 262.144;
- ID Ollama `19e422b02313`;
- dimensione locale 18 GB;
- testo della licenza Apache-2.0 incluso nel manifest.

Con “senza vincoli all'utilizzo” si intende qui **senza restrizioni sul campo
d'uso**, inclusi uso commerciale e ambito sanitario. Apache-2.0 non è pubblico
dominio: in caso di redistribuzione restano gli obblighi di conservare licenza
e avvisi.

`mistral-small3.2:latest` resta un ottimo fallback già installato. Anche la
[scheda ufficiale Mistral](https://huggingface.co/mistralai/Mistral-Small-3.2-24B-Instruct-2506)
dichiara Apache-2.0. Non è stato scelto BioMistral 7B: pur essendo Apache-2.0,
la sua [model card](https://huggingface.co/BioMistral/BioMistral-7B) ne
sconsiglia espressamente l'uso professionale medico e sanitario. I modelli
Llama non soddisfano invece il requisito di licenza permissiva posto per
questa valutazione.

Qwen non è un dispositivo medico né un modello clinico validato. La scelta è
adatta a sintesi, organizzazione del quadro e preparazione di domande da
discutere con un professionista; non autorizza diagnosi o decisioni autonome.

## Macchina di prova

- CPU AMD Ryzen 5 8600G, 6 core / 12 thread;
- 60 GiB RAM;
- NVIDIA RTX 3060 con 12 GB VRAM;
- Ollama locale, modello parzialmente offloadato sulla GPU.

## Smoke test privacy

Il test usa esclusivamente PII sintetiche. Costruisce un quesito con paziente,
medico, codice fiscale e telefono, esegue rilevazione Presidio, sostituzione
con token opachi, invio a Ollama, controllo della risposta e reidratazione
locale.

```bash
.venv/bin/python tools/smoke_ollama_pii.py --model qwen3:30b-instruct
```

| Controllo | Qwen3 30B Instruct | Mistral Small 3.2 |
|---|---:|---:|
| PII rilevate | 4 | 4 |
| Token restituiti integri | 4/4 | 4/4 |
| PII nel payload esterno | 0 | 0 |
| PII nella risposta esterna | 0 | 0 |
| Token sconosciuti/malformati | 0/0 | 0/0 |
| Valori reidratati | 4/4 | 4/4 |
| Durata a caldo | 6,14 s | 21,27 s |

Il primo run Qwen a freddo, comprensivo del caricamento, ha richiesto 34,73 s.
Le durate sono indicative: le risposte possono avere lunghezze diverse e lo
smoke non è un benchmark di qualità clinica. Il risultato misura il confine
privacy e la conservazione dei token.
