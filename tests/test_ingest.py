"""Prove del motore di estrazione, separato dalla lettura del PDF.

Fino alla giuntura fra `converti` e `elabora` queste prove non erano
scrivibili: servivano un PDF su disco e un modello in esecuzione. Ora bastano
un contenuto e delle funzioni di modello finte.
"""

import unittest
from pathlib import Path
from unittest.mock import patch

import ingest


class ContenutoTest(unittest.TestCase):
    def test_il_testo_estratto_indica_un_documento_nativo(self):
        contenuto = ingest.Contenuto(testo="Referto", immagini=[])

        self.assertEqual(contenuto.origine, "nativo")

    def test_senza_testo_il_documento_e_una_scansione(self):
        contenuto = ingest.Contenuto(testo=None, immagini=["<png>"])

        self.assertEqual(contenuto.origine, "scansione")


class ConversioneTest(unittest.TestCase):
    def test_un_testo_sufficiente_non_rasterizza_il_pdf(self):
        with (
            patch.object(ingest, "_pagine_testo", return_value="R" * 120),
            patch.object(ingest, "_pagine_immagini") as rasterizza,
        ):
            contenuto = ingest.converti(Path("nativo.pdf"))

        self.assertEqual(contenuto.origine, "nativo")
        rasterizza.assert_not_called()

    def test_una_scansione_viene_rasterizzata_una_sola_volta(self):
        with (
            patch.object(ingest, "_pagine_testo", return_value=None),
            patch.object(ingest, "_pagine_immagini", return_value=["p1", "p2"]) as rasterizza,
        ):
            contenuto = ingest.converti(Path("scansione.pdf"))

        self.assertEqual(contenuto.origine, "scansione")
        self.assertEqual(contenuto.immagini, ["p1", "p2"])
        rasterizza.assert_called_once()

    def test_il_testo_mescolato_ha_piu_rumore_del_testo_clinico(self):
        pulito = "Referto firmato digitalmente con glucosio e creatinina"
        patologico = "Referto frmtnzz qwrtsdf klmnprst"

        self.assertLess(
            ingest._rumore_testo(pulito),
            ingest._rumore_testo(patologico),
        )


class ElaboraTest(unittest.TestCase):
    def setUp(self):
        self.chiamate = []
        self._chiama = ingest._chiama
        self._classifica = ingest.classifica
        self._riassumi = ingest.riassumi
        ingest.classifica = self.classifica_finta
        ingest.riassumi = self.riassumi_finta
        ingest._chiama = self.chiama_finta

    def tearDown(self):
        ingest._chiama = self._chiama
        ingest.classifica = self._classifica
        ingest.riassumi = self._riassumi

    def classifica_finta(self, model, contenuto, immagine=None):
        self.chiamate.append(("classifica", model, immagine is not None))
        return {"tipo": "analisi_sangue", "data_documento": "01/01/2020",
                "titolo": "Referto", "struttura": "Laboratorio Primo"}

    def riassumi_finta(self, model, funzione, contenuto, immagini=None):
        self.chiamate.append(("riassumi", model, funzione))
        return {"sintesi": "Quadro stabile", "conclusioni": "",
                "reperti_rilevanti": []}

    def chiama_finta(self, model, funzione, contenuto, immagini=None,
                     etichetta="", istruzione_layout=""):
        self.chiamate.append((funzione, model, etichetta))
        return ({"laboratorio": "Laboratorio Secondo",
                 "data_prelievo": "02/02/2021",
                 "esami": [{"nome_referto": "Glucosio", "valore": "95",
                            "unita": "mg/dL"}]}, {"modello": model})

    @property
    def modelli(self):
        return {"classificazione": "modello-testo",
                "estrazione_testo": "modello-testo",
                "estrazione_vision": "modello-visione",
                "analisi": "modello-testo"}

    def test_un_referto_tabellare_nativo_estrae_gli_esami_dal_testo(self):
        contenuto = ingest.Contenuto(testo="Glucosio 95 mg/dL", immagini=[])

        risultato = ingest.elabora(contenuto, self.modelli)

        self.assertEqual(risultato["origine"], "nativo")
        self.assertEqual([e["nome_referto"] for e in risultato["esami"]],
                         ["Glucosio"])
        self.assertIn(("estrazione_testo", "modello-testo", "valori"),
                      self.chiamate)

    def test_una_scansione_estrae_gli_esami_pagina_per_pagina_col_modello_vision(self):
        contenuto = ingest.Contenuto(testo=None, immagini=["<p1>", "<p2>"])

        risultato = ingest.elabora(contenuto, self.modelli)

        self.assertEqual(risultato["origine"], "scansione")
        self.assertEqual(len(risultato["esami"]), 2)
        modelli_usati = {model for funzione, model, _ in self.chiamate
                         if funzione == "estrazione_vision"}
        self.assertEqual(modelli_usati, {"modello-visione"})

    def test_data_e_laboratorio_dell_estrazione_prevalgono_sulla_classificazione(self):
        contenuto = ingest.Contenuto(testo="Glucosio 95 mg/dL", immagini=[])

        risultato = ingest.elabora(contenuto, self.modelli)

        self.assertEqual(risultato["data_documento"], "2021-02-02")
        self.assertEqual(risultato["struttura"], "Laboratorio Secondo")

    def test_il_tipo_forzato_evita_la_classificazione(self):
        contenuto = ingest.Contenuto(testo="Glucosio 95 mg/dL", immagini=[])

        risultato = ingest.elabora(contenuto, self.modelli,
                                   tipo_forzato="analisi_urine")

        self.assertEqual(risultato["tipo"], "analisi_urine")
        self.assertNotIn("classifica", [c[0] for c in self.chiamate])

    def test_un_documento_non_tabellare_produce_la_narrativa_e_non_gli_esami(self):
        self.classifica_finta = lambda model, contenuto, immagine=None: {
            "tipo": "ecografia", "data_documento": "", "titolo": "",
            "struttura": ""}
        ingest.classifica = self.classifica_finta
        contenuto = ingest.Contenuto(testo="Fegato nei limiti", immagini=[])

        risultato = ingest.elabora(contenuto, self.modelli)

        self.assertEqual(risultato["esami"], [])
        self.assertEqual(risultato["narrativa"]["sintesi"], "Quadro stabile")


if __name__ == "__main__":
    unittest.main()
