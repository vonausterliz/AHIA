import json
import sqlite3
import unittest
from unittest import mock

import catalogo_modelli as catalogo
import configurazione_modelli as configurazione
import segreti


class CatalogoModelliTest(unittest.TestCase):
    def test_normalizza_openrouter_capacita_prezzi_e_contesto(self):
        modelli = catalogo.normalizza_openrouter({"data": [{
            "id": "provider/modello-medico",
            "name": "Modello medico",
            "architecture": {"input_modalities": ["text", "image"]},
            "supported_parameters": ["tools", "reasoning"],
            "context_length": 131072,
            "pricing": {"prompt": "0.000002", "completion": "0.000008"},
            "top_provider": {"max_completion_tokens": 8192},
        }]})

        self.assertEqual(len(modelli), 1)
        modello = modelli[0]
        self.assertEqual(modello.id, "provider/modello-medico")
        self.assertEqual(modello.input, ("testo", "immagine"))
        self.assertIn("visione", modello.capacita)
        self.assertIn("strumenti", modello.capacita)
        self.assertIn("ragionamento", modello.capacita)
        self.assertEqual(modello.contesto, 131072)
        self.assertEqual(modello.costo_input_milione, 2.0)
        self.assertEqual(modello.costo_output_milione, 8.0)

    def test_cache_roundtrip(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE impostazioni (chiave TEXT PRIMARY KEY, valore TEXT NOT NULL)")
        originale = catalogo.ModelloCatalogo(
            id="x/y", nome="X", provider="openrouter",
            input=("testo",), capacita=("chat",), contesto=32000,
        )
        catalogo.salva_cache(conn, "openrouter", [originale])

        letti, aggiornato = catalogo.leggi_cache(conn, "openrouter")

        self.assertEqual(letti, [originale])
        self.assertIsNotNone(aggiornato)
        conn.close()

    @mock.patch("catalogo_modelli.request.urlopen")
    def test_errore_catalogo_non_espone_corpo_o_chiave(self, urlopen):
        urlopen.side_effect = OSError("risposta con SEGRETO")
        with self.assertRaises(catalogo.ErroreCatalogo) as contesto:
            catalogo.carica("openai", chiave="sk-SEGRETO-123456789012345")
        messaggio = str(contesto.exception)
        self.assertNotIn("SEGRETO", messaggio)
        self.assertNotIn("sk-", messaggio)


class ConfigurazioneModelliTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE impostazioni (chiave TEXT PRIMARY KEY, valore TEXT NOT NULL)"
        )

    def tearDown(self):
        self.conn.close()

    def salva(self, chiave, valore):
        self.conn.execute("INSERT OR REPLACE INTO impostazioni VALUES (?, ?)", (chiave, valore))
        self.conn.commit()

    def test_automatico_riduce_nove_funzioni_a_quattro_ruoli(self):
        disponibili = [
            "qwen3:14b", "qwen3:30b", "qwen2.5vl:7b", "bge-m3",
        ]
        risultato = configurazione.risolvi(self.conn, disponibili)

        self.assertEqual(risultato["modalita"], "automatico")
        self.assertEqual(set(risultato["ruoli"]), set(configurazione.RUOLI))
        self.assertEqual(risultato["scelte"]["classificazione"], "qwen3:14b")
        self.assertEqual(risultato["scelte"]["analisi"], "qwen3:30b")
        self.assertEqual(risultato["scelte"]["estrazione_vision"], "qwen2.5vl:7b")
        self.assertEqual(risultato["embedding"], "bge-m3")

    def test_riconosce_la_variante_qwen_instruct_installata(self):
        ruoli = configurazione.assegna_ruoli(
            ["deepseek-r1:latest", "qwen3:30b-instruct", "llama3.3:latest"],
            "equilibrato",
        )
        self.assertEqual(ruoli["rapido"], "qwen3:30b-instruct")
        self.assertEqual(ruoli["approfondito"], "qwen3:30b-instruct")

    def test_impostazione_storica_attiva_modalita_personalizzata(self):
        self.salva("modello.analisi", "modello-storico:latest")

        risultato = configurazione.risolvi(self.conn, ["qwen3:14b"])

        self.assertEqual(risultato["modalita"], "personalizzato")
        self.assertEqual(risultato["scelte"]["analisi"], "modello-storico:latest")

    def test_override_di_ruolo_si_applica_senza_eccezioni_per_funzione(self):
        self.salva("modelli.modalita", "personalizzato")
        self.salva("modelli.ruolo.approfondito", "modello-grande:latest")

        risultato = configurazione.risolvi(
            self.conn, ["qwen3:14b", "modello-grande:latest"]
        )

        self.assertEqual(risultato["scelte"]["analisi"], "modello-grande:latest")
        self.assertEqual(
            risultato["scelte"]["diagnosi_estrazione"], "modello-grande:latest"
        )

    def test_filtra_modelli_per_visione_ed_embedding(self):
        disponibili = ["qwen3:14b", "qwen2.5vl:7b", "bge-m3"]
        self.assertEqual(
            configurazione.compatibili_per_ruolo(disponibili, "visione"),
            ["qwen2.5vl:7b"],
        )
        self.assertEqual(
            configurazione.compatibili_per_ruolo(disponibili, "embedding"),
            ["bge-m3"],
        )


class OpenRouterTest(unittest.TestCase):
    @mock.patch("segreti._chiama")
    def test_invio_impone_policy_privacy_e_nessun_fallback(self, chiama):
        chiama.return_value = {"choices": [{"message": {"content": "ok"}}]}

        risposta = segreti.invia(
            "openrouter", "sk-or-12345678901234567890", "payload opaco",
            modello="anthropic/test",
        )

        self.assertEqual(risposta, "ok")
        url, intestazioni, payload = chiama.call_args.args
        self.assertEqual(url, "https://eu.openrouter.ai/api/v1/chat/completions")
        self.assertNotIn("payload opaco", json.dumps(intestazioni))
        self.assertEqual(payload["model"], "anthropic/test")
        self.assertEqual(payload["provider"], {
            "zdr": True,
            "data_collection": "deny",
            "allow_fallbacks": False,
        })


if __name__ == "__main__":
    unittest.main()
