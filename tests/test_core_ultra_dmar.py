"""Intel Core Ultra PCs hang at EXITBS:START with VT-d's DMAR table present; every one that booted had VT-d off. The
build drops DMAR for them (the same as switching VT-d off for macOS) and leaves every other PC's ACPI alone."""
import os
import plistlib
import tempfile
import unittest

from p1401 import engine, policy


def build(manufacturer, name, codename=""):
    t = tempfile.mkdtemp()
    path = os.path.join(t, "config.plist")
    cfg = {"NVRAM": {"Add": {}, "Delete": {}}, "Kernel": {"Add": [], "Patch": [], "Quirks": {"DisableIoMapper": True}},
           "Booter": {"Quirks": {}}, "Misc": {}, "ACPI": {"Add": [], "Delete": []},
           "UEFI": {"Drivers": [], "Quirks": {}}, "PlatformInfo": {"Generic": {}}}
    with open(path, "wb") as f:
        plistlib.dump(cfg, f)
    res = engine.BuildResult(ok=True, out_dir=t, macos_version="24.6.0", hardware={
        "Motherboard": {"Name": "Board", "Chipset": ""},
        "CPU": {"Manufacturer": manufacturer, "Processor Name": name, "Codename": codename}, "GPU": {}})
    policy.apply(path, res, engine.Policy())
    return plistlib.load(open(path, "rb"))["ACPI"]["Delete"]


def drops_dmar(dele):
    return [d for d in dele if d.get("TableSignature") == b"DMAR" and d.get("Enabled") and d.get("All")]


class CoreUltraDmar(unittest.TestCase):
    def test_arrow_lake_desktop_drops_dmar(self):
        self.assertTrue(drops_dmar(build("Intel", "Intel(R) Core(TM) Ultra 7 265KF", "Arrow Lake")))

    def test_core_ultra_laptop_without_a_codename_drops_dmar(self):
        self.assertTrue(drops_dmar(build("Intel", "Intel(R) Core(TM) Ultra 9 275HX")))

    def test_older_intel_and_amd_keep_their_acpi(self):
        self.assertEqual(build("Intel", "Intel(R) Core(TM) i7-14700K", "Raptor Lake"), [])
        self.assertEqual(build("AMD", "AMD Ryzen 7 7800X3D 8-Core Processor", "Raphael"), [])

    def test_dmar_is_dropped_once(self):
        self.assertEqual(len(drops_dmar(build("Intel", "Intel(R) Core(TM) Ultra 5 245KF", "Arrow Lake"))), 1)


if __name__ == "__main__":
    unittest.main()
