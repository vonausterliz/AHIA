from pathlib import Path
import hashlib
import tempfile
import unittest
import zipfile

from tools import crea_pacchetto


class PacchettoPortabileTest(unittest.TestCase):
    def test_zip_contiene_codice_ma_non_dati_o_ambienti(self):
        with tempfile.TemporaryDirectory(prefix="ahia-package-") as tmp:
            output = Path(tmp) / "AHIA-test.zip"
            crea_pacchetto.crea(output, consenti_modifiche=True)
            with zipfile.ZipFile(output) as archivio:
                nomi = archivio.namelist()
                nome_manifest = next(
                    nome for nome in nomi
                    if nome.endswith("/MANIFEST.sha256")
                )
                manifest = archivio.read(nome_manifest).decode("utf-8")
            self.assertTrue(manifest.startswith("# versione="))
            stato = crea_pacchetto._git("status", "--porcelain")
            atteso = "true" if stato else "false"
            self.assertIn(f"\n# working_tree_dirty={atteso}\n", manifest)
            prefisso = nome_manifest.removesuffix("MANIFEST.sha256")
            with zipfile.ZipFile(output) as archivio:
                for riga in manifest.splitlines():
                    if not riga or riga.startswith("#"):
                        continue
                    attesa, relativo = riga.split("  ", 1)
                    effettiva = hashlib.sha256(
                        archivio.read(prefisso + relativo)
                    ).hexdigest()
                    self.assertEqual(attesa, effettiva)
            self.assertTrue(any(nome.endswith("/app.py") for nome in nomi))
            self.assertTrue(any(
                nome.endswith("/MANIFEST.sha256") for nome in nomi
            ))
            vietati = ("/.git/", "/.venv/", "/.ahia/", "__pycache__")
            self.assertFalse(any(
                frammento in nome for nome in nomi for frammento in vietati
            ))
            self.assertFalse(any(nome.endswith((".db", ".env")) for nome in nomi))


if __name__ == "__main__":
    unittest.main()
