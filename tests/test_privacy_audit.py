import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from urllib import error

import config
import core
import pseudonimizzazione as pseudo
import secondo_parere_e2e
import segreti


class PrivacyAuditTest(unittest.TestCase):
    def test_archivi_di_utenti_diversi_hanno_radici_fisiche_distinte(self):
        with tempfile.TemporaryDirectory(prefix="ahia-isolamento-") as tmp:
            with mock.patch.object(config, "ARCHIVI_DIR", Path(tmp)):
                primo = config.Archivio(101)
                secondo = config.Archivio(202)
                self.assertNotEqual(primo.dir, secondo.dir)
                self.assertFalse(primo.dir.is_relative_to(secondo.dir))
                self.assertFalse(secondo.dir.is_relative_to(primo.dir))

    def test_registro_non_conserva_dettagli_non_dichiarati_sicuri(self):
        with tempfile.TemporaryDirectory(prefix="ahia-log-") as tmp:
            conn = core.apri_db(Path(tmp) / "salute.db")
            sensibile = "Ada Quercia glicemia 94 [[AAAAAAAAAAAAAAAAAAAAAAAA]]"
            core.registra_evento(
                conn, "errore", categoria="provider", dettaglio=sensibile
            )
            salvato = conn.execute(
                "SELECT dettaglio FROM eventi ORDER BY id DESC LIMIT 1"
            ).fetchone()["dettaglio"]
            self.assertEqual(salvato, "")

    @mock.patch("segreti.urllib.request.urlopen")
    def test_errore_provider_non_riflette_payload_o_chiave(self, urlopen):
        payload = "Ada Quercia [[AAAAAAAAAAAAAAAAAAAAAAAA]]"
        chiave = "sk-segreta-12345678901234567890"
        corpo = json.dumps({"error": {"message": payload + chiave}}).encode()
        urlopen.side_effect = error.HTTPError(
            "https://example.invalid", 500, "errore", {}, io.BytesIO(corpo)
        )
        with self.assertRaises(segreti.ErroreAPI) as contesto:
            segreti.invia("openai", chiave, payload)
        messaggio = str(contesto.exception)
        self.assertNotIn(payload, messaggio)
        self.assertNotIn(chiave, messaggio)

    def test_tutti_i_provider_ricevono_solo_payload_pseudonimizzato(self):
        testo = "Paziente Ada Quercia, referto RF-728190."
        valori = ("Ada Quercia", "RF-728190")
        entita = []
        for valore, tipo in zip(
            valori, ("PAZIENTE", "IDENTIFICATIVO_DOCUMENTO")
        ):
            inizio = testo.index(valore)
            entita.append(pseudo.Entita(
                inizio, inizio + len(valore), tipo, fonte="manuale"
            ))

        for fornitore in segreti.FORNITORI:
            with self.subTest(fornitore=fornitore), mock.patch(
                "segreti._chiama"
            ) as chiama:
                if fornitore == "anthropic":
                    chiama.return_value = {
                        "content": [{"type": "text", "text": "ok"}]
                    }
                else:
                    chiama.return_value = {
                        "choices": [{"message": {"content": "ok"}}]
                    }

                def provider(payload):
                    return segreti.invia(
                        fornitore, "sk-test-12345678901234567890", payload
                    )

                secondo_parere_e2e.esegui(testo, entita, provider)
                richiesta = json.dumps(
                    chiama.call_args.args[2], ensure_ascii=False
                )
                self.assertNotIn(valori[0], richiesta)
                self.assertNotIn(valori[1], richiesta)


if __name__ == "__main__":
    unittest.main()
