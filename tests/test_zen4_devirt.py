"""Zen 4 / Zen 5 Ryzen PCs stop in boot.efi at EB.MM.AKM with DevirtualiseMmio off, and most people reboot the same
stick instead of rebuilding, so the boot-log steps never run for them. The first build turns it on for these CPUs;
AM4 and older Zen keep it off."""
import os
import plistlib
import tempfile
import unittest

from p1401 import engine, policy


def build(cpu, codename="", devirt=False, svm=True, chipset=""):
    t = tempfile.mkdtemp()
    path = os.path.join(t, "config.plist")
    cfg = {"NVRAM": {"Add": {}, "Delete": {}}, "Kernel": {"Add": [], "Patch": [], "Quirks": {}},
           "Booter": {"Quirks": {"DevirtualiseMmio": devirt, "SetupVirtualMap": svm}, "MmioWhitelist": []}, "Misc": {},
           "ACPI": {"Add": []}, "UEFI": {"Drivers": [], "Quirks": {}}, "PlatformInfo": {"Generic": {}}}
    with open(path, "wb") as f:
        plistlib.dump(cfg, f)
    res = engine.BuildResult(ok=True, out_dir=t, macos_version="24.6.0", hardware={
        "Motherboard": {"Name": "Some Board", "Chipset": chipset},
        "CPU": {"Manufacturer": "AMD", "Processor Name": cpu, "Codename": codename}, "GPU": {}})
    policy.apply(path, res, engine.Policy())
    q = plistlib.load(open(path, "rb"))["Booter"]["Quirks"]
    return q["DevirtualiseMmio"], q["SetupVirtualMap"]


class Zen4Devirt(unittest.TestCase):
    def test_am5_desktop_by_codename_gets_both_memory_quirks_on(self):
        self.assertEqual(build("AMD Ryzen 9 9950X3D 16-Core Processor", "Granite Ridge"), (True, True))

    def test_am5_desktop_without_codename_is_found_by_name(self):
        for name in ("AMD Ryzen 7 7800X3D 8-Core Processor", "AMD Ryzen 5 7600 6-Core Processor",
                     "AMD Ryzen 7 9800X3D 8-Core Processor", "AMD Ryzen 7 8700F 8-Core Processor"):
            self.assertEqual(build(name), (True, True), name)

    def test_zen4_laptops_are_found_by_name(self):
        for name in ("AMD Ryzen 9 8945H w/ Radeon 780M Graphics", "AMD Ryzen 7 7840HS w/ Radeon 780M Graphics",
                     "AMD Ryzen 7 7745HX with Radeon Graphics", "AMD Ryzen AI 9 HX 375 w/ Radeon 890M"):
            self.assertEqual(build(name)[0], True, name)

    def test_am4_and_zen3_laptops_keep_devirt_off(self):
        for name in ("AMD Ryzen 5 5600X 6-Core Processor", "AMD Ryzen 7 3700X 8-Core Processor",
                     "AMD Ryzen 7 7735HS with Radeon Graphics", "AMD Ryzen 5 5500"):
            self.assertEqual(build(name, devirt=True)[0], False, name)

    def test_a_devirt_only_config_gets_setupvirtualmap_too(self):
        self.assertEqual(build("AMD Ryzen 7 7800X3D 8-Core Processor", devirt=True, svm=False), (True, True))


if __name__ == "__main__":
    unittest.main()
