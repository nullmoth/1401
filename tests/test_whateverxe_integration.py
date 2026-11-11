"""WhateverXe in the Windows EFI builder: the pin the Mac app uses, and the config requirements upstream documents.

The Mac app has pinned WhateverXe 0.8.0 and its AMFIPass Mod for a while; the Windows builder asks OpCore Simplify for
the latest release. These tests keep the two on the same bytes and keep policy from producing an EFI that names
WhateverXe but leaves SIP at 0x03 (the Windows build's old value) or keeps WhateverGreen enabled beside it. No network.
"""
import os
import pathlib
import plistlib
import re
import tempfile
import unittest
import zipfile

from p1401 import engine, policy, whateverxe

ROOT = pathlib.Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "out" / "release-cache" / "fixtures" / "OpenCore-1.0.8-RELEASE.zip"
SETUP = ROOT / "mac" / "Resources" / "nullmoth-setup.sh"


def kext(bundle, enabled=True):
    return {"Arch": "Any", "BundlePath": bundle, "Comment": "", "Enabled": enabled,
            "ExecutablePath": "Contents/MacOS/" + bundle[:-5], "MaxKernel": "", "MinKernel": "",
            "PlistPath": "Contents/Info.plist"}


class MacAppPin(unittest.TestCase):
    """The Windows builder must install the same release the Mac app pins, or the kext and graphics stack can differ."""

    def test_whateverxe_release_is_the_setup_scripts_pin(self):
        text = SETUP.read_text(encoding="utf-8")
        m = re.search(r"WhateverXe\.kext\) echo \"(\S+) ([0-9a-f]{64})\"", text)
        self.assertIsNotNone(m, "nullmoth-setup.sh no longer pins WhateverXe in the expected form")
        self.assertEqual(m.group(1), whateverxe.RELEASE_URL)
        self.assertEqual(m.group(2), whateverxe.RELEASE_SHA256)

    def test_amfipass_mod_is_pinned_to_a_commit_and_the_same_hash(self):
        text = SETUP.read_text(encoding="utf-8")
        xg = re.search(r"\bXG=([0-9a-f]{40})", text)
        url = re.search(r"^\s*XAMFI_URL=(\S+)$", text, re.M)
        sha = re.search(r"^\s*XAMFI_SHA=([0-9a-f]{64})$", text, re.M)
        self.assertIsNotNone(xg, "the setup script no longer pins the WhateverXe-Graphics commit")
        self.assertIsNotNone(url, "the setup script no longer pins AMFIPass Mod")
        self.assertIsNotNone(sha, "the setup script no longer pins AMFIPass Mod's SHA-256")
        self.assertEqual(url.group(1).replace("$XG", xg.group(1)), whateverxe.AMFIPASS_MOD_URL)
        self.assertEqual(sha.group(1), whateverxe.AMFIPASS_MOD_SHA256)
        self.assertIn("/" + xg.group(1) + "/", whateverxe.AMFIPASS_MOD_URL,
                      "the Mod URL must be commit-pinned, not refs/heads/main")

    def test_graphics_package_is_the_setup_scripts_pin(self):
        text = SETUP.read_text(encoding="utf-8")
        url = re.search(r"^\s*XPKG_URL=(\S+)$", text, re.M)
        sha = re.search(r"^\s*XPKG_SHA=([0-9a-f]{64})$", text, re.M)
        self.assertIsNotNone(url, "the setup script no longer pins WhateverXe Graphics")
        self.assertIsNotNone(sha, "the setup script no longer pins WhateverXe Graphics' SHA-256")
        self.assertEqual(url.group(1), whateverxe.GRAPHICS_URL)
        self.assertEqual(sha.group(1), whateverxe.GRAPHICS_SHA256)

    def test_upstream_requirements_are_recorded(self):
        self.assertEqual(whateverxe.SIP, 0x803)
        self.assertEqual(whateverxe.BOOT_ARGS, ("-allow3d", "-disablegfxfirmware"))
        self.assertEqual(whateverxe.VERSION, "0.8.0")


class EngineUsesThePin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine._load_engine()

    def test_opcore_downloads_the_pinned_whateverxe(self):
        from Scripts.datasets import kext_data
        idx = kext_data.kext_index_by_name["WhateverXe"]
        info = kext_data.kexts[idx].download_info
        self.assertEqual(info.get("url"), whateverxe.RELEASE_URL)
        self.assertEqual(info.get("sha256"), whateverxe.RELEASE_SHA256)

    def test_opcore_downloads_the_pinned_amfipass_mod(self):
        from Scripts.datasets import kext_data
        info = kext_data.AMFIPassModDownloadInfo
        self.assertEqual(info.get("url"), whateverxe.AMFIPASS_MOD_URL)
        self.assertEqual(info.get("sha256"), whateverxe.AMFIPASS_MOD_SHA256)


@unittest.skipUnless(SAMPLE.is_file(), "OpenCore 1.0.8 sample archive is not in the test cache")
class Policy(unittest.TestCase):
    def apply(self, bundles, csr=b"\x03\x00\x00\x00", args="-v", decisions=(), macos="25.99.99"):
        with zipfile.ZipFile(SAMPLE) as z:
            cfg = plistlib.loads(z.read("Docs/Sample.plist"))
        cfg["NVRAM"]["Add"][policy.BOOT]["boot-args"] = args
        cfg["NVRAM"]["Add"][policy.BOOT]["csr-active-config"] = csr
        cfg["Kernel"]["Add"] = [kext(b) for b in bundles]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.plist")
            with open(path, "wb") as fh:
                plistlib.dump(cfg, fh)
            result = engine.BuildResult(
                ok=True, out_dir=tmp, macos_version=macos,
                hardware={"GPU": {"Intel(R) Iris(R) Xe Graphics": {
                    "Manufacturer": "Intel", "Device ID": "8086-A7A0", "Device Type": "Integrated GPU"}}},
                decisions=list(decisions))
            changes = policy.apply(path, result, engine.Policy())
            with open(path, "rb") as fh:
                return plistlib.load(fh), changes

    @staticmethod
    def value(cfg, key):
        return cfg["NVRAM"]["Add"][policy.BOOT].get(key)

    def test_whateverxe_gets_sip_803_and_its_boot_arguments(self):
        cfg, changes = self.apply(["Lilu.kext", "WhateverXe.kext"])
        csr = int.from_bytes(self.value(cfg, "csr-active-config"), "little")
        self.assertEqual(csr, 0x803)
        args = self.value(cfg, "boot-args").split()
        self.assertIn("-allow3d", args)
        self.assertIn("-disablegfxfirmware", args)
        self.assertTrue(any(c["rule"] in ("whateverxe-sip", "sip-minimal")
                            and "0x803" in (c.get("why") or "") for c in changes), changes)
        self.assertTrue(any(c["rule"] == "whateverxe-args" for c in changes), changes)

    def test_whateverxe_turns_whatevergreen_off(self):
        cfg, changes = self.apply(["Lilu.kext", "WhateverXe.kext", "WhateverGreen.kext"],
                                  args="-v -igfxvesa")
        weg = next(k for k in cfg["Kernel"]["Add"] if k["BundlePath"] == "WhateverGreen.kext")
        self.assertFalse(weg["Enabled"])
        self.assertTrue(any(c["rule"] == "whateverxe-weg" for c in changes), changes)

    def test_whateverxe_keeps_bits_another_feature_needs(self):
        cfg, _ = self.apply(["Lilu.kext", "WhateverXe.kext"], csr=(0x0A43).to_bytes(4, "little"))
        self.assertEqual(int.from_bytes(self.value(cfg, "csr-active-config"), "little"), 0x0A43)

    def test_voodoo_hda_still_lowers_sip_when_the_kext_is_really_there(self):
        cfg, _ = self.apply(["Lilu.kext", "VoodooHDA.kext"], decisions=[
            engine.Decision("Select audio kext for your system:", "2", "")])
        self.assertEqual(int.from_bytes(self.value(cfg, "csr-active-config"), "little"), 0x03)

    def test_the_audio_menu_alone_does_not_lower_sip(self):
        # The old rule keyed off "Select audio kext" and the default VoodooHDA answer, so every Tahoe build got 0x03
        # although the menu's option 2 is AppleALC + SimpleHDA and no VoodooHDA was in the EFI.
        cfg, changes = self.apply(["Lilu.kext"], decisions=[
            engine.Decision("Select audio kext for your system:", "2", "")])
        self.assertEqual(int.from_bytes(self.value(cfg, "csr-active-config"), "little"), 0x00000000)
        self.assertFalse(any(c["rule"] == "sip-minimal" and c.get("after") == "03000000" for c in changes), changes)

    def test_tahoe_whateverxe_will_not_load_before_26_7(self):
        cfg, _ = self.apply(["Lilu.kext", "WhateverXe.kext"], macos="25.0.0")
        wex = next(k for k in cfg["Kernel"]["Add"] if k["BundlePath"] == "WhateverXe.kext")
        self.assertEqual(wex["MinKernel"], "25.7.0")

    def test_sequoia_whateverxe_keeps_the_engine_min_kernel(self):
        cfg, _ = self.apply(["Lilu.kext", "WhateverXe.kext"], macos="24.99.99")
        wex = next(k for k in cfg["Kernel"]["Add"] if k["BundlePath"] == "WhateverXe.kext")
        self.assertNotEqual(wex["MinKernel"], "25.7.0")

    def test_no_whateverxe_gets_no_whateverxe_arguments(self):
        cfg, changes = self.apply(["Lilu.kext"])
        self.assertNotIn("-allow3d", self.value(cfg, "boot-args").split())
        self.assertFalse(any(c["rule"].startswith("whateverxe-") for c in changes), changes)


if __name__ == "__main__":
    unittest.main()
