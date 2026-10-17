"""Opt-in persistent NVRAM on AMD guard boards (Policy.persistent_nvram_amd). The default is still the firmware-write
guard (test_amd_nvram_write_guard); this covers the emulated-NVRAM path OpenCore's Configuration doc specifies, built
only from the sha256-checked OpenCore release. The guard is turned OFF only when the emulated store is actually in
place, because with it on OpenRuntime would reject the same macOS writes and nothing would persist."""
import io
import os
import plistlib
import tempfile
import unittest
import zipfile

from p1401 import engine, policy, validate


DRIVER_MEMBER = "X64/EFI/OC/Drivers/OpenVariableRuntimeDxe.efi"
HOOK_FILES = ("Launchd.command", "Launchd.command.plist", "nvramdump", "README.md")


def fake_release(with_driver=True, with_hook=True):
    """Bytes of a minimal zip shaped like the real OpenCore release - the driver under X64/..., the LogoutHook under
    Utilities/LogoutHook/ - so _enable_emulated_nvram reads it exactly as it reads the downloaded one."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        if with_driver:
            z.writestr(DRIVER_MEMBER, b"OVRD-driver-bytes")
        if with_hook:
            for name in HOOK_FILES:
                z.writestr("Utilities/LogoutHook/" + name, b"#!/bin/bash\n:\n")
    return buf.getvalue()


def run_policy(persistent, release=None, cpu="AMD Ryzen 9 9900X 12-Core Processor", maker="AMD", chipset="B650"):
    """Build a config in a real EFI/OC/ tree (so the ESP-relative staging lands under it), run the policy pass, and
    return (config dict, changes, efi_dir). An AM5 Zen 4/5 CPU reaches the guard branch with both memory-map quirks on."""
    top = tempfile.mkdtemp()
    oc_dir = os.path.join(top, "EFI", "OC")
    os.makedirs(oc_dir)
    config_path = os.path.join(oc_dir, "config.plist")
    cfg = {"NVRAM": {"Add": {}, "Delete": {}, "LegacySchema": {}},
           "Kernel": {"Add": [], "Patch": [], "Quirks": {}, "Block": []},
           "Booter": {"Quirks": {"DevirtualiseMmio": True, "SetupVirtualMap": True}, "MmioWhitelist": []}, "Misc": {},
           "ACPI": {"Add": []},
           "UEFI": {"Drivers": [{"Path": "OpenRuntime.efi", "Enabled": True}], "Quirks": {}},
           "PlatformInfo": {"Generic": {}}}
    with open(config_path, "wb") as f:
        plistlib.dump(cfg, f)
    res = engine.BuildResult(ok=True, out_dir=top, macos_version="24.6.0", hardware={
        "Motherboard": {"Name": "Some Board", "Chipset": chipset},
        "CPU": {"Manufacturer": maker, "Processor Name": cpu, "Codename": ""}, "GPU": {}})
    orig = validate.release_archive
    validate.release_archive = (lambda: release) if release is not None else orig
    try:
        changes = policy.apply(config_path, res, engine.Policy(persistent_nvram_amd=persistent))
    finally:
        validate.release_archive = orig
    with open(config_path, "rb") as f:
        return plistlib.load(f), changes, os.path.join(top, "EFI")


def driver_paths(cfg):
    return [d.get("Path") for d in cfg["UEFI"]["Drivers"]]


class DefaultKeepsTheGuard(unittest.TestCase):
    def test_default_build_sets_the_guard_and_adds_no_emulated_driver(self):
        cfg, _changes, efi = run_policy(persistent=False)
        self.assertIs(cfg["Booter"]["Quirks"]["DisableVariableWrite"], True)
        self.assertNotIn("OpenVariableRuntimeDxe.efi", driver_paths(cfg))
        self.assertFalse(os.path.exists(os.path.join(efi, "NullMoth")))


class OptInEnablesEmulatedNvram(unittest.TestCase):
    def setUp(self):
        self.cfg, self.changes, self.efi = run_policy(persistent=True, release=fake_release())

    def test_the_guard_is_turned_off_because_the_emulated_store_replaces_it(self):
        self.assertIs(self.cfg["Booter"]["Quirks"]["DisableVariableWrite"], False)

    def test_the_driver_is_added_loadearly_and_ordered_before_openruntime(self):
        paths = driver_paths(self.cfg)
        self.assertIn("OpenVariableRuntimeDxe.efi", paths)
        self.assertLess(paths.index("OpenVariableRuntimeDxe.efi"), paths.index("OpenRuntime.efi"))
        drivers = self.cfg["UEFI"]["Drivers"]
        self.assertIs(drivers[paths.index("OpenVariableRuntimeDxe.efi")]["LoadEarly"], True)
        self.assertIs(drivers[paths.index("OpenRuntime.efi")]["LoadEarly"], True)

    def test_the_verified_driver_bytes_are_written_to_disk(self):
        with open(os.path.join(self.efi, "OC", "Drivers", "OpenVariableRuntimeDxe.efi"), "rb") as f:
            self.assertEqual(f.read(), b"OVRD-driver-bytes")

    def test_legacyschema_has_the_three_permissive_guids(self):
        schema = self.cfg["NVRAM"]["LegacySchema"]
        for guid in policy.EMULATED_NVRAM_SCHEMA:
            self.assertEqual(schema.get(guid), ["*"])

    def test_the_logouthook_is_staged_on_the_esp_for_the_mac_app(self):
        hook = os.path.join(self.efi, "NullMoth", "LogoutHook")
        for name in HOOK_FILES:
            self.assertTrue(os.path.isfile(os.path.join(hook, name)), name)
        self.assertTrue(os.access(os.path.join(hook, "Launchd.command"), os.X_OK))


class OptInFallsBackWhenTheDriverIsMissing(unittest.TestCase):
    def test_a_release_without_the_driver_keeps_the_guard(self):
        # A TRX40 Threadripper keeps DevirtualiseMmio on but is not Zen 4/5, so the guard is not pre-set by the
        # Zen-4/5 rule and the fall-back records it here with its reason.
        cfg, changes, efi = run_policy(persistent=True, release=fake_release(with_driver=False),
                                       cpu="AMD Ryzen Threadripper PRO 5995WX", chipset="TRX40")
        self.assertIs(cfg["Booter"]["Quirks"]["DisableVariableWrite"], True)
        self.assertNotIn("OpenVariableRuntimeDxe.efi", driver_paths(cfg))
        self.assertFalse(os.path.exists(os.path.join(efi, "NullMoth")))
        guard = [c for c in changes if c["rule"] == "amd-nvram-write-guard"]
        self.assertTrue(guard and "kept the guard" in guard[0]["why"])


class IntelIsNeverTouched(unittest.TestCase):
    def test_intel_gets_no_emulated_nvram_even_opted_in(self):
        cfg, _changes, efi = run_policy(persistent=True, release=fake_release(),
                                        cpu="Intel Core i9-13900K", maker="Intel")
        self.assertNotIn("OpenVariableRuntimeDxe.efi", driver_paths(cfg))
        self.assertNotEqual(cfg["Booter"]["Quirks"].get("DisableVariableWrite"), True)
        self.assertFalse(os.path.exists(os.path.join(efi, "NullMoth")))


if __name__ == "__main__":
    unittest.main()
