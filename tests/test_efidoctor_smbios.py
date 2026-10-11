"""The EFI checker names an SMBIOS model Apple's installer refuses ('This version of Mac OS X is not supported on this
platform!', stick logs 10-10: Mac-F42386C8 on macOS 15, iMacPro1,1 on macOS 26) - as a note, since 1401 also plans
older macOS for older PCs."""
import unittest

from p1401 import efidoctor


def cfg(model):
    return {"PlatformInfo": {"Generic": {"SystemProductName": model}}}


class Smbios(unittest.TestCase):
    def test_a_model_macos_15_refuses_is_named(self):
        self.assertIn("not a Mac that macOS 15 installs on", efidoctor.smbios_problems(cfg("iMac9,1"))[0])

    def test_imacpro_is_flagged_for_macos_26_only(self):
        out = efidoctor.smbios_problems(cfg("iMacPro1,1"))
        self.assertTrue(out[0].startswith("note:") and "macOS 26" in out[0])

    def test_models_both_accept_say_nothing(self):
        for m in ("MacPro7,1", "iMac20,1", "MacBookPro16,2"):
            self.assertEqual(efidoctor.smbios_problems(cfg(m)), [])


if __name__ == "__main__":
    unittest.main()
