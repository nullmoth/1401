"""OpenCore stops at start with "Configuration requires vault but no vault provided" when the config asks for a vault
the EFI does not carry (1401 #153). 1401 ships no vault files, so the policy pass sets Optional."""
import os
import plistlib
import tempfile
import unittest

from p1401 import engine, policy


def build(vault):
    t = tempfile.mkdtemp()
    path = os.path.join(t, "config.plist")
    sec = {} if vault is None else {"Vault": vault}
    cfg = {"NVRAM": {"Add": {}, "Delete": {}}, "Kernel": {"Add": [], "Patch": [], "Quirks": {}},
           "Booter": {"Quirks": {}, "MmioWhitelist": []}, "Misc": {"Security": sec}, "ACPI": {"Add": []},
           "UEFI": {"Drivers": [], "Quirks": {}}, "PlatformInfo": {"Generic": {}}}
    with open(path, "wb") as f:
        plistlib.dump(cfg, f)
    res = engine.BuildResult(ok=True, out_dir=t, macos_version="24.6.0", hardware={
        "Motherboard": {"Name": "B", "Chipset": ""}, "CPU": {"Manufacturer": "Intel", "Processor Name": "i5", "Codename": ""}, "GPU": {}})
    changes = policy.apply(path, res, engine.Policy())
    with open(path, "rb") as f:
        return plistlib.load(f)["Misc"]["Security"].get("Vault"), [c["rule"] for c in changes]


class VaultOptional(unittest.TestCase):
    def test_a_config_that_asks_for_a_vault_is_set_to_optional(self):
        for mode in ("Basic", "Secure"):
            vault, rules = build(mode)
            self.assertEqual(vault, "Optional", mode)
            self.assertIn("vault-optional", rules)

    def test_optional_or_unset_is_left_alone(self):
        self.assertEqual(build("Optional"), ("Optional", build("Optional")[1]))
        self.assertNotIn("vault-optional", build("Optional")[1])
        vault, rules = build(None)
        self.assertEqual(vault, None)
        self.assertNotIn("vault-optional", rules)


if __name__ == "__main__":
    unittest.main()
