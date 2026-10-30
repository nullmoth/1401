"""Kext pairs that do the same job, both enabled, crashed macOS with "[kalloc.type.var*.16]: element modified after free":
USBInjectAll with USBToolBox, IntelMausi with IntelSnowMausi. The builder never emits both; the checker warns on a user's
config and its fix keeps USBToolBox and IntelMausi."""
import os
import plistlib
import tempfile
import unittest

from p1401 import efi_rules, engine, policy

FACTS = {"macos": "24.6.0", "cpu_vendor": "Intel", "cpu_class": [], "chipset": "", "laptop": False,
         "amd_dgpu": False, "intel_igpu": False, "fact": []}
HW = {"CPU": {"Manufacturer": "Intel", "Processor Name": "Intel(R) Core(TM) i5-10400", "Codename": "Comet Lake"},
      "Motherboard": {"Name": "B460", "Chipset": "", "Platform": "Desktop"}}


def cfg(*on, off=()):
    return {"Kernel": {"Add": [{"BundlePath": n, "Enabled": True} for n in on] +
                              [{"BundlePath": n, "Enabled": False} for n in off]}}


def issues(c):
    return {i["id"] for i in efi_rules.check(c, FACTS, "installed")}


def build(c):
    d = tempfile.mkdtemp()
    path = os.path.join(d, "config.plist")
    base = {"ACPI": {"Add": [], "Delete": []}, "Booter": {"Quirks": {}}, "Misc": {"Boot": {}, "Debug": {}, "Security": {}},
            "NVRAM": {"Add": {policy.BOOT: {"boot-args": ""}}, "Delete": {policy.BOOT: []}}, "UEFI": {"Drivers": []},
            "PlatformInfo": {"Generic": {}}}
    base["Kernel"] = {"Add": c["Kernel"]["Add"], "Block": [], "Patch": [], "Quirks": {}}
    with open(path, "wb") as f:
        plistlib.dump(base, f)
    changes = policy.apply(path, engine.BuildResult(ok=True, out_dir=d, macos_version="24.6.0", hardware=HW), engine.Policy())
    with open(path, "rb") as f:
        built = plistlib.load(f)
    return {k["BundlePath"] for k in built["Kernel"]["Add"] if k["Enabled"]}, {c["rule"] for c in changes}


class KextConflicts(unittest.TestCase):
    def test_usbinjectall_beside_usbtoolbox_is_flagged_and_fixed_to_usbtoolbox(self):
        c = cfg("Lilu.kext", "USBToolBox.kext", "USBInjectAll.kext")
        found = efi_rules.check(c, FACTS, "installed")
        self.assertIn("kext-conflict-usb", {i["id"] for i in found})
        fixed = efi_rules.fix(c, found)
        self.assertEqual({k["BundlePath"] for k in fixed["Kernel"]["Add"] if k["Enabled"]}, {"Lilu.kext", "USBToolBox.kext"})

    def test_usbinjectall_alone_or_already_off_is_not_flagged(self):
        self.assertNotIn("kext-conflict-usb", issues(cfg("USBInjectAll.kext")))
        self.assertNotIn("kext-conflict-usb", issues(cfg("USBToolBox.kext", off=["USBInjectAll.kext"])))

    def test_both_mausi_drivers_are_flagged_and_fixed_to_intelmausi(self):
        c = cfg("IntelMausi.kext", "IntelSnowMausi.kext")
        found = efi_rules.check(c, FACTS, "installed")
        self.assertIn("kext-conflict-mausi", {i["id"] for i in found})
        fixed = efi_rules.fix(c, found)
        self.assertEqual({k["BundlePath"] for k in fixed["Kernel"]["Add"] if k["Enabled"]}, {"IntelMausi.kext"})

    def test_one_mausi_driver_is_not_flagged(self):
        self.assertNotIn("kext-conflict-mausi", issues(cfg("IntelMausi.kext")))
        self.assertNotIn("kext-conflict-mausi", issues(cfg("IntelSnowMausi.kext", off=["IntelMausi.kext"])))

    def test_the_builder_never_emits_either_pair(self):
        on, rules = build(cfg("Lilu.kext", "USBToolBox.kext", "USBInjectAll.kext", "IntelMausi.kext", "IntelSnowMausi.kext"))
        self.assertNotIn("USBInjectAll.kext", on)
        self.assertNotIn("IntelSnowMausi.kext", on)
        self.assertTrue({"USBToolBox.kext", "IntelMausi.kext"} <= on)
        self.assertTrue({"kext-conflict-usb", "kext-conflict-mausi"} <= rules)

    def test_the_builder_leaves_a_config_without_a_pair_alone(self):
        on, rules = build(cfg("Lilu.kext", "USBInjectAll.kext", "IntelSnowMausi.kext"))
        self.assertTrue({"USBInjectAll.kext", "IntelSnowMausi.kext"} <= on)
        self.assertFalse({"kext-conflict-usb", "kext-conflict-mausi"} & rules)


if __name__ == "__main__":
    unittest.main()
