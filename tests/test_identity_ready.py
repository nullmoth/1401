"""Apple's services refuse or mis-count a Mac whose identity is a placeholder, a sample value or malformed. The check
names each case, and a fresh build never writes a ROM with the multicast bit set (the upstream builder draws six
random bytes, so half of all builds did)."""
import os
import plistlib
import tempfile
import types
import unittest

from p1401 import engine, identity_ready as ir

GOOD = {"SystemSerialNumber": "C02ABCDEF8J1", "MLB": "C02123456789ABCDE", "SystemUUID": "6F1E0C5A-3A0B-4F6B-9C41-0D5B1C2E7A11",
        "ROM": bytes.fromhex("A4C3F0112233"), "SystemProductName": "MacPro7,1"}


def cfg(**over):
    g = dict(GOOD)
    g.update(over)
    return {"PlatformInfo": {"Automatic": True, "UpdateDataHub": True, "UpdateNVRAM": True, "UpdateSMBIOS": True, "Generic": g},
            "DeviceProperties": {"Add": {"PciRoot(0x0)/Pci(0x1C,0x2)/Pci(0x0,0x0)": {"built-in": b"\x01"}}},
            "Booter": {"Quirks": {}}, "NVRAM": {}}


def codes(c, eth=True):
    return [code for _l, code, _t in ir.check(c, eth)]


class Check(unittest.TestCase):
    def test_a_complete_identity_has_no_findings(self):
        self.assertEqual(ir.check(cfg(), True), [])

    def test_the_placeholder_the_builder_writes_when_serial_generation_fails_is_a_problem(self):
        self.assertIn("serial-placeholder", codes(cfg(SystemSerialNumber="A" + "0" * 10 + "9")))
        self.assertIn("mlb-placeholder", codes(cfg(MLB="A" + "0" * 15 + "Z")))

    def test_opencores_sample_values_are_problems(self):
        self.assertIn("serial-placeholder", codes(cfg(SystemSerialNumber="W00000000001")))
        self.assertIn("rom-placeholder", codes(cfg(ROM=bytes.fromhex("112233445566"))))
        self.assertIn("uuid-zero", codes(cfg(SystemUUID="00000000-0000-0000-0000-000000000000")))

    def test_malformed_values_are_problems(self):
        self.assertIn("serial-shape", codes(cfg(SystemSerialNumber="c02abc")))
        self.assertIn("mlb-shape", codes(cfg(MLB="SHORT")))
        self.assertIn("uuid-shape", codes(cfg(SystemUUID="not-a-uuid")))
        self.assertIn("rom-shape", codes(cfg(ROM=b"\x01\x02")))

    def test_a_multicast_rom_is_a_problem_and_a_unicast_one_is_not(self):
        self.assertIn("rom-multicast", codes(cfg(ROM=bytes.fromhex("A5C3F0112233"))))
        self.assertNotIn("rom-multicast", codes(cfg()))

    def test_turned_off_updates_hide_the_identity_from_macos(self):
        c = cfg()
        c["PlatformInfo"]["UpdateDataHub"] = False
        self.assertIn("update-updatedatahub", codes(c))

    def test_blocked_nvram_without_emulation_forgets_the_sign_in_and_emulation_fixes_it(self):
        c = cfg()
        c["Booter"]["Quirks"]["DisableVariableWrite"] = True
        self.assertIn("nvram-readonly", codes(c))
        c["NVRAM"]["LegacyEnable"] = True
        self.assertNotIn("nvram-readonly", codes(c))

    def test_ethernet_cases(self):
        self.assertIn("no-pci-ethernet", codes(cfg(), eth=False))
        unmarked = cfg()
        unmarked["DeviceProperties"] = {"Add": {}}
        self.assertIn("ethernet-not-built-in", codes(unmarked, eth=True))
        self.assertEqual([c for c in codes(unmarked, eth=None) if c.startswith("ethernet") or c.startswith("no-pci")], [])


class Rom(unittest.TestCase):
    def test_rom_from_a_network_address(self):
        self.assertEqual(ir.rom_from_mac("a4:c3:f0:11:22:33"), bytes.fromhex("A4C3F0112233"))
        self.assertEqual(ir.rom_from_mac("A4-C3-F0-11-22-33"), bytes.fromhex("A4C3F0112233"))

    def test_text_that_is_not_a_unicast_address_gives_nothing(self):
        for bad in ("", "zz:zz", "a5:c3:f0:11:22:33", "00:00:00:00:00:00", "112233445566", "a4:c3:f0:11:22"):
            self.assertIsNone(ir.rom_from_mac(bad), bad)

    def test_clearing_the_multicast_bit_changes_only_that_bit(self):
        self.assertEqual(ir.unicast_rom(bytes.fromhex("A5C3F0112233")), bytes.fromhex("A4C3F0112233"))


class RomPass(unittest.TestCase):
    def run_pass(self, rom, prior=None, rom_mac=""):
        out = tempfile.mkdtemp()
        os.makedirs(os.path.join(out, "EFI", "OC"))
        path = os.path.join(out, "EFI", "OC", "config.plist")
        with open(path, "wb") as f:
            plistlib.dump({"PlatformInfo": {"Generic": {"ROM": rom}}}, f)
        h = types.SimpleNamespace(policy=engine.Policy(), notices=[])
        h.policy.rom_mac = rom_mac
        engine._identity_rom_pass(out, prior, h)
        with open(path, "rb") as f:
            return plistlib.load(f)["PlatformInfo"]["Generic"]["ROM"], h.notices

    def test_a_fresh_multicast_rom_is_made_unicast(self):
        rom, _ = self.run_pass(bytes.fromhex("A5C3F0112233"))
        self.assertEqual(rom, bytes.fromhex("A4C3F0112233"))

    def test_a_kept_identity_is_never_touched(self):
        multicast = bytes.fromhex("A5C3F0112233")
        rom, _ = self.run_pass(multicast, prior={"ROM": multicast})
        self.assertEqual(rom, multicast)

    def test_the_adapter_address_switch_writes_the_ROM_and_a_bad_address_keeps_the_old_one(self):
        rom, notes = self.run_pass(bytes.fromhex("A4C3F0112233"), rom_mac="70:85:C2:AA:BB:CC")
        self.assertEqual(rom, bytes.fromhex("7085C2AABBCC"))
        keep, notes = self.run_pass(bytes.fromhex("A4C3F0112233"), rom_mac="nonsense")
        self.assertEqual(keep, bytes.fromhex("A4C3F0112233"))
        self.assertTrue(any("not a valid" in n for n in notes))



class Doctor(unittest.TestCase):
    """The EFI checker reports the identity of an EFI 1401 did not build, and corrects a multicast ROM only with --fix."""

    def efi(self, rom):
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "EFI", "OC"))
        c = cfg(ROM=rom)
        with open(os.path.join(root, "EFI", "OC", "config.plist"), "wb") as f:
            plistlib.dump(c, f)
        return root

    def test_a_multicast_rom_is_named_and_fixed_only_when_asked(self):
        from p1401 import efidoctor
        root = self.efi(bytes.fromhex("A5C3F0112233"))
        out = efidoctor.check(root)
        self.assertTrue(any("multicast" in n for n in out["notes"]))
        self.assertTrue(any(f.startswith("rom-unicast") for f in out["would_fix"]))
        with open(os.path.join(root, "EFI", "OC", "config.plist"), "rb") as f:
            self.assertEqual(plistlib.load(f)["PlatformInfo"]["Generic"]["ROM"], bytes.fromhex("A5C3F0112233"))
        out = efidoctor.check(root, fix=True)
        self.assertTrue(out["written"])
        with open(os.path.join(root, "EFI", "OC", "config.plist"), "rb") as f:
            self.assertEqual(plistlib.load(f)["PlatformInfo"]["Generic"]["ROM"], bytes.fromhex("A4C3F0112233"))


if __name__ == "__main__":
    unittest.main()
