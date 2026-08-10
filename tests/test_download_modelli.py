import threading
import time
import unittest

import download_modelli


class DownloadModelliTest(unittest.TestCase):
    def attendi_fine(self, timeout=2):
        scadenza = time.monotonic() + timeout
        while time.monotonic() < scadenza:
            corrente = download_modelli.stato()
            if corrente and not corrente.attivo:
                return corrente
            time.sleep(0.01)
        self.fail("il download in background non è terminato")

    def test_avanza_e_completa_in_background(self):
        cancello = threading.Event()

        def sorgente(modello):
            self.assertEqual(modello, "modello:test")
            cancello.wait(1)
            yield {"status": "pulling manifest"}
            yield {"status": "downloading", "completed": 50, "total": 100}

        avviato, _ = download_modelli.avvia("modello:test", sorgente)
        self.assertTrue(avviato)
        self.assertTrue(download_modelli.stato().attivo)
        cancello.set()
        finale = self.attendi_fine()
        self.assertEqual(finale.fase, "completato")
        self.assertEqual(finale.frazione, 1.0)

    def test_impedisce_download_concorrenti(self):
        cancello = threading.Event()

        def sorgente(_):
            cancello.wait(1)
            yield {"status": "done"}

        avviato, _ = download_modelli.avvia("primo:test", sorgente)
        self.assertTrue(avviato)
        secondo, messaggio = download_modelli.avvia("secondo:test", sorgente)
        self.assertFalse(secondo)
        self.assertIn("primo:test", messaggio)
        cancello.set()
        self.attendi_fine()

    def test_espone_errore_del_worker(self):
        def sorgente(_):
            raise RuntimeError("spazio insufficiente")
            yield

        avviato, _ = download_modelli.avvia("errore:test", sorgente)
        self.assertTrue(avviato)
        finale = self.attendi_fine()
        self.assertEqual(finale.fase, "errore")
        self.assertEqual(finale.errore, "spazio insufficiente")


if __name__ == "__main__":
    unittest.main()
