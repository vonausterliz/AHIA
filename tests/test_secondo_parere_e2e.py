import unittest

import pseudonimizzazione as pseudo
import secondo_parere_e2e
import benchmark_estrazione
import presidio_ahia


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

    def test_token_alterato_non_viene_reidratato_per_approssimazione(self):
        testo = "Paziente Ada Quercia: quadro stabile."
        inizio = testo.index("Ada Quercia")
        entita = [pseudo.Entita(
            inizio, inizio + len("Ada Quercia"), "PAZIENTE", fonte="manuale"
        )]

        def provider(payload):
            token = pseudo.TOKEN_RE.search(payload).group(0)
            return token[:-3] + "XX]]"

        esito = secondo_parere_e2e.esegui(testo, entita, provider)
        self.assertNotIn("Ada Quercia", esito.risposta_reidratata)
        self.assertTrue(esito.token_malformati)


    def test_identita_del_corpus_non_raggiunge_il_provider(self):
        _, casi = benchmark_estrazione.carica_corpus()
        testo = casi[0]["testo"]
        identita = casi[0]["truth"]["paziente"]["nome_completo"]
        entita, _ = presidio_ahia.rileva(
            testo, profilo={"nome": identita}
        )
        payload_ricevuti = []

        def provider(payload):
            payload_ricevuti.append(payload)
            self.assertNotIn(identita, payload)
            return "Valutazione ricevuta."

        esito = secondo_parere_e2e.esegui(testo, entita, provider)

        self.assertEqual(len(payload_ricevuti), 1)
        self.assertNotIn(identita, esito.payload)
        self.assertNotIn(identita, esito.risposta_pseudonima)


if __name__ == "__main__":
    unittest.main()
