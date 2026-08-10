import json
import unittest

from tools import valuta_modelli_sintetici as valutazione


class ValutazioneModelliTest(unittest.TestCase):
    def test_corpus_e_interamente_sintetico_e_ha_rubriche(self):
        corpus = json.loads(valutazione.FIXTURE.read_text(encoding="utf-8"))
        self.assertIn("interamente sintetici", corpus["provenienza"])
        self.assertGreaterEqual(len(corpus["casi"]), 5)
        for caso in corpus["casi"]:
            self.assertTrue(caso["richiesti"])
            self.assertIn("vietati", caso)


if __name__ == "__main__":
    unittest.main()
