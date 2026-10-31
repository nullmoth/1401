"""A UEFI driver the config loads but the EFI lacks is reported with what EFI/OC/Drivers does hold (2.6.5 build logs:
"UEFI driver missing on disk: HfsPlus.efi" alone could not tell a skipped binary-data download from one removed file)."""
import os
import plistlib
import tempfile
import unittest

from p1401 import validate


def efi(tmp, present):
    oc = os.path.join(tmp, "EFI", "OC")
    os.makedirs(os.path.join(oc, "Drivers"))
    for n in present:
        open(os.path.join(oc, "Drivers", n), "wb").close()
    cfg = {"Kernel": {"Add": []}, "ACPI": {"Add": []}, "Misc": {"Tools": []},
           "UEFI": {"Drivers": [{"Path": "HfsPlus.efi", "Enabled": True}, {"Path": "OpenRuntime.efi", "Enabled": True}]},
           "PlatformInfo": {"Generic": {}}}
    with open(os.path.join(oc, "config.plist"), "wb") as fh:
        plistlib.dump(cfg, fh)
    return tmp


class MissingDriverListing(unittest.TestCase):
    def test_a_missing_driver_names_what_the_folder_holds(self):
        with tempfile.TemporaryDirectory() as t:
            fails = validate.invariants(efi(t, ["OpenRuntime.efi", "ResetNvramEntry.efi"]))
        line = next(f for f in fails if "HfsPlus.efi" in f)
        self.assertIn("EFI/OC/Drivers holds: OpenRuntime.efi, ResetNvramEntry.efi", line)

    def test_an_empty_folder_says_nothing(self):
        with tempfile.TemporaryDirectory() as t:
            fails = validate.invariants(efi(t, []))
        self.assertTrue(any("holds: nothing" in f for f in fails), fails)

    def test_negative_control_drivers_present_report_no_driver_line(self):
        with tempfile.TemporaryDirectory() as t:
            fails = validate.invariants(efi(t, ["HfsPlus.efi", "OpenRuntime.efi"]))
        self.assertFalse(any("UEFI driver missing" in f for f in fails), fails)


if __name__ == "__main__":
    unittest.main()
