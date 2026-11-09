"""The ARM apps choice on the write page is OFF unless the user ticks it, and unticked the stick is written exactly as
before.

Ticked, the stick's NullMoth/system-profile.json carries one extra top-level key,
    "opt_in": {"arm_apps": true, "from": "1401-windows", "schema": 1}
which the Mac app reads (it already loads every stick's system-profile.json into its machine profile, and the driver
setup keeps that record in /Library/NullMoth/system-profile.json). On its first launch after setup the Mac app offers
one click to finish the signed, SHA-256 checked install, or names why this Mac's processor cannot run it. Nothing on
Windows downloads or installs the ARM package, and the window's text must not promise more than that offer.

The arms drive the real copy_to_installer() and cli_write() with the disk and Apple stubbed, and read the window's
source for the default and the flag it passes.
"""
import json
import pathlib
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from p1401 import machine_handoff, usbwriter

ROOT = pathlib.Path(__file__).resolve().parents[1]
FORM = (ROOT / "windows/App/MainForm.cs").read_text(encoding="utf-8")
LOC = (ROOT / "windows/App/Loc.cs").read_text(encoding="utf-8")
REQUEST = {"arm_apps": True, "from": "1401-windows", "schema": 1}


class ArmAppsOptIn(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.build = self.root / "build"
        (self.build / "EFI/OC").mkdir(parents=True)
        (self.build / "EFI/OC/config.plist").write_bytes(b"validated configuration")
        self.scan = self.root / "Report.json"
        self.scan.write_text(json.dumps({"CPU": {"Processor Name": "Processor"}, "GPU": {}}))
        result = SimpleNamespace(hardware={"CPU": {"Processor Name": "Processor"}, "GPU": {}}, disabled_devices={},
                                 acpi_fingerprints=[], out_dir=str(self.build), macos_version="24.6.0", smbios="iMacPro1,1")
        self.value = machine_handoff.create(str(self.scan), result)

    def stick(self, name, opt_in):
        machine_handoff.copy_to_installer(self.value, str(self.root / name), opt_in)
        return (self.root / name / "NullMoth/system-profile.json").read_bytes()

    def test_unticked_writes_the_same_bytes_as_before_the_choice_existed(self):
        # the pre-choice call shape (two arguments) is the reference
        machine_handoff.copy_to_installer(self.value, str(self.root / "old"))
        before = (self.root / "old/NullMoth/system-profile.json").read_bytes()
        self.assertEqual(self.stick("unticked", machine_handoff.opt_in(arm_apps=False)), before)
        self.assertNotIn(b"opt_in", before)

    def test_ticked_adds_only_the_opt_in_key(self):
        plain = json.loads(self.stick("plain", None))
        ticked = json.loads(self.stick("ticked", machine_handoff.opt_in(arm_apps=True)))
        self.assertEqual(ticked.pop("opt_in"), REQUEST)
        self.assertEqual(ticked, plain)

    def test_ticking_does_not_touch_the_build_bound_profile(self):
        self.stick("ticked", machine_handoff.opt_in(arm_apps=True))
        self.assertNotIn("opt_in", self.value)
        self.assertEqual(machine_handoff.verified(str(self.build), str(self.scan)), self.value)

    def run_cli(self, *flags):
        disk = {"Number": 3, "BusType": "USB", "Size": 16 * 10**9, "FriendlyName": "Stick"}
        seen = {}

        def fake_write(*a, **k):
            seen.update(k)
            return {"root": str(self.root / "cli")}
        with patch.object(usbwriter, "list_disks", return_value=[disk]), \
                patch.object(usbwriter, "eligible", return_value=(True, [])), \
                patch.object(usbwriter, "write", fake_write), \
                patch("p1401.apple.local_image", return_value={"name": "local", "local": True}), \
                patch("p1401.netsupport.needs_local_image", return_value=False), \
                patch("builtins.print") as out:
            rc = usbwriter.cli_write(["3", str(self.build), "24", "--profile", str(self.scan), *flags])
        printed = " ".join(str(c.args[0]) for c in out.call_args_list if c.args)
        return rc, seen, printed

    def test_cli_without_the_flag_requests_nothing(self):
        rc, seen, printed = self.run_cli()
        self.assertEqual(rc, 0)
        self.assertIn("opt_in", seen)
        self.assertIsNone(seen["opt_in"])
        self.assertNotIn("ARM apps", printed)

    def test_cli_with_the_flag_carries_the_request_to_the_stick(self):
        rc, seen, printed = self.run_cli("--arm-apps")
        self.assertEqual(rc, 0)
        self.assertEqual(seen["opt_in"], REQUEST)
        self.assertIn("ARM apps requested", printed)

    def test_window_box_is_off_by_default_and_passes_the_flag_only_when_ticked(self):
        self.assertIn("armApps.Checked = false;", FORM)
        self.assertEqual(FORM.count("--arm-apps"), 1)
        self.assertIn('if (armApps.Checked && armApps.Visible) args += " --arm-apps";', FORM)
        # shown on the write page only, only for a stick that carries the NVIDIA driver, frozen once written
        self.assertIn('if (summary.Contains("NVIDIA")) Show(disks, refresh, armApps, fullInstaller, recoveryPick, bar, log); else Show(disks, refresh, fullInstaller, recoveryPick, bar, log);', FORM)
        self.assertIn("armApps.Enabled = !written;", FORM)
        self.assertIn("armApps.SetBounds(", FORM)

    def test_window_text_is_translated(self):
        start = FORM.index('armApps.Text = Loc.T("') + len('armApps.Text = Loc.T("')
        text = FORM[start:FORM.index('");', start)]
        self.assertIn("(opt-in)", text)
        # the Mac side offers a click, it does not install by itself: the text must say so and never claim an install
        self.assertIn("offers to finish", text)
        self.assertNotIn("installs", text)
        self.assertIn('{ "' + text + '",', LOC)


if __name__ == "__main__":
    unittest.main()
