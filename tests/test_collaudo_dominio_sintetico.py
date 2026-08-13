import hashlib
import unittest

import benchmark_estrazione
import core
import grafici
import ingest


class CollaudoDominioSinteticoTest(unittest.TestCase):
    def setUp(self):
        self.metadata, self.casi = benchmark_estrazione.carica_corpus()
        self.alias = ingest.carica_alias(
            benchmark_estrazione.CORPUS_PREDEFINITO.with_name("non-esiste.json")
        )
        self.conn = core.apri_db(":memory:")

    def tearDown(self):
        self.conn.close()

    def _normalizza_caso(self, caso):
        sconosciuti = set()
        righe = []
        for esame in caso["truth"]["esami"]:
            riga = ingest.normalizza({
                "nome_referto": esame["nome"],
                "valore": str(esame["valore"]).replace(".", ","),
                "unita": esame["unita"],
                "range_min": esame.get("range_min"),
                "range_max": esame.get("range_max"),
                "flag": "",
            }, self.alias, sconosciuti)
            self.assertIsNotNone(riga)
            righe.append(riga)
        self.assertFalse(sconosciuti)
        return righe

    def test_alias_unita_e_flag_sono_deterministici(self):
        risultati = [self._normalizza_caso(caso)[0] for caso in self.casi]

        self.assertEqual({r["analita"] for r in risultati}, {"GLUCOSIO"})
        self.assertEqual(
            [r["flag"] for r in risultati],
            [caso["truth"]["esami"][0]["flag"] for caso in self.casi],
        )
        self.assertEqual({r["unita"] for r in risultati}, {"mg/dL"})
        self.assertAlmostEqual(risultati[1]["valore"], 99.1001, places=4)

    def test_deduplica_e_serie_storica_usano_la_verita_nota(self):
        for caso in self.casi:
            truth = caso["truth"]
            righe = self._normalizza_caso(caso)
            sha = hashlib.sha256(caso["id"].encode()).hexdigest()
            inserite = core.salva_referto(
                self.conn,
                sha,
                caso["id"] + ".txt",
                "nativo",
                {
                    "data_prelievo": truth["data"],
                    "laboratorio": truth["laboratorio"]["nome"],
                },
                righe,
            )
            self.assertEqual(inserite, 1)

        duplicato = self.casi[-1]
        inserite = core.salva_referto(
            self.conn,
            "sha-duplicato",
            "duplicato.txt",
            "nativo",
            {
                "data_prelievo": duplicato["truth"]["data"],
                "laboratorio": duplicato["truth"]["laboratorio"]["nome"],
            },
            self._normalizza_caso(duplicato),
        )
        self.assertEqual(inserite, 0)
        self.assertEqual(core.numero_prelievi(self.conn), len(self.casi))
        self.assertEqual(core.misure_duplicate(self.conn), [])

        serie = grafici.serie_df(self.conn, ["GLUCOSIO"])
        self.assertEqual(len(serie), len(self.casi))
        self.assertEqual(
            serie["data"].dt.date.astype(str).tolist(),
            [caso["truth"]["data"] for caso in self.casi],
        )
        self.assertEqual(serie["flag"].tolist(), ["N", "N", "L"])


if __name__ == "__main__":
    unittest.main()
