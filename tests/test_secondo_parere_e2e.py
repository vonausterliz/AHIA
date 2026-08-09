import unittest

import pseudonimizzazione as pseudo
import secondo_parere_e2e


class SecondoParereE2ETest(unittest.TestCase):
    def test_nessuna_pii_al_provider_e_reidratazione_della_risposta(self):
        testo = ("Paziente Ada Quercia; referto RF-728190. "
                 "Richiedo un secondo parere.")
        valori = ("Ada Quercia", "RF-728190")
        entita = []
        for valore, tipo in zip(
                valori, ("PAZIENTE", "IDENTIFICATIVO_DOCUMENTO")):
            inizio = testo.index(valore)
            entita.append(pseudo.Entita(
                inizio, inizio + len(valore), tipo, fonte="manuale"))
        payload_ricevuti = []

        def provider_finto(payload):
            payload_ricevuti.append(payload)
            self.assertNotIn(valori[0], payload)
            self.assertNotIn(valori[1], payload)
            token = pseudo.TOKEN_RE.findall(payload)
            return "Valutazione per " + " e ".join(token) + ": quadro stabile."

        esito = secondo_parere_e2e.esegui(testo, entita, provider_finto)

        self.assertEqual(len(payload_ricevuti), 1)
        self.assertIn(valori[0], esito.risposta_reidratata)
        self.assertIn(valori[1], esito.risposta_reidratata)
        self.assertNotIn(valori[0], esito.risposta_pseudonima)
        self.assertFalse(esito.token_sconosciuti)
        self.assertFalse(esito.token_malformati)


if __name__ == "__main__":
    unittest.main()
