"""Boards stopped POSTing after macOS wrote NVRAM through a rewritten firmware memory map (AM5, and an AM4 5600X). Any
AMD build with SetupVirtualMap or DevirtualiseMmio on gets DisableVariableWrite, whatever the CPU's name."""
import os
import plistlib
import tempfile
import unittest

from p1401 import engine, policy


def build(cpu, devirt, svm, ort=True, maker="AMD", chipset="B550"):
    t = tempfile.mkdtemp()
    path = os.path.join(t, "config.plist")
    cfg = {"NVRAM": {"Add": {}, "Delete": {}}, "Kernel": {"Add": [], "Patch": [], "Quirks": {}},
           "Booter": {"Quirks": {"DevirtualiseMmio": devirt, "SetupVirtualMap": svm}, "MmioWhitelist": []}, "Misc": {},
           "ACPI": {"Add": []}, "UEFI": {"Drivers": [{"Path": "OpenRuntime.efi", "Enabled": True}] if ort else [], "Quirks": {}},
           "PlatformInfo": {"Generic": {}}}
    with open(path, "wb") as f:
        plistlib.dump(cfg, f)
    res = engine.BuildResult(ok=True, out_dir=t, macos_version="24.6.0", hardware={
        "Motherboard": {"Name": "Some Board", "Chipset": chipset},
        "CPU": {"Manufacturer": maker, "Processor Name": cpu, "Codename": ""}, "GPU": {}})
    policy.apply(path, res, engine.Policy())
    return plistlib.load(open(path, "rb"))["Booter"]["Quirks"]


class AmdNvramGuard(unittest.TestCase):
    def test_a_zen3_board_left_with_setupvirtualmap_on_gets_the_guard(self):
        q = build("AMD Ryzen 5 5600X 6-Core Processor", False, True, chipset="X570")
        if q.get("SetupVirtualMap") or q.get("DevirtualiseMmio"):
            self.assertTrue(q.get("DisableVariableWrite"))

    def test_am5_keeps_the_guard(self):
        self.assertTrue(build("AMD Ryzen 9 9900X 12-Core Processor", True, True).get("DisableVariableWrite"))

    def test_an_amd_build_with_both_quirks_off_is_left_alone(self):
        q = build("AMD Ryzen 5 5600X 6-Core Processor", False, False)
        self.assertFalse(q.get("SetupVirtualMap") or q.get("DevirtualiseMmio"))
        self.assertNotEqual(q.get("DisableVariableWrite"), True)

    def test_intel_is_never_touched(self):
        self.assertNotEqual(build("Intel Core i5-12400F", True, True, maker="Intel").get("DisableVariableWrite"), True)

    def test_without_openruntime_nothing_is_set(self):
        q = build("AMD Ryzen 5 5600X 6-Core Processor", False, True, ort=False, chipset="X570")
        self.assertNotEqual(q.get("DisableVariableWrite"), True)


if __name__ == "__main__":
    unittest.main()
