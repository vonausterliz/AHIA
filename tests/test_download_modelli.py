import threading
import time
import unittest

import download_modelli


class DownloadModelliTest(unittest.TestCase):
    def attendi_fine(self, quanti=1, timeout=2):
        scadenza = time.monotonic() + timeout
        while time.monotonic() < scadenza:
            elementi = download_modelli.stati()
            if len(elementi) == quanti and not any(x.pendente for x in elementi):
                return elementi
            time.sleep(0.01)
        self.fail("la coda dei download non è terminata")

    def test_avanza_e_completa_in_background(self):
        cancello = threading.Event()

        def sorgente(modello):
            self.assertEqual(modello, "modello:test")
            cancello.wait(1)
            yield {"status": "pulling manifest"}
            yield {"status": "downloading", "completed": 50, "total": 100}

        avviato, _ = download_modelli.avvia("modello:test", sorgente)
        self.assertTrue(avviato)
        self.assertTrue(download_modelli.stato().pendente)
        cancello.set()
        finale = self.attendi_fine()[0]
        self.assertEqual(finale.fase, "completato")
        self.assertEqual(finale.frazione, 1.0)

    def test_esegue_in_ordine_senza_sovrapporre(self):
        cancello = threading.Event()
        eventi = []

        def sorgente(modello):
            eventi.append(f"inizio:{modello}")
            if modello == "primo:test":
                cancello.wait(1)
            yield {"status": "done"}
            eventi.append(f"fine:{modello}")

        primo, _ = download_modelli.avvia("primo:test", sorgente)
        secondo, messaggio = download_modelli.avvia("secondo:test", sorgente)
        self.assertTrue(primo)
        self.assertTrue(secondo)
        self.assertIn("coda", messaggio)
        elementi = download_modelli.stati()
        self.assertEqual(elementi[1].fase, "in_coda")
        self.assertNotIn("inizio:secondo:test", eventi)

        cancello.set()
        self.attendi_fine(quanti=2)
        self.assertEqual(eventi, [
            "inizio:primo:test", "fine:primo:test",
            "inizio:secondo:test", "fine:secondo:test",
        ])

    def test_non_accoda_due_volte_lo_stesso_modello(self):
        cancello = threading.Event()

        def sorgente(_):
            cancello.wait(1)
            yield {"status": "done"}

        download_modelli.avvia("duplicato:test", sorgente)
        accettato, messaggio = download_modelli.avvia("duplicato:test", sorgente)
        self.assertFalse(accettato)
        self.assertIn("già", messaggio)
        cancello.set()
        self.attendi_fine()

    def test_un_errore_non_blocca_il_successivo(self):
        cancello = threading.Event()

        def sorgente(modello):
            if modello == "errore:test":
                cancello.wait(1)
                raise RuntimeError("spazio insufficiente")
            yield {"status": "done"}

        download_modelli.avvia("errore:test", sorgente)
        download_modelli.avvia("successivo:test", sorgente)
        cancello.set()
        finale = self.attendi_fine(quanti=2)
        self.assertEqual([x.fase for x in finale], ["errore", "completato"])
        self.assertEqual(finale[0].errore, "spazio insufficiente")


if __name__ == "__main__":
    unittest.main()
