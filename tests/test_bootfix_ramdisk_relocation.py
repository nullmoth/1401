"""Install stage 2 on some AMD laptops stops with STOP 0x15 (EB.MM.AKMR) because boot.efi cannot place the 818 MB root
image at OpenCore's slide. The stick's own log asks the next build for the relocation block and slide=0; the runtime
area stop (EB.MM.AKM, STOP 0x16) keeps its own steps."""
import unittest
from types import SimpleNamespace

from p1401 import bootfix

BOOT = bootfix.BOOT_GUID
AMD = SimpleNamespace(hardware={"CPU": {"Manufacturer": "AMD"}})
INTEL = SimpleNamespace(hardware={"CPU": {"Manufacturer": "Intel"}})
STAGE2 = "AAPL: #[EB.MM.AKMR|!] Err(0xE) <- EB.MM.MKP\nOCB: StartImage failed - Aborted\nSTOP 0x15\n"
RUNTIME = "AAPL: #[EB.MM.AKM|!] Err(0xE)\nOCB: StartImage failed - Aborted\n"


def run(result, text, args="keepsyms=1"):
    cfg = {"Booter": {"Quirks": {"DevirtualiseMmio": False, "SetupVirtualMap": False, "ProvideCustomSlide": False,
                                 "AvoidRuntimeDefrag": False, "AllowRelocationBlock": False}, "MmioWhitelist": []},
           "NVRAM": {"Add": {BOOT: {"boot-args": args}}}}
    log = []
    bootfix.apply(cfg, result, [text], lambda *a: log.append(a[0]))
    return cfg, log


class RamdiskRelocation(unittest.TestCase):
    def test_a_stage_2_ramdisk_stop_asks_for_the_relocation_block_and_slide_zero(self):
        cfg, log = run(AMD, STAGE2)
        q = cfg["Booter"]["Quirks"]
        self.assertEqual(log, ["bootlog-ramdisk-relocation"])
        self.assertTrue(q["AllowRelocationBlock"] and q["ProvideCustomSlide"] and q["AvoidRuntimeDefrag"])
        self.assertEqual(cfg["NVRAM"]["Add"][BOOT]["boot-args"], "keepsyms=1 slide=0")

    def test_the_memory_map_steps_do_not_run_for_it(self):
        cfg, _ = run(AMD, STAGE2)
        q = cfg["Booter"]["Quirks"]
        self.assertFalse(q["DevirtualiseMmio"] or q["SetupVirtualMap"])

    def test_the_runtime_area_stop_is_untouched(self):
        cfg, log = run(AMD, RUNTIME)
        self.assertEqual(log, ["bootlog-amd-memory-map"])
        self.assertFalse(cfg["Booter"]["Quirks"]["AllowRelocationBlock"])
        self.assertEqual(cfg["NVRAM"]["Add"][BOOT]["boot-args"], "keepsyms=1")

    def test_akmr2_of_the_runtime_stop_is_not_the_ramdisk_stop(self):
        text = "AAPL: #[EB.BST.FBS|RT!] 0 <- EB.MM.AKMr2 0x21286000 0x0\nAAPL: #[EB.MM.AKM|!] Err(0xE) <- EB.MM.MKP\n"
        self.assertFalse(bootfix.findings([text])["ramdisk_stop"])

    def test_an_existing_slide_argument_is_replaced_not_doubled_and_a_second_run_changes_nothing(self):
        cfg, _ = run(INTEL, STAGE2, "slide=80 -v")
        self.assertEqual(cfg["NVRAM"]["Add"][BOOT]["boot-args"], "-v slide=0")
        again = []
        bootfix.apply(cfg, INTEL, [STAGE2], lambda *a: again.append(a[0]))
        self.assertEqual(cfg["NVRAM"]["Add"][BOOT]["boot-args"], "-v slide=0")


if __name__ == "__main__":
    unittest.main()
