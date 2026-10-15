"""Intel PCs that stop in boot.efi at EB.MM.AKM because no kernel slide was usable: the next build turns
DevirtualiseMmio on, from the stick's own log (6 stick logs 10-15, all 12th-gen Intel with it off)."""
import unittest
from types import SimpleNamespace

from p1401 import bootfix

AKM_OFF = ("OCABC: ALRBL 1 RTDFRG 1 DEVMMIO 0 NOSU 0 NOVRWR 0 NOSB 0 FBSIG 0 NOHBMAP 0 SMSLIDE 1 WRUNPROT 0\n"
           "OCABC: No slide values are usable! Falling back to 0!\n"
           "AAPL: #[EB|BST:FBS] Err(0xE) <- EB.MM.AKMr2\n")
AKM_ON = ("OCABC: ALRBL 1 RTDFRG 1 DEVMMIO 1 NOSU 0 NOVRWR 0 NOSB 0 FBSIG 0 NOHBMAP 0 SMSLIDE 1 WRUNPROT 0\n"
          "OCABC: MMIO devirt 0xC0000000 (0x10000 pages, 0x8000000000000001) skip 0\n"
          "OCABC: No slide values are usable! Falling back to 0!\n"
          "AAPL: #[EB|BST:FBS] Err(0xE) <- EB.MM.AKMr2\n")


def run(cpu, logs, devmmio=False):
    cfg = {"Booter": {"Quirks": {"DevirtualiseMmio": devmmio, "SetupVirtualMap": True}}}
    changes = []
    bootfix.apply(cfg, SimpleNamespace(hardware={"CPU": {"Manufacturer": cpu}}), logs, lambda *a: changes.append(a))
    return cfg["Booter"]["Quirks"], [c[0] for c in changes]


class IntelAkm(unittest.TestCase):
    def test_an_intel_pc_with_no_slide_gets_devirtualise_mmio_on(self):
        q, ch = run("Intel", [AKM_OFF])
        self.assertTrue(q["DevirtualiseMmio"])
        self.assertIn("bootlog-intel-akm-devirt", ch)

    def test_it_already_ran_on_so_nothing_flips_and_the_user_is_told(self):
        q, ch = run("Intel", [AKM_ON], devmmio=True)
        self.assertTrue(q["DevirtualiseMmio"])
        self.assertNotIn("bootlog-intel-akm-devirt", ch)
        self.assertIn("bootlog-note", ch)

    def test_a_good_intel_boot_changes_nothing(self):
        q, ch = run("Intel", ["OCABC: ALRBL 1 RTDFRG 1 DEVMMIO 0 NOSU 0\nOCABC: Only 200/256 slide values are usable!\n"])
        self.assertFalse(q["DevirtualiseMmio"])
        self.assertEqual(ch, [])

    def test_an_akm_with_slides_left_is_not_this_fix(self):
        q, ch = run("Intel", ["OCABC: Only 65/256 slide values are usable!\nAAPL: Err(0xE) <- EB.MM.AKMr2\n"])
        self.assertFalse(q["DevirtualiseMmio"])
        self.assertNotIn("bootlog-intel-akm-devirt", ch)


if __name__ == "__main__":
    unittest.main()
