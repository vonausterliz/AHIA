import json
import re
import sqlite3
import unittest

import regole_pii
import segreti


class RegolePIITest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        segreti.prepara(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_valori_e_categorie_sono_cifrati(self):
        regole_pii.salva(
            self.conn, 7, "Password!123", "Dottor Mario Riservato", "MEDICO")
        riga = self.conn.execute(
            "SELECT nome, valore FROM segreti WHERE utente_id=7").fetchone()
        self.assertEqual(riga["nome"], regole_pii.NOME_SEGRETO)
        self.assertNotIn(b"Mario Riservato", riga["valore"])
        self.assertNotIn(b"MEDICO", riga["valore"])

        caricate = regole_pii.carica(self.conn, 7, "Password!123")
        self.assertEqual([(r.valore, r.tipo, r.attiva) for r in caricate],
                         [("Dottor Mario Riservato", "MEDICO", True)])

    def test_regole_isolate_per_utente(self):
        regole_pii.salva(self.conn, 1, "Password!123", "Mario Alfa", "PERSONA")
        regole_pii.salva(self.conn, 2, "Password!456", "Giulia Beta", "PERSONA")
        prima = regole_pii.carica(self.conn, 1, "Password!123")
        seconda = regole_pii.carica(self.conn, 2, "Password!456")
        self.assertEqual([r.valore for r in prima], ["Mario Alfa"])
        self.assertEqual([r.valore for r in seconda], ["Giulia Beta"])

    def test_password_errata_non_decifra(self):
        regole_pii.salva(self.conn, 1, "Password!123", "Mario Alfa", "PERSONA")
        with self.assertRaises(regole_pii.RegoleNonDecifrabili):
            regole_pii.carica(self.conn, 1, "Password!999")

    def test_salvataggio_duplicato_aggiorna_e_riattiva(self):
        prima = regole_pii.salva(
            self.conn, 1, "Password!123", "Mario Alfa", "PERSONA")
        regole_pii.aggiorna(
            self.conn, 1, "Password!123", prima.id,
            valore="Mario Alfa", tipo="PERSONA", attiva=False)
        seconda = regole_pii.salva(
            self.conn, 1, "Password!123", "  MARIO ALFA  ", "PAZIENTE")
        caricate = regole_pii.carica(self.conn, 1, "Password!123")
        self.assertEqual(len(caricate), 1)
        self.assertEqual(seconda.id, prima.id)
        self.assertTrue(caricate[0].attiva)
        self.assertEqual(caricate[0].tipo, "PAZIENTE")

    def test_modifica_disattivazione_ed_eliminazione(self):
        regola = regole_pii.salva(
            self.conn, 1, "Password!123", "Mario Alfa", "PERSONA")
        aggiornata = regole_pii.aggiorna(
            self.conn, 1, "Password!123", regola.id,
            valore="Mario Gamma", tipo="MEDICO", attiva=False)
        self.assertEqual(aggiornata.valore, "Mario Gamma")
        self.assertEqual(regole_pii.attive([aggiornata]), [])
        self.assertTrue(regole_pii.elimina(
            self.conn, 1, "Password!123", regola.id))
        self.assertEqual(regole_pii.carica(self.conn, 1, "Password!123"), [])

    def test_limiti_impediscono_referti_interi_e_token(self):
        with self.assertRaises(regole_pii.ErroreRegole):
            regole_pii.salva(self.conn, 1, "Password!123", "AB", "ALTRO_PII")
        with self.assertRaises(regole_pii.ErroreRegole):
            regole_pii.salva(
                self.conn, 1, "Password!123", "X" * 121, "ALTRO_PII")
        with self.assertRaises(regole_pii.ErroreRegole):
            regole_pii.salva(
                self.conn, 1, "Password!123", "[[AAAAAAAAAAAAAAAAAAAAAAAA]]",
                "ALTRO_PII")

    def test_export_non_contiene_pii_segnalata(self):
        testo = ("Controllo per Mario Riservato: HbA1c 6,2%. "
                 "Rivedere Mario Riservato tra sei mesi.")
        occorrenze = [(m.start(), m.end())
                      for m in re.finditer("Mario Riservato", testo)]
        caso = regole_pii.crea_caso_miglioramento(
            testo, "Mario Riservato", "PERSONA", occorrenze)
        esportato = json.dumps(caso, ensure_ascii=False)
        self.assertNotIn("Mario Riservato", esportato)
        self.assertEqual(
            sum(c.count("[[PII_SEGNALATA]]") for c in caso["contesti"]), 2)
        self.assertTrue(caso["revisione_privacy_richiesta"])

    def test_export_richiede_almeno_un_occorrenza(self):
        with self.assertRaises(regole_pii.ErroreRegole):
            regole_pii.crea_caso_miglioramento(
                "Mario Riservato", "Mario Riservato", "PERSONA", [])


if __name__ == "__main__":
    unittest.main()
