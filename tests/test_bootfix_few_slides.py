"""Intel boots that stop at EB.MM.AKM after OpenCore found only a few usable kernel slides take the same step as "No
slide values are usable" (2.6.5 stick logs: 1 of 256 and 6 of 256, STOP 0x16)."""
import unittest
from types import SimpleNamespace

from p1401 import bootfix

Q0 = {"DevirtualiseMmio": False, "SetupVirtualMap": False}
AKM = "AAPL: #[EB.MM.AKM|!] Err(0xE) <- EB.MM.MKP\nAAPL: #[EB|STOP] 0x16\nOCB: StartImage failed - Aborted\n"
DEVIRT = "OCABC: MMIO devirt 0xFE000000 (0x11 pages, 0x8000000000000001) skip 0\n"


def run(logs, cpu="Intel"):
    cfg = {"Booter": {"Quirks": dict(Q0)}}
    changes = []
    bootfix.apply(cfg, SimpleNamespace(hardware={"CPU": {"Manufacturer": cpu}}), logs, lambda *a: changes.append(a))
    return cfg["Booter"]["Quirks"], changes


class FewSlides(unittest.TestCase):
    def test_six_of_256_slides_then_akm_turns_devirtualise_mmio_on(self):
        q, ch = run(["OCABC: Only 6/256 slide values are usable!\n" + AKM])
        self.assertTrue(q["DevirtualiseMmio"])
        self.assertEqual(ch[0][0], "bootlog-intel-akm-devirt")
        self.assertIn("too few kernel slides", ch[0][3])

    def test_with_devirtualise_mmio_already_on_the_bios_checklist_is_said(self):
        q, ch = run(["OCABC: Only 1/256 slide values are usable!\n" + DEVIRT + AKM])
        self.assertEqual([c[0] for c in ch], ["bootlog-note"])
        self.assertIn("Above 4G Decoding", ch[0][2])

    def test_no_slide_wording_is_unchanged(self):
        _, ch = run(["OCABC: No slide values are usable! Falling back to 0 with 0x0FF00000 bytes!\n" + AKM])
        self.assertIn("found no kernel slide", ch[0][3])

    def test_negative_control_few_slides_without_a_boot_efi_stop_changes_nothing(self):
        q, ch = run(["OCABC: Only 6/256 slide values are usable!\nOCB: StartImage failed - Aborted\n"])
        self.assertEqual((q, [c[0] for c in ch if c[0].startswith("bootlog-intel-akm")]), (Q0, []))

    def test_negative_control_a_boot_with_slides_and_no_failure_changes_nothing(self):
        q, ch = run(["OCABC: Only 200/256 slide values are usable!\n"])
        self.assertEqual((q, ch), (Q0, []))


if __name__ == "__main__":
    unittest.main()
