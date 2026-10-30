"""Two stops the stick's logs and the user's stopped-at line now carry into the next build (1401 #124, #126):
boot-args OpenCore refused because the PC kept an earlier start's, and the VoodooI2C touchpad stack hanging at start."""
import unittest
from types import SimpleNamespace

from p1401 import bootfix

GUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
KEPT = f"OCVAR: Setting NVRAM {GUID}:boot-args - ignored, exists\n"
WROTE = f"OCVAR: Setting NVRAM {GUID}:boot-args - Success\n"
MACOS = ("OCB: Registering entry Macintosh HD [Apple] (T:2|F:0|G:0|E:0|B:0) - "
         "PciRoot(0x0)/Pci(0x1D,0x0)/NVMe(0x1,AA)/HD(2,GPT,X)\n")
STICK_MACOS = ("OCB: Registering entry macOS Base System [Apple] (T:2|F:0|G:0|E:0|B:0) - "
               "PciRoot(0x0)/Pci(0x14,0x0)/USB(0x3,0x0)/HD(2,GPT,X)\n")


def build(logs, cfg=None, cpu="AMD", stopped=""):
    cfg = cfg if cfg is not None else {"NVRAM": {"Add": {GUID: {"boot-args": "-v keepsyms=1"}}, "Delete": {GUID: []}}}
    changes = []
    bootfix.apply(cfg, SimpleNamespace(hardware={"CPU": {"Manufacturer": cpu}}), logs, lambda *a: changes.append(a), stopped)
    bootfix.apply_after_handoff(cfg, logs, stopped, lambda *a: changes.append(a))
    return cfg, [c[0] for c in changes]


def i2c_cfg():
    names = ["Lilu.kext", "VoodooI2C.kext", "VoodooI2C.kext/Contents/PlugIns/VoodooGPIO.kext",
             "VoodooI2C.kext/Contents/PlugIns/VoodooI2CServices.kext", "VoodooI2C.kext/Contents/PlugIns/VoodooInput.kext",
             "VoodooI2CHID.kext", "VoodooPS2Controller.kext", "VoodooPS2Controller.kext/Contents/PlugIns/VoodooInput.kext"]
    return {"Kernel": {"Add": [{"BundlePath": n, "Enabled": True} for n in names]}, "NVRAM": {"Add": {}}}


class StoredBootArgs(unittest.TestCase):
    def test_refused_boot_args_on_a_pc_without_macos_are_replaced(self):
        cfg, ch = build([KEPT])
        self.assertIn("boot-args", cfg["NVRAM"]["Delete"][GUID])
        self.assertEqual(ch, ["bootlog-own-boot-args"])

    def test_the_npci_step_reaches_the_kernel_with_it(self):
        # 124: stopped at PCI configuration with old boot-args stored: npci is added AND the stored ones are replaced
        cfg, ch = build([KEPT], stopped="[ PCI configuration begin ]")
        self.assertIn("npci=0x2000", cfg["NVRAM"]["Add"][GUID]["boot-args"].split())
        self.assertIn("boot-args", cfg["NVRAM"]["Delete"][GUID])
        self.assertEqual(ch, ["bootlog-own-boot-args", "bootlog-pci-config"])

    def test_a_pc_that_runs_macos_keeps_its_own_and_is_told_to_reset_nvram(self):
        cfg, ch = build([MACOS + KEPT])
        self.assertNotIn("boot-args", cfg["NVRAM"]["Delete"][GUID])
        self.assertEqual(ch, ["bootlog-note"])

    def test_the_stick_s_own_recovery_volume_is_not_an_installed_macos(self):
        cfg, _ = build([STICK_MACOS + KEPT])
        self.assertIn("boot-args", cfg["NVRAM"]["Delete"][GUID])

    def test_boot_args_written_normally_change_nothing(self):
        cfg, ch = build([WROTE])
        self.assertEqual((cfg["NVRAM"]["Delete"][GUID], ch), ([], []))

    def test_a_config_without_a_delete_section_gets_one(self):
        cfg, _ = build([KEPT], cfg={})
        self.assertEqual(cfg["NVRAM"]["Delete"][GUID], ["boot-args"])

    def test_already_deleted_is_not_listed_twice(self):
        cfg, ch = build([KEPT], cfg={"NVRAM": {"Delete": {GUID: ["boot-args"]}}})
        self.assertEqual((cfg["NVRAM"]["Delete"][GUID], ch), (["boot-args"], []))


class TouchpadHang(unittest.TestCase):
    def enabled(self, cfg):
        return {k["BundlePath"] for k in cfg["Kernel"]["Add"] if k["Enabled"]}

    def test_amd_gpio_hang_switches_the_whole_voodooi2c_stack_off(self):
        cfg, ch = build([], cfg=i2c_cfg(), stopped="VoodooI2CACPIController::AMD10018 Starting I2C controller\n"
                                                    "VoodooGPIOMD::Loading GPIO Data for AMD")
        self.assertEqual(self.enabled(cfg), {"Lilu.kext", "VoodooPS2Controller.kext",
                                             "VoodooPS2Controller.kext/Contents/PlugIns/VoodooInput.kext"})
        self.assertEqual(set(ch), {"bootlog-i2c-hang-off"})
        self.assertTrue(any("VoodooI2C" in r for r in bootfix.after_handoff([], "VoodooGPIOMD::Loading GPIO Data")["report"]))

    def test_an_opencore_log_that_injects_voodooi2c_changes_nothing(self):
        log = "OC: Prelinked injection VoodooI2C.kext () - Success\nOC: Prelinked injection VoodooI2C.kext v2.9.1\n"
        cfg, ch = build([log], cfg=i2c_cfg())
        self.assertEqual(len(self.enabled(cfg)), 8)
        self.assertEqual(ch, [])


if __name__ == "__main__":
    unittest.main()
