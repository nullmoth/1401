"""AMD laptops: the 0xFF000000 region stays at its address (type-14 fault at 0xFF00004C, 1401 #147), and the Intel
SSDT-PLUG tables never load on an AMD machine (AM5 hang after CoreAnalyticsHub, 1401 #21)."""
import os
import plistlib
import tempfile
import unittest

from p1401 import engine, policy


def build(cpu_name, platform, devirt=True, add=None, vendor="AMD", wl=None):
    t = tempfile.mkdtemp()
    path = os.path.join(t, "config.plist")
    cfg = {"NVRAM": {"Add": {}, "Delete": {}}, "Kernel": {"Add": [], "Patch": [], "Quirks": {}},
           "Booter": {"Quirks": {"DevirtualiseMmio": devirt, "SetupVirtualMap": True}, "MmioWhitelist": wl or []}, "Misc": {},
           "ACPI": {"Add": add or []}, "UEFI": {"Drivers": [], "Quirks": {}}, "PlatformInfo": {"Generic": {}}}
    with open(path, "wb") as f:
        plistlib.dump(cfg, f)
    res = engine.BuildResult(ok=True, out_dir=t, macos_version="24.6.0", hardware={
        "Motherboard": {"Name": "Some Board", "Chipset": "", "Platform": platform},
        "CPU": {"Manufacturer": vendor, "Processor Name": cpu_name, "Codename": ""}, "GPU": {}})
    changes = policy.apply(path, res, engine.Policy())
    with open(path, "rb") as f:
        return plistlib.load(f), [c["rule"] for c in changes]


ZEN4_LAPTOP = "AMD Ryzen 9 8945HX with Radeon Graphics"
ZEN4_DESKTOP = "AMD Ryzen 7 7800X3D 8-Core Processor"
PLUG = [{"Comment": "", "Enabled": True, "Path": "SSDT-PLUG-ALT.aml"}, {"Comment": "", "Enabled": True, "Path": "SSDT-EC.aml"}]


class AmdLaptopMmio(unittest.TestCase):
    def test_a_zen4_laptop_whitelists_0xff000000(self):
        cfg, rules = build(ZEN4_LAPTOP, "Laptop")
        self.assertEqual([(w["Address"], w["Enabled"]) for w in cfg["Booter"]["MmioWhitelist"]], [(0xFF000000, True)])
        self.assertIn("amd-laptop-mmio-ff000000", rules)

    def test_a_desktop_and_an_intel_laptop_get_no_such_entry(self):
        for name, platform, vendor in ((ZEN4_DESKTOP, "Desktop", "AMD"), ("Intel(R) Core(TM) i9-13900HX", "Laptop", "Intel")):
            cfg, rules = build(name, platform, vendor=vendor)
            self.assertEqual(cfg["Booter"]["MmioWhitelist"], [], name)
            self.assertNotIn("amd-laptop-mmio-ff000000", rules)

    def test_zen3_laptops_keep_devirtualisation_off_so_nothing_is_whitelisted(self):
        cfg, rules = build("AMD Ryzen 7 5800H with Radeon Graphics", "Laptop", devirt=False)
        self.assertFalse(cfg["Booter"]["Quirks"]["DevirtualiseMmio"])
        self.assertFalse(any(w["Enabled"] for w in cfg["Booter"]["MmioWhitelist"]))

    def test_an_existing_entry_is_switched_on_not_duplicated_and_a_second_pass_changes_nothing(self):
        cfg, _ = build(ZEN4_LAPTOP, "Laptop", wl=[{"Address": 0xFF000000, "Comment": "x", "Enabled": False}])
        self.assertEqual([(w["Address"], w["Enabled"]) for w in cfg["Booter"]["MmioWhitelist"]], [(0xFF000000, True)])


class AmdPlugOff(unittest.TestCase):
    def test_ssdt_plug_alt_is_off_on_amd_and_other_tables_stay_on(self):
        for name, platform in ((ZEN4_DESKTOP, "Desktop"), (ZEN4_LAPTOP, "Laptop")):
            cfg, rules = build(name, platform, add=[dict(e) for e in PLUG])
            self.assertEqual({e["Path"]: e["Enabled"] for e in cfg["ACPI"]["Add"]}, {"SSDT-PLUG-ALT.aml": False, "SSDT-EC.aml": True})
            self.assertIn("amd-ssdt-plug-off", rules)

    def test_intel_keeps_its_plug_table(self):
        cfg, rules = build("Intel(R) Core(TM) i7-4770K", "Desktop", add=[dict(e) for e in PLUG], vendor="Intel")
        self.assertTrue(all(e["Enabled"] for e in cfg["ACPI"]["Add"]))
        self.assertNotIn("amd-ssdt-plug-off", rules)


if __name__ == "__main__":
    unittest.main()
