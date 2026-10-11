"""When Windows application control (Smart App Control / WDAC, error 4551) refuses to run ocvalidate, the build checks the
config against OpenCore's own sample instead of stopping (8 PCs could not build at all on 1.2-1.9). Both directions:
a good config passes and says it used the fallback; a wrong type or unknown key fails; any other validator failure
still stops the build."""
import os
import plistlib
import tempfile
import unittest
from unittest import mock

from p1401 import validate

SAMPLE = {"Booter": {"Quirks": {"AvoidRuntimeDefrag": True}}, "Kernel": {"Add": [{"BundlePath": "Lilu.kext", "Enabled": True}],
          "Quirks": {"DisableIoMapper": False}}, "NVRAM": {"Add": {"7C436110-AB2A-4BBB-A880-FE41995C9F82": {"boot-args": ""}}}}
BLOCKED = validate.ValidatorUnavailable("Windows application control blocked the verified OpenCore validator (4551). ...")


def efi(cfg):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "EFI", "OC"))
    with open(os.path.join(d, "EFI", "OC", "config.plist"), "wb") as fh:
        plistlib.dump(cfg, fh)
    return d


class Fallback(unittest.TestCase):
    def run_validate(self, cfg, error=BLOCKED):
        with mock.patch.object(validate, "run_ocvalidate", side_effect=error), \
             mock.patch.object(validate, "release_samples", return_value=[SAMPLE]), \
             mock.patch.object(validate, "invariants", return_value=[]), \
             mock.patch.object(validate, "release_components", return_value=[]):
            return validate.validate(efi(cfg))

    def test_a_good_config_passes_on_the_samples_and_says_so(self):
        good = {"Booter": {"Quirks": {"AvoidRuntimeDefrag": True}}, "Kernel": {"Add": [{"BundlePath": "X.kext"}]},
                "NVRAM": {"Add": {"4D1EDE05-38C7-4A6A-9CC6-4BCCA8B38C14": {"anything": b"\x01"}}}}
        out = self.run_validate(good)
        self.assertTrue(out["ok"], out)
        self.assertIn("4551", out["ocvalidate"]["fallback"])

    def test_a_wrong_type_or_unknown_key_fails(self):
        bad = {"Booter": {"Quirks": {"AvoidRuntimeDefrag": "yes"}}, "Kernel": {"Quirks": {"NoSuchQuirk": True}}}
        out = self.run_validate(bad)
        self.assertFalse(out["ok"])
        self.assertEqual(sorted(out["invariants"]), ["Booter.Quirks.AvoidRuntimeDefrag: is str, OpenCore reads bool",
                                                     "Kernel.Quirks.NoSuchQuirk: not a key OpenCore knows"])

    def test_any_other_validator_failure_still_stops(self):
        out = self.run_validate(SAMPLE, validate.ValidatorUnavailable("OpenCore validator bytes differ from the verified release"))
        self.assertFalse(out["ok"])
        self.assertIn("bytes differ", out["error"])


if __name__ == "__main__":
    unittest.main()
