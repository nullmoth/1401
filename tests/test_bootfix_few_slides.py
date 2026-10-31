"""Intel boots that stop at EB.MM.AKM after OpenCore found only a few usable kernel slides (2.6.5 stick logs: 1 of 256
and 6 of 256, STOP 0x16) are told the BIOS checklist. No quirk changes: which slide count makes DevirtualiseMmio the fix
is not measured, and "No slide values are usable" keeps its own step."""
import unittest
from types import SimpleNamespace

from p1401 import bootfix

Q0 = {"DevirtualiseMmio": False, "SetupVirtualMap": False}
AKM = "AAPL: #[EB.MM.AKM|!] Err(0xE) <- EB.MM.MKP\nAAPL: #[EB|STOP] 0x16\nOCB: StartImage failed - Aborted\n"


def run(logs, cpu="Intel"):
    cfg = {"Booter": {"Quirks": dict(Q0)}}
    changes = []
    bootfix.apply(cfg, SimpleNamespace(hardware={"CPU": {"Manufacturer": cpu}}), logs, lambda *a: changes.append(a))
    return cfg["Booter"]["Quirks"], changes


class FewSlides(unittest.TestCase):
    def test_six_of_256_slides_then_akm_gives_the_bios_checklist_and_no_quirk_change(self):
        q, ch = run(["OCABC: Only 6/256 slide values are usable!\n" + AKM])
        self.assertEqual(q, Q0)
        self.assertEqual([c[0] for c in ch], ["bootlog-note"])
        self.assertIn("Above 4G Decoding", ch[0][2])

    def test_no_slide_keeps_its_own_step(self):
        q, ch = run(["OCABC: No slide values are usable! Falling back to 0 with 0x0FF00000 bytes!\n" + AKM])
        self.assertTrue(q["DevirtualiseMmio"])
        self.assertEqual([c[0] for c in ch], ["bootlog-intel-akm-devirt"])

    def test_negative_control_few_slides_without_a_boot_efi_stop_says_nothing(self):
        q, ch = run(["OCABC: Only 6/256 slide values are usable!\nOCB: StartImage failed - Aborted\n"])
        self.assertEqual((q, ch), (Q0, []))

    def test_negative_control_amd_is_left_to_its_own_steps(self):
        _, ch = run(["OCABC: Only 6/256 slide values are usable!\n" + AKM], cpu="AMD")
        self.assertNotIn("few kernel slides usable", " ".join(str(c) for c in ch))


if __name__ == "__main__":
    unittest.main()
