"""Kexts excluded by dependency licence restrictions (NootedRed, NootRX, SMCRadeonSensors, ForgedInvariant) never reach a
1401 EFI: the policy pass removes their config entries and their files, and leaves every other kext alone."""
import os
import plistlib
import tempfile
import unittest

from p1401 import engine, policy


def build(paths):
    t = tempfile.mkdtemp()
    path = os.path.join(t, "config.plist")
    os.makedirs(os.path.join(t, "Kexts"))
    for p in paths:
        os.makedirs(os.path.join(t, "Kexts", p.split("/")[0], "Contents"), exist_ok=True)
    cfg = {"NVRAM": {"Add": {}, "Delete": {}},
           "Kernel": {"Add": [{"BundlePath": p, "Enabled": True} for p in paths], "Patch": [], "Quirks": {}},
           "Booter": {"Quirks": {}, "MmioWhitelist": []}, "Misc": {}, "ACPI": {"Add": []},
           "UEFI": {"Drivers": [], "Quirks": {}}, "PlatformInfo": {"Generic": {}}}
    with open(path, "wb") as f:
        plistlib.dump(cfg, f)
    res = engine.BuildResult(ok=True, out_dir=t, macos_version="24.6.0", hardware={
        "Motherboard": {"Name": "Laptop", "Chipset": ""},
        "CPU": {"Manufacturer": "AMD", "Processor Name": "AMD Ryzen 7 5800H", "Codename": "Cezanne"}, "GPU": {}})
    changes = policy.apply(path, res, engine.Policy())
    kept = [k["BundlePath"] for k in plistlib.load(open(path, "rb"))["Kernel"]["Add"]]
    return kept, sorted(os.listdir(os.path.join(t, "Kexts"))), changes


class ExcludedKexts(unittest.TestCase):
    def test_every_excluded_kext_leaves_the_config_and_the_disk(self):
        kept, files, changes = build(["Lilu.kext", "NootedRed.kext", "NootRX.kext", "SMCRadeonSensors.kext",
                                      "ForgedInvariant.kext", "VirtualSMC.kext"])
        for name in policy.EXCLUDED_KEXTS:
            self.assertNotIn(name, kept)
            self.assertNotIn(name, files)
        self.assertIn("excluded-kexts", [c["rule"] for c in changes])

    def test_other_kexts_are_untouched(self):
        kept, files, changes = build(["Lilu.kext", "WhateverGreen.kext", "AppleALC.kext"])
        self.assertEqual(kept[:3], ["Lilu.kext", "WhateverGreen.kext", "AppleALC.kext"])
        self.assertEqual(files, ["AppleALC.kext", "Lilu.kext", "WhateverGreen.kext"])
        self.assertNotIn("excluded-kexts", [c["rule"] for c in changes])

    def test_a_plugin_path_inside_an_excluded_kext_goes_too(self):
        kept, _, _ = build(["Lilu.kext", "NootedRed.kext/Contents/PlugIns/Example.kext"])
        self.assertEqual(kept[0], "Lilu.kext")
        self.assertFalse([k for k in kept if k.startswith("NootedRed.kext")])


if __name__ == "__main__":
    unittest.main()
