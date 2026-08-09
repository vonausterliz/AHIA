import json
from pathlib import Path
import unittest

import pseudonimizzazione as ps


CORPUS = Path(__file__).parent / "fixtures" / "pseudonimizzazione_corpus.json"


class CorpusPseudonimizzazioneTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = json.loads(CORPUS.read_text(encoding="utf-8"))

    def test_corpus_sintetico_anti_leak_e_round_trip(self):
        for caso in self.corpus["cases"]:
            with self.subTest(caso=caso["id"]):
                testo = caso["text"]
                rilevate = ps.rileva_profilo(testo, caso.get("profile"))
                rilevate.extend(ps.rileva_legacy(testo))
                risolte = ps.risolvi_sovrapposizioni(testo, rilevate)

                tipi = {entita.tipo for entita in risolte}
                self.assertTrue(set(caso["expected_types"]).issubset(tipi))

                esito = ps.pseudonimizza(testo, risolte)
                payload_casefold = esito.testo.casefold()
                for valore in caso["must_not_leak"]:
                    self.assertNotIn(valore.casefold(), payload_casefold)
                for valore in caso["must_preserve"]:
                    self.assertIn(valore, esito.testo)

                self.assertEqual(ps.reidrata(esito.testo, esito.sessione).testo,
                                 testo)
                self.assertEqual(ps.TOKEN_RE.findall(esito.testo),
                                 ps.TOKEN_SIMILE_RE.findall(esito.testo))

                if "expected_occurrences" in caso:
                    self.assertEqual(len(ps.TOKEN_RE.findall(esito.testo)),
                                     caso["expected_occurrences"])
                if "expected_distinct_tokens" in caso:
                    self.assertEqual(len(set(ps.TOKEN_RE.findall(esito.testo))),
                                     caso["expected_distinct_tokens"])

    def test_corpus_dichiara_provenienza_sintetica(self):
        self.assertIn("sintetico", self.corpus["provenance"].lower())
        self.assertGreaterEqual(len(self.corpus["cases"]), 15)


if __name__ == "__main__":
    unittest.main()
