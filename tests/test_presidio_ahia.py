import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import presidio_ahia


class PresidioAdapterTest(unittest.TestCase):
    def test_persona_richiede_forma_da_nome_proprio(self):
        risultato = SimpleNamespace(
            start=0, end=len("Acido folico"), entity_type="PERSON", score=0.9
        )
        self.assertFalse(
            presidio_ahia._accetta_risultato_ner("Acido folico 8 ng/mL", risultato)
        )
        nome = SimpleNamespace(
            start=0, end=len("Mario Rossi"), entity_type="PERSON", score=0.9
        )
        self.assertTrue(
            presidio_ahia._accetta_risultato_ner("Mario Rossi", nome)
        )

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

    def test_soglia_specifica_per_tipo_prevale_sulla_globale(self):
        with patch.dict(os.environ, {
                "AHIA_PRESIDIO_SCORE": "0.55",
                "AHIA_PRESIDIO_SCORE_PERSON": "0.72",
        }):
            self.assertEqual(
                presidio_ahia.soglia_configurata("PERSON"), 0.72)
            self.assertEqual(
                presidio_ahia.soglia_configurata("LOCATION"), 0.55)

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
                    SimpleNamespace(start=0, end=5, entity_type="LOCATION",
                                    score=0.20),
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

    def test_filtro_ner_protegge_nomi_e_localita_ma_non_analiti(self):
        class AnalyzerFinto:
            def analyze(self, **kwargs):
                return [
                    SimpleNamespace(start=3, end=14, entity_type="PERSON",
                                    score=0.85),
                    SimpleNamespace(start=23, end=29, entity_type="LOCATION",
                                    score=0.85),
                    SimpleNamespace(start=31, end=40, entity_type="LOCATION",
                                    score=0.85),
                ]

        testo = "Da Mario Rossi, vive a Milano. Ferritina normale."
        presidio_ahia._analyzer = AnalyzerFinto()
        with patch.dict(os.environ, {"AHIA_PRESIDIO_ENABLED": "1"}):
            entita, _ = presidio_ahia.rileva_presidio(testo)
        self.assertEqual(
            [(e.tipo, testo[e.start:e.end]) for e in entita],
            [("PERSONA", "Mario Rossi"), ("LOCALITA", "Milano")])


if __name__ == "__main__":
    unittest.main()
