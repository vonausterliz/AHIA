# Come AHIA viene collaudata con FAKING_MEDDOC

## 1. Il collegamento, senza abbreviazioni

FAKING_MEDDOC crea un referto interamente sintetico in formato testo e un file JSON che dichiara quali dati contiene. AHIA riceve quel testo, prova a estrarre gli esami e il benchmark confronta il risultato con il JSON.

```text
FAKING_MEDDOC                     AHIA
---------------                   ----
referto sintetico.txt  ────────►  ingest.elabora()
                                      │
truth manifest.json  ─────────────► confronto
                                      │
                                      ▼
                         recall, valori, unità,
                              allucinazioni
```

Non c’è una chiamata runtime fra i due progetti. Gli output vengono generati e revisionati, poi copiati nel repository AHIA come fixture congelate.

## 2. Perché questo test esiste

Il normale processo di AHIA ha due passaggi indipendenti:

1. `ingest.converti()` apre il PDF e produce testo o immagini;
2. `ingest.elabora()` legge quel contenuto e produce dati strutturati.

FAKING_MEDDOC collauda il secondo passaggio. Il testo sintetico viene inserito direttamente in:

```python
ingest.Contenuto(testo=caso["testo"], immagini=[])
```

In questo modo un errore di OCR non viene confuso con un errore di estrazione. I due rami di conversione dei PDF — text layer e scansione — sono verificati separatamente in `tests/test_ingest.py`.

## 3. Il corpus end-to-end

Il file [`tests/fixtures/faking_meddoc_corpus.json`](../tests/fixtures/faking_meddoc_corpus.json) contiene tre coppie testo/manifest prodotte realmente da FAKING_MEDDOC 0.2.22 con i seed:

- `12001`: anemia sideropenica, emoglobina `10.5 g/dL`;
- `12002`: diabete tipo 2, glicemia `135 mg/dL`;
- `12005`: ipertensione, pressione sistolica `145 mmHg`.

Ogni caso conserva senza modifiche:

- testo completo emesso dal generatore;
- `schema_version` e `generator_version`;
- seed;
- identità sintetica;
- data e laboratorio sintetici;
- lista degli esami con nome, valore e unità.

Il PDF usato per produrre questi casi era a sua volta una fixture sintetica di FAKING_MEDDOC. Nessun documento clinico reale o dato personale è contenuto nel corpus.

## 4. Cosa esegue il benchmark

Per ogni caso `tools/benchmark_estrazione.py`:

1. carica il testo e il manifest;
2. costruisce `Contenuto(testo=..., immagini=[])`;
3. forza il tipo `analisi_sangue`, perché il test vuole misurare l’estrazione e non la classificazione;
4. chiama `ingest.elabora()` con il modello locale configurato;
5. normalizza esami attesi ed estratti con le stesse regole AHIA;
6. confronta gli esami senza dipendere dall’ordine;
7. stampa un rapporto JSON.

Comando:

```bash
.venv/bin/python tools/benchmark_estrazione.py
```

Metriche:

| Metrica | Domanda a cui risponde |
|---|---|
| `recall_analiti` | AHIA ha trovato tutti gli esami presenti nel testo? |
| `accuratezza_valori` | I valori estratti coincidono con quelli attesi? |
| `accuratezza_unita` | Le unità estratte coincidono? |
| `allucinazioni` | AHIA ha inventato esami non presenti? |

Il benchmark usa un LLM e quindi non è un gate deterministico della CI. Il rapporto deve sempre indicare modello e configurazione usati quando viene pubblicato.

## 5. Risultato end-to-end verificato

Il 15 agosto 2026 gli stessi tre testi sono stati passati realmente a `ingest.elabora()` sulla configurazione locale:

| Caso | Analiti trovati | Valori | Unità | Allucinazioni |
|---|---:|---:|---:|---:|
| seed 12001 | 100% | 100% | 100% | 0 |
| seed 12002 | 100% | 100% | 100% | 0 |
| seed 12005 | 100% | 100% | 100% | 0 |

Questo risultato prova che il collegamento FAKING_MEDDOC → testo → AHIA → confronto funziona per i tre casi e il modello locale provato. Non dimostra che AHIA estragga correttamente ogni referto possibile.

## 6. Il corpus delle regole di dominio è un’altra cosa

Il file [`tests/fixtures/ahia_domain_corpus.json`](../tests/fixtures/ahia_domain_corpus.json) non è output diretto di FAKING_MEDDOC. È stato progettato in AHIA per verificare in modo deterministico:

- alias fra `Glicemia`, `S-Glucosio` e `GLUCOSIO SIERICO`;
- conversione `mmol/L` → `mg/dL`;
- calcolo dei flag;
- deduplicazione;
- ordinamento delle serie storiche.

Viene eseguito da:

```bash
.venv/bin/python -m unittest discover \
  -s tests -p 'test_collaudo_dominio_sintetico.py'
```

Separare i due corpus rende esplicito cosa stiamo testando:

| Corpus | Provenienza | Oggetto del test | Usa un LLM? |
|---|---|---|---:|
| `faking_meddoc_corpus.json` | output reale di FAKING_MEDDOC | estrazione dal testo | sì |
| `ahia_domain_corpus.json` | casi sintetici progettati in AHIA | regole e persistenza | no |

## 7. Secondo parere

Il corpus FAKING_MEDDOC viene riutilizzato anche per controllare il confine privacy del Secondo parere. Il test prende l’identità sintetica dichiarata nel manifest, verifica che venga riconosciuta e controlla che il provider simulato non la riceva.

Questo non misura l’estrazione clinica; usa lo stesso materiale sintetico per provare un confine diverso.

## 8. Come si aggiorna il corpus end-to-end

L’aggiornamento deve conservare la provenienza:

1. in FAKING_MEDDOC generare testo e manifest nello stesso comando;
2. accettare soltanto casi per cui l’esportazione testuale riesce;
3. revisionare testo e JSON e verificare che non contengano dati del PDF reale;
4. copiare testo e manifest senza riscriverne i valori;
5. registrare versione del generatore, seed, modalità e data;
6. eseguire i test statici del corpus;
7. eseguire il benchmark con il modello locale;
8. revisionare il diff prima del commit.

Una nuova release di FAKING_MEDDOC non cambia automaticamente le fixture esistenti. `generator_version` è la provenienza del singolo caso e cambia soltanto quando quel caso viene rigenerato.

## 9. Limite noto del produttore

FAKING_MEDDOC rifiuta l’esportazione testuale quando il modello clinico conserva contenuto derivato dal PDF reale. Oggi questo accade anche sui referti tabellari per i quali il generatore varia localmente i valori al fine di preservare il layout.

Questi PDF possono essere usati per collaudi visuali, ma non devono entrare nel corpus testuale end-to-end. La limitazione è documentata nel repository FAKING_MEDDOC in `docs/ARCHITETTURA.md`.
