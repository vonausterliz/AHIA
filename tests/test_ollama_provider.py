import json
import unittest
from unittest import mock

import ollama_provider


class _Risposta:
    def __init__(self, dati):
        self.dati = dati

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.dati).encode("utf-8")


class OllamaProviderTest(unittest.TestCase):
    @mock.patch("ollama_provider.request.urlopen")
    def test_invia_chat_non_streaming_senza_esporre_prompt(self, urlopen):
        urlopen.return_value = _Risposta(
            {"message": {"content": "Risposta locale"}})

        risposta = ollama_provider.invia(
            "dato sensibile", "modello-test",
            host="http://127.0.0.1:11434", timeout=3)

        self.assertEqual(risposta, "Risposta locale")
        richiesta = urlopen.call_args.args[0]
        corpo = json.loads(richiesta.data)
        self.assertFalse(corpo["stream"])
        self.assertFalse(corpo["think"])
        self.assertEqual(corpo["model"], "modello-test")
        self.assertEqual(corpo["messages"][0]["content"], "dato sensibile")

    def test_rifiuta_host_non_http(self):
        with self.assertRaises(ollama_provider.ErroreOllama):
            ollama_provider.invia("test", "modello", host="file:///tmp/x")

    @mock.patch("ollama_provider.request.urlopen")
    def test_errore_non_contiene_il_prompt(self, urlopen):
        urlopen.side_effect = OSError("errore simulato")
        segreto = "PAZIENTE SEGRETISSIMO"
        with self.assertRaises(ollama_provider.ErroreOllama) as contesto:
            ollama_provider.invia(segreto, "modello")
        self.assertNotIn(segreto, str(contesto.exception))


if __name__ == "__main__":
    unittest.main()
