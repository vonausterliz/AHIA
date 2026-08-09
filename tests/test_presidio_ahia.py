import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import presidio_ahia


class PresidioAdapterTest(unittest.TestCase):
    def tearDown(self):
        presidio_ahia._reset_cache_per_test()

    def test_disattivazione_esplicita_mantiene_i_recognizer_ahia(self):
        testo = "Paziente Mario Rossi, CF RSSMRA80A01H501U"
        with patch.dict(os.environ, {"AHIA_PRESIDIO_ENABLED": "0"}):
            entita, stato = presidio_ahia.rileva(
                testo, {"nome": "Mario Rossi"})
        self.assertFalse(stato.attivo)
        self.assertIn("PAZIENTE", {e.tipo for e in entita})
        self.assertIn("CODICE_FISCALE", {e.tipo for e in entita})

    def test_soglia_non_valida_usa_default(self):
        with patch.dict(os.environ, {"AHIA_PRESIDIO_SCORE": "non-numero"}):
            self.assertEqual(presidio_ahia.soglia_configurata(), 0.55)

    def test_tipi_presidio_non_diventano_tag_semantici(self):
        self.assertEqual(presidio_ahia._TIPI["PERSON"], "PERSONA")
        self.assertEqual(presidio_ahia._TIPI["IT_FISCAL_CODE"],
                         "CODICE_FISCALE")

    def test_senza_dipendenza_restituisce_stato_degradato(self):
        with patch.dict(os.environ, {"AHIA_PRESIDIO_ENABLED": "1"}), \
                patch.object(presidio_ahia, "_crea_analyzer",
                             side_effect=ModuleNotFoundError("presidio")):
            _, stato = presidio_ahia.rileva_presidio("Mario Rossi")
        self.assertFalse(stato.attivo)
        self.assertFalse(stato.disponibile)
        self.assertTrue(stato.dettaglio)

    def test_risultati_presidio_sono_convertiti_in_span_ahia(self):
        class AnalyzerFinto:
            def analyze(self, **kwargs):
                self.kwargs = kwargs
                return [
                    SimpleNamespace(start=0, end=11, entity_type="PERSON",
                                    score=0.87),
                    SimpleNamespace(start=12, end=40,
                                    entity_type="ORGANIZATION", score=0.80),
                ]

        analyzer = AnalyzerFinto()
        presidio_ahia._analyzer = analyzer
        testo = "Mario Rossi [[AAAAAAAAAAAAAAAAAAAAAAAA]]"
        with patch.dict(os.environ, {"AHIA_PRESIDIO_ENABLED": "1"}):
            entita, stato = presidio_ahia.rileva_presidio(testo)

        self.assertTrue(stato.attivo)
        self.assertEqual([(e.tipo, testo[e.start:e.end]) for e in entita],
                         [("PERSONA", "Mario Rossi")])
        self.assertEqual(analyzer.kwargs["language"], "it")


if __name__ == "__main__":
    unittest.main()
