"""efidoctor on a hand-built EFI: finds and fixes what 1401's own builds get right. Fixture files only."""
import json, os, plistlib, tempfile, unittest

from p1401 import efidoctor, nullmoth

PATH = "PciRoot(0x0)/Pci(0x1,0x0)/Pci(0x0,0x0)"


def kext(name):
    return {"BundlePath": name, "Enabled": True, "ExecutablePath": "Contents/MacOS/" + name.split(".")[0], "PlistPath": "Contents/Info.plist"}


def make(root, kexts, args="-v"):
    oc = os.path.join(root, "EFI", "OC")
    for k in kexts:
        d = os.path.join(oc, "Kexts", k, "Contents", "MacOS"); os.makedirs(d)
        open(os.path.join(d, k.split(".")[0]), "wb").write(b"x"); open(os.path.join(oc, "Kexts", k, "Contents", "Info.plist"), "wb").write(b"x")
    os.makedirs(os.path.join(root, "EFI", "BOOT")); open(os.path.join(root, "EFI", "BOOT", "BOOTx64.efi"), "wb").write(b"x")
    cfg = {"ACPI": {"Add": []}, "Booter": {"Quirks": {"DevirtualiseMmio": False, "SetupVirtualMap": False}, "MmioWhitelist": []},
           "DeviceProperties": {"Add": {}}, "Kernel": {"Add": [kext(k) for k in kexts]},
           "Misc": {"Tools": []}, "NVRAM": {"Add": {"7C436110-AB2A-4BBB-A880-FE41995C9F82": {"boot-args": args}}},
           "PlatformInfo": {"Generic": {"SystemProductName": "iMacPro1,1", "SystemSerialNumber": "X", "MLB": "Y", "SystemUUID": "Z", "ROM": b"1"}},
           "UEFI": {"Drivers": [], "Quirks": {}}}
    with open(os.path.join(oc, "config.plist"), "wb") as fh: plistlib.dump(cfg, fh)
    return os.path.join(oc, "config.plist")


def report(root, platform="Laptop", cpu="AMD"):
    p = os.path.join(root, "Report.json")
    json.dump({"Motherboard": {"Platform": platform}, "CPU": {"Manufacturer": cpu},
               "GPU": {"RTX 4060 Laptop": {"Manufacturer": "NVIDIA", "Device Type": "Discrete GPU", "Device ID": "10DE-28E0", "PCI Path": PATH}}}, open(p, "w"))
    return p


class Doctor(unittest.TestCase):
    def test_hand_built_laptop_efi_is_diagnosed_then_fixed(self):
        with tempfile.TemporaryDirectory() as t:
            cfgp = make(t, ["WhateverGreen.kext", "Lilu.kext"])
            log = os.path.join(t, "opencore-1.txt"); open(log, "w").write("AAPL: #[EB.MM.AKM|!] Err(0xE)\n")
            before = open(cfgp, "rb").read()
            dry = efidoctor.check(t, report(t), [log], fix=False)
            self.assertFalse(dry["ok"])
            self.assertEqual(open(cfgp, "rb").read(), before, "a check without --fix must not write")
            rules = " ".join(dry["would_fix"])
            for want in ("kext-order", "nullmoth-boot-args", "nullmoth-sip", "nullmoth-laptop-gpu-awake", "bootlog-amd-memory-map"):
                self.assertIn(want, rules)
            done = efidoctor.check(t, report(t), [log], fix=True)
            self.assertTrue(done["ok"], done)
            cfg = plistlib.load(open(cfgp, "rb"))
            self.assertEqual([k["BundlePath"] for k in cfg["Kernel"]["Add"]], ["Lilu.kext", "WhateverGreen.kext"])
            self.assertEqual(cfg["DeviceProperties"]["Add"][PATH]["acpi-wake-type"], 1)
            self.assertIn("nvaccel=1", cfg["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"])
            self.assertTrue(os.path.exists(done["written"]["backup"]))
            again = efidoctor.check(t, report(t), [], fix=False)
            self.assertTrue(again["ok"], again)

    def test_control_a_correct_desktop_efi_without_nvidia_has_nothing_to_fix(self):
        with tempfile.TemporaryDirectory() as t:
            make(t, ["Lilu.kext", "WhateverGreen.kext"])
            out = efidoctor.check(t, None, [], fix=False)
            self.assertTrue(out["ok"], out)
            self.assertEqual(out["would_fix"], [])

    def test_a_missing_kext_file_is_a_problem_not_a_silent_pass(self):
        with tempfile.TemporaryDirectory() as t:
            cfgp = make(t, ["Lilu.kext"])
            cfg = plistlib.load(open(cfgp, "rb")); cfg["Kernel"]["Add"].append(kext("Ghost.kext"))
            plistlib.dump(cfg, open(cfgp, "wb"))
            out = efidoctor.check(t, None, [], fix=True)
            self.assertFalse(out["ok"])
            self.assertTrue(any("Ghost.kext" in p for p in out["problems"]))


if __name__ == "__main__":
    unittest.main()
