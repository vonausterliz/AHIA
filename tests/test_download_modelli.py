import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

import download_modelli
import ui_modelli_locali


class DownloadModelliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ahia-download-test-")
        self.percorso = Path(self.tmp.name) / "coda.json"
        self.coda = download_modelli.CodaDownload(
            self.percorso, spazio_libero=lambda: 100 * download_modelli.GIB
        )

    def tearDown(self):
        self.assertTrue(self.coda.attendi())
        self.tmp.cleanup()

    def attendi_fine(self, quanti=1, timeout=2):
        scadenza = time.monotonic() + timeout
        while time.monotonic() < scadenza:
            elementi = self.coda.stati()
            if len(elementi) == quanti and not any(x.pendente for x in elementi):
                return elementi
            time.sleep(0.01)
        self.fail("la coda dei download non è terminata")

    def test_avanza_completa_e_persiste(self):
        def sorgente(modello):
            self.assertEqual(modello, "modello:test")
            yield {"status": "downloading", "completed": 50, "total": 100}

        avviato, _ = self.coda.avvia(
            "modello:test", sorgente, dimensione_gb=2.0
        )
        self.assertTrue(avviato)
        finale = self.attendi_fine()[0]
        self.assertEqual(finale.fase, "completato")
        self.assertEqual(finale.frazione, 1.0)
        salvato = json.loads(self.percorso.read_text(encoding="utf-8"))
        self.assertEqual(salvato["attivita"][0]["fase"], "completato")

    def test_esegue_in_ordine_senza_sovrapporre(self):
        cancello = threading.Event()
        eventi = []

        def sorgente(modello):
            eventi.append(f"inizio:{modello}")
            if modello == "primo:test":
                cancello.wait(1)
            yield {"status": "done"}
            eventi.append(f"fine:{modello}")

        self.coda.avvia("primo:test", sorgente)
        accettato, messaggio = self.coda.avvia("secondo:test", sorgente)
        self.assertTrue(accettato)
        self.assertIn("coda", messaggio)
        self.assertEqual(self.coda.stati()[1].fase, "in_coda")
        self.assertNotIn("inizio:secondo:test", eventi)
        cancello.set()
        self.attendi_fine(quanti=2)
        self.assertEqual(eventi, [
            "inizio:primo:test", "fine:primo:test",
            "inizio:secondo:test", "fine:secondo:test",
        ])

    def test_ripristina_e_riprende_dopo_un_riavvio(self):
        self.percorso.write_text(json.dumps({
            "versione": 1,
            "attivita": [
                {"id": 1, "modello": "interrotto:test", "fase": "download"},
                {"id": 2, "modello": "in-coda:test", "fase": "in_coda"},
            ],
        }), encoding="utf-8")
        ripristinata = download_modelli.CodaDownload(
            self.percorso, spazio_libero=lambda: 100 * download_modelli.GIB
        )
        self.coda = ripristinata
        self.assertEqual(
            [x.fase for x in ripristinata.stati()], ["in_coda", "in_coda"]
        )
        ordine = []

        def sorgente(modello):
            ordine.append(modello)
            yield {"status": "done"}

        self.assertTrue(ripristinata.riprendi(sorgente))
        finale = self.attendi_fine(quanti=2)
        self.assertEqual(ordine, ["interrotto:test", "in-coda:test"])
        self.assertTrue(all(x.fase == "completato" for x in finale))

    def test_annulla_un_elemento_in_coda(self):
        cancello = threading.Event()
        eseguiti = []

        def sorgente(modello):
            eseguiti.append(modello)
            if modello == "primo:test":
                cancello.wait(1)
            yield {"status": "done"}

        self.coda.avvia("primo:test", sorgente)
        self.coda.avvia("secondo:test", sorgente)
        secondo = self.coda.stati()[1]
        ok, _ = self.coda.annulla(secondo.id)
        self.assertTrue(ok)
        cancello.set()
        finale = self.attendi_fine(quanti=2)
        self.assertEqual(finale[1].fase, "annullato")
        self.assertEqual(eseguiti, ["primo:test"])

    def test_annulla_quello_attivo_al_prossimo_aggiornamento(self):
        cancello = threading.Event()

        def sorgente(_):
            cancello.wait(1)
            yield {"status": "downloading", "completed": 1, "total": 10}

        self.coda.avvia("attivo:test", sorgente)
        corrente = self.coda.stato()
        ok, _ = self.coda.annulla(corrente.id)
        self.assertTrue(ok)
        cancello.set()
        finale = self.attendi_fine()[0]
        self.assertEqual(finale.fase, "annullato")

    def test_un_errore_non_blocca_il_successivo_e_si_puo_riprovare(self):
        cancello = threading.Event()

        def sorgente(modello):
            if modello == "errore:test":
                cancello.wait(1)
                raise RuntimeError("connessione interrotta")
            yield {"status": "done"}

        self.coda.avvia("errore:test", sorgente)
        self.coda.avvia("successivo:test", sorgente)
        cancello.set()
        finale = self.attendi_fine(quanti=2)
        self.assertEqual([x.fase for x in finale], ["errore", "completato"])

        def riuscita(_):
            yield {"status": "done"}

        ok, _ = self.coda.riprova(finale[0].id, riuscita)
        self.assertTrue(ok)
        finale = self.attendi_fine(quanti=2)
        self.assertEqual(finale[0].fase, "completato")

    def test_rifiuta_duplicato_e_spazio_insufficiente(self):
        bloccata = download_modelli.CodaDownload(
            Path(self.tmp.name) / "poco-spazio.json",
            spazio_libero=lambda: 2 * download_modelli.GIB,
        )
        ok, messaggio = bloccata.avvia("enorme:test", dimensione_gb=3.0)
        self.assertFalse(ok)
        self.assertIn("Spazio insufficiente", messaggio)

        cancello = threading.Event()

        def sorgente(_):
            cancello.wait(1)
            yield {"status": "done"}

        self.coda.avvia("duplicato:test", sorgente)
        ok, messaggio = self.coda.avvia("duplicato:test", sorgente)
        self.assertFalse(ok)
        self.assertIn("già", messaggio)
        cancello.set()
        self.attendi_fine()

    def test_testo_avanzamento_mostra_percentuale_e_byte(self):
        elemento = download_modelli.StatoDownload(
            id=1, modello="modello:test",
            completato=1_000_000_000, totale=4_000_000_000,
        )
        self.assertEqual(
            ui_modelli_locali._testo_avanzamento(elemento),
            "25% · 1.0 di 4.0 GB",
        )

    def test_testo_avanzamento_spiega_la_preparazione(self):
        elemento = download_modelli.StatoDownload(
            id=1, modello="modello:test",
        )
        self.assertEqual(
            ui_modelli_locali._testo_avanzamento(elemento),
            "Preparazione del download…",
        )


if __name__ == "__main__":
    unittest.main()
