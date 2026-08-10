# Baseline holdout PII

Data del primo run: 9 agosto 2026

Corpus: `tests/fixtures/pseudonimizzazione_holdout.json`

Licenza: CC0-1.0, dati interamente sintetici

SHA-256 del file congelato:
`21a88bb500665f4364ebdbae44f8c511c034c103ef16e6284482001d9b23726f`

## Metodo

Il corpus è stato creato separatamente dai 180 casi di sviluppo, congelato
prima della prima esecuzione e non usato per modificare soglie o recognizer.
Contiene 80 casi, 78 annotazioni, 20 testi con PII multiple, impaginazione
multilinea, rumore OCR simulato e 24 negativi clinici difficili.

Comando:

```bash
.venv/bin/python tools/benchmark_pii.py --holdout
```

Ambiente del primo run: Presidio attivo con `it_core_news_lg`.

## Risultato iniziale

| Metrica | Risultato |
|---|---:|
| Recall complessiva | 88,46% |
| Precisione degli span | 87,18% |
| Accuratezza del tipo | 84,62% |
| Leak annotati | 9 |
| Errori di preservazione | 9 |
| Errori di round-trip | 0 |

Tutti i tipi tranne `IDENTIFICATIVO_DOCUMENTO` hanno ottenuto recall 100%.
Gli identificativi documento non standard si fermano al 30,77%. I nove errori
di preservazione comprendono termini e abbreviazioni cliniche classificati
come PII: sono casi per i quali serve la revisione umana dei falsi positivi.

Il risultato non supera i gate di rilascio. Questa è una baseline informativa,
non un dato da occultare con tuning sul medesimo corpus. Le correzioni future
devono nascere da casi di sviluppo o segnalazioni revisionate; una nuova misura
su questo file serve a confrontare le versioni, non costituisce più una prova
cieca.

## Confronto con AHIA 1.26.0

Il corpus non è stato modificato: l'impronta SHA-256 sopra è invariata. Le
correzioni sono nate dal corpus di sviluppo e da regole generali; il holdout è
stato misurato soltanto dopo l'implementazione.

| Metrica | Baseline 1.23 | AHIA 1.26.0 |
|---|---:|---:|
| Recall complessiva | 88,46% | 100,00% |
| Precisione degli span | 87,18% | 90,59% |
| Accuratezza del tipo | 84,62% | 96,15% |
| Leak annotati | 9 | 0 |
| Errori di preservazione | 9 | 8 |
| Errori di round-trip | 0 | 0 |

La v1.26 elimina i leak annotati e riconosce gli identificativi documentali
eterogenei che mancavano. Il risultato **non supera ancora tutti i gate**:
restano otto falsi positivi che alterano termini clinici e richiedono revisione
umana. Non viene quindi presentato come una validazione conclusa.

## Proprietà già verificate

- Nessuna PII o annotazione proviene da persone reali.
- Offset e valori annotati sono validati automaticamente.
- Gli ID e i testi non si sovrappongono al corpus di sviluppo.
- Il round-trip è esatto in tutti gli 80 casi.
- L'impronta consente di rilevare qualsiasi modifica successiva del corpus.
