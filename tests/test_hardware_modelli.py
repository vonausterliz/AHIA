import unittest
from unittest import mock

import hardware_modelli


class HardwareModelliTest(unittest.TestCase):
    def test_equilibrato_su_12_gb_vram(self):
        hardware = hardware_modelli.ProfiloHardware(
            ram_gb=64,
            vram_gb=12,
            gpu="RTX test",
            architettura="x86_64",
        )

        modelli = hardware_modelli.raccomanda(hardware, "equilibrato")

        self.assertEqual(modelli, {
            "rapido": "qwen3:8b",
            "approfondito": "qwen3:14b",
            "visione": "qwen3-vl:8b",
            "embedding": "bge-m3",
        })
        self.assertEqual(
            hardware_modelli.esecuzione_prevista(hardware, "qwen3:14b"),
            "interamente su GPU",
        )
        self.assertEqual(
            hardware_modelli.esecuzione_prevista(
                hardware, "qwen3:30b-instruct"
            ),
            "in GPU/RAM, più lento",
        )

    def test_macchina_compatta_riduce_dimensione_e_embedding(self):
        hardware = hardware_modelli.ProfiloHardware(
            ram_gb=12,
            vram_gb=0,
            gpu="",
            architettura="x86_64",
        )

        modelli = hardware_modelli.raccomanda(hardware, "equilibrato")

        self.assertEqual(modelli["rapido"], "qwen3:4b")
        self.assertEqual(modelli["visione"], "qwen3-vl:4b")
        self.assertEqual(modelli["embedding"], "nomic-embed-text")

    def test_memoria_unificata_viene_usata_come_acceleratore(self):
        hardware = hardware_modelli.ProfiloHardware(
            ram_gb=32,
            vram_gb=32,
            gpu="Apple Silicon",
            architettura="arm64",
            memoria_unificata=True,
        )

        modelli = hardware_modelli.raccomanda(hardware, "qualita")

        self.assertEqual(modelli["approfondito"], "qwen3:30b-instruct")
        self.assertEqual(modelli["visione"], "qwen3-vl:30b")
        self.assertEqual(
            hardware_modelli.esecuzione_prevista(
                hardware, "qwen3:30b-instruct"
            ),
            "in memoria unificata",
        )

    @mock.patch("hardware_modelli.subprocess.run")
    def test_rilevazione_nvidia_somma_la_vram(self, esegui):
        esegui.return_value.returncode = 0
        esegui.return_value.stdout = "GPU A, 12288\nGPU B, 8192\n"

        nome, vram = hardware_modelli._nvidia()

        self.assertEqual(nome, "GPU A + GPU B")
        self.assertEqual(vram, 20.0)


if __name__ == "__main__":
    unittest.main()
