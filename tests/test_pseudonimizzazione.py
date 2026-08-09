import re
import unittest

import pseudonimizzazione as ps


class MotorePseudonimizzazioneTest(unittest.TestCase):
    def test_token_opaco_e_round_trip(self):
        testo = "Il paziente Mario Rossi vive a Roma."
        entita = [
            ps.Entita(12, 23, "PAZIENTE", fonte="manuale"),
            ps.Entita(31, 35, "LOCALITA", fonte="manuale"),
        ]
        casuali = iter(["A" * 24, "B" * 24])
        esito = ps.pseudonimizza(testo, entita,
                                 generatore=lambda: next(casuali))

        self.assertEqual(
            esito.testo,
            "Il paziente [[AAAAAAAAAAAAAAAAAAAAAAAA]] vive a "
            "[[BBBBBBBBBBBBBBBBBBBBBBBB]].",
        )
        self.assertNotIn("PAZIENTE", esito.testo)
        self.assertNotIn("LOCALITA", esito.testo)
        self.assertEqual(ps.reidrata(esito.testo, esito.sessione).testo, testo)

    def test_stesso_valore_usa_lo_stesso_token(self):
        testo = "Mario Rossi incontra MARIO ROSSI."
        entita = [
            ps.Entita(0, 11, "PERSONA"),
            ps.Entita(21, 32, "PERSONA"),
        ]
        esito = ps.pseudonimizza(
            testo, entita, generatore=lambda: "C" * 24)
        token = "[[CCCCCCCCCCCCCCCCCCCCCCCC]]"
        self.assertEqual(esito.testo.count(token), 2)
        self.assertEqual(len(esito.sessione.token_a_valore), 1)

    def test_sessioni_diverse_non_correlabili(self):
        testo = "Mario Rossi"
        entita = [ps.Entita(0, len(testo), "PERSONA")]
        prima = ps.pseudonimizza(
            testo, entita, generatore=lambda: "D" * 24)
        seconda = ps.pseudonimizza(
            testo, entita, generatore=lambda: "E" * 24)
        self.assertNotEqual(prima.testo, seconda.testo)

    def test_profilo_preferisce_nome_completo(self):
        testo = "Paziente Mario Rossi, controllo annuale."
        entita = ps.rileva_profilo(testo, {"nome": "Mario Rossi"})
        risolte = ps.risolvi_sovrapposizioni(testo, entita)
        self.assertEqual(len(risolte), 1)
        self.assertEqual(testo[risolte[0].start:risolte[0].end], "Mario Rossi")

    def test_token_sconosciuto_non_viene_reidratato(self):
        sessione = ps.SessionePseudonimi()
        sconosciuto = "[[FFFFFFFFFFFFFFFFFFFFFFFF]]"
        esito = ps.reidrata(f"Risposta per {sconosciuto}", sessione)
        self.assertIn(sconosciuto, esito.testo)
        self.assertEqual(esito.token_sconosciuti, [sconosciuto])

    def test_token_malformato_non_viene_corretto(self):
        token = "[[PERSONA_01]]"
        esito = ps.reidrata(token, ps.SessionePseudonimi())
        self.assertEqual(esito.testo, token)
        self.assertEqual(esito.token_malformati, [token])

    def test_segnalazione_manuale_sostituisce_solo_occorrenze_scelte(self):
        testo = "Roma, poi Roma e infine Roma."
        occorrenze = ps.trova_occorrenze(testo, "Roma")
        entita = ps.rileva_valore(testo, "Roma", "LOCALITA", [occorrenze[1]])
        esito = ps.pseudonimizza(
            testo, entita, generatore=lambda: "1" * 24)
        self.assertEqual(esito.testo.count("Roma"), 2)
        self.assertIn("[[111111111111111111111111]]", esito.testo)

    def test_verifica_payload_rileva_valore_ricomparso(self):
        testo = "Mario Rossi"
        esito = ps.pseudonimizza(
            testo, [ps.Entita(0, len(testo), "PERSONA")],
            generatore=lambda: "2" * 24)
        payload_modificato = esito.testo + " Mario Rossi"
        self.assertTrue(any("valori originali" in a
                            for a in ps.verifica_payload(
                                payload_modificato, esito.sessione)))

    def test_valore_breve_non_viene_cercato_dentro_altre_parole(self):
        esito = ps.pseudonimizza(
            "MI", [ps.Entita(0, 2, "LOCALITA")],
            generatore=lambda: "3" * 24)
        payload = esito.testo + " termini clinici"
        self.assertFalse(any("valori originali" in a
                             for a in ps.verifica_payload(
                                 payload, esito.sessione)))

    def test_dimentica_svuota_tutta_la_mappa(self):
        esito = ps.pseudonimizza(
            "Mario", [ps.Entita(0, 5, "PERSONA")],
            generatore=lambda: "4" * 24)
        esito.sessione.dimentica()
        self.assertEqual(esito.sessione.token_a_valore, {})
        self.assertEqual(esito.sessione.token_a_tipo, {})
        self.assertEqual(esito.sessione.valore_a_token, {})
        self.assertEqual(esito.sessione.impronta_payload, "")

    def test_recognizer_legacy_non_modifica_il_testo(self):
        testo = ("Codice RSSMRA80A01H501U, email mario@example.it, "
                 "referto AB123456 e data 12/03/2024.")
        entita = ps.rileva_legacy(testo)
        tipi = {e.tipo for e in entita}
        self.assertIn("CODICE_FISCALE", tipi)
        self.assertIn("CONTATTO", tipi)
        self.assertIn("IDENTIFICATIVO_DOCUMENTO", tipi)
        self.assertIn("DATA_CLINICA", tipi)
        self.assertEqual(testo.count("["), 0)

    def test_medico_non_scambia_dr_interno_a_un_nome(self):
        testo = "Il caregiver Andrea Gallo riferisce buona aderenza."
        entita = ps.rileva_legacy(testo)
        self.assertFalse(any(e.tipo == "MEDICO" for e in entita))

    def test_token_ha_esattamente_96_bit_esadecimali(self):
        esito = ps.pseudonimizza(
            "Mario", [ps.Entita(0, 5, "PERSONA")])
        self.assertRegex(esito.testo, re.compile(r"^\[\[[0-9A-F]{24}\]\]$"))

    def test_regola_personale_rispetta_i_confini_e_ha_priorita(self):
        testo = "Mario visita il poliambulatorio Mariologia con Mario."
        entita = ps.rileva_regole_personali(
            testo, [("Mario", "PERSONA")])
        self.assertEqual([testo[e.start:e.end] for e in entita],
                         ["Mario", "Mario"])
        self.assertTrue(all(e.fonte == "personale" for e in entita))


if __name__ == "__main__":
    unittest.main()
