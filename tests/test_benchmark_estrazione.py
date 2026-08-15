import unittest

import benchmark_estrazione


class BenchmarkEstrazioneTest(unittest.TestCase):
    def test_corpus_predefinito_e_output_diretto_di_faking_meddoc(self):
        metadata, casi = benchmark_estrazione.carica_corpus()

        self.assertEqual(metadata["kind"], "faking_meddoc_text_truth_corpus")
        self.assertEqual(metadata["generation"]["generator_version"], "0.2.22")
        self.assertEqual(
            [caso["truth"]["seed"] for caso in casi],
            [12001, 12002, 12005],
        )
        for caso in casi:
            truth = caso["truth"]
            self.assertEqual(truth["generator_version"], "0.2.22")
            self.assertIn(truth["paziente"]["nome_completo"], caso["testo"])
            for esame in truth["esami"]:
                self.assertIn(esame["nome"], caso["testo"])
                self.assertIn(esame["unita"], caso["testo"])

    def test_metriche_contano_mancanti_errori_e_allucinazioni(self):
        manifest = {
            "esami": [
                {"nome": "Glicemia", "valore": 95, "unita": "mg/dL"},
                {"nome": "Emoglobina", "valore": 14.2, "unita": "g/dL"},
            ]
        }
        estratti = [
            {"nome_referto": "Glucosio", "valore": "96", "unita": "mg/dL"},
            {"nome_referto": "Creatinina", "valore": "1.0", "unita": "mg/dL"},
        ]

        rapporto = benchmark_estrazione.valuta_manifest(manifest, estratti)

        self.assertEqual(rapporto["attesi"], 2)
        self.assertEqual(rapporto["trovati"], 1)
        self.assertEqual(rapporto["mancanti"], ["EMOGLOBINA"])
        self.assertEqual(rapporto["errori_valore"], ["GLUCOSIO"])
        self.assertEqual(rapporto["allucinazioni"], 1)
        self.assertEqual(rapporto["analiti_allucinati"], ["CREATININA"])

    def test_unita_convertibili_sono_confrontate_dopo_normalizzazione(self):
        manifest = {
            "esami": [
                {"nome": "Glicemia", "valore": 5.5, "unita": "mmol/L"},
            ]
        }
        estratti = [
            {"nome_referto": "S-Glucosio", "valore": "5,5",
             "unita": "mmol/L"},
        ]

        rapporto = benchmark_estrazione.valuta_manifest(manifest, estratti)

        self.assertEqual(rapporto["recall_analiti"], 1.0)
        self.assertEqual(rapporto["accuratezza_valori"], 1.0)
        self.assertEqual(rapporto["accuratezza_unita"], 1.0)


if __name__ == "__main__":
    unittest.main()
