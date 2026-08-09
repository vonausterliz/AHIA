import unittest

import benchmark_pii
import pseudonimizzazione as pseudo


class BenchmarkPIITest(unittest.TestCase):
    def test_corpus_sintetico_ha_180_casi_e_offset_validi(self):
        metadata, casi = benchmark_pii.carica_corpus()
        self.assertEqual(metadata["target_cases"], 180)
        self.assertEqual(len(casi), 180)
        self.assertIn("sintetico", metadata["provenance"].lower())
        self.assertEqual(metadata["license"], "CC0-1.0")
        for caso in casi:
            for annotazione in caso.annotazioni:
                self.assertEqual(
                    caso.testo[annotazione.start:annotazione.end],
                    annotazione.valore)

    def test_motore_metriche_con_rilevatore_oracolo(self):
        _, casi = benchmark_pii.carica_corpus()
        per_testo = {
            caso.testo: [
                pseudo.Entita(a.start, a.end, a.tipo, fonte="manuale")
                for a in caso.annotazioni
            ]
            for caso in casi
        }

        rapporto = benchmark_pii.valuta(
            casi, lambda testo, profilo: per_testo[testo])
        self.assertTrue(rapporto["superato"])
        self.assertEqual(rapporto["recall"], 1.0)
        self.assertEqual(rapporto["precisione_span"], 1.0)
        self.assertEqual(rapporto["leak"], 0)
        self.assertEqual(rapporto["errori_preservazione"], 0)
        self.assertEqual(rapporto["errori_round_trip"], 0)


if __name__ == "__main__":
    unittest.main()
