"""Every engine option a user may choose has a control: each p1401 build option and each stick-writer option appears in the
Windows window or is listed here as set by the app itself; each Mac setup option appears in the Mac app. A new option
without either fails this test, so it cannot ship unreachable."""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FORM = (ROOT / "windows/App/MainForm.cs").read_text(encoding="utf-8")
MAIN = (ROOT / "p1401/__main__.py").read_text()
USB = (ROOT / "p1401/usbwriter.py").read_text()
SETUP = (ROOT / "mac/Resources/nullmoth-setup.sh").read_text()
MAC_SRC = "".join(p.read_text() for p in (ROOT / "mac/Sources").glob("*.swift"))

# set by the app from what it knows, not chosen by the user (the reason is the value)
SET_BY_THE_WINDOW = {
    "--macos": "the Sequoia / Tahoe picker", "--json": "the window always asks for the result as JSON",
    "--boot-log": "the newest startup log on the stick, found by the window", "--stopped-at": "the line the user typed after a stop",
    "--echo": "engine debugging output", "--state": "storage-prep keeps its record at the default path the window also reads",
}
SET_BY_THE_MAC_APP = {
    "--dry": "the preview run before an install", "--remove": "the Remove button", "--update": "the Tahoe preparation buttons",
    "--collect-logs": "Send logs", "--efi": "the EFI picker", "--pkg": "the checked package", "--sha": "its SHA-256",
    "--tool": "the app's own recovery tool", "--app": "the app binary", "--verbose": "the verbose-boot switch", "--efi-read": "the EFI check",
    "--knob": "the profile switches", "--profile": "the machine profile", "--usbmap": "the USB map builder", "--backlight": "the backlight switch",
    "--hidpi": "the HiDPI switch", "--xe": "the Intel Xe switch", "--gpu-test": "the AMD / Intel test driver switch",
    "--hybrid": "the hybrid laptop switch", "--game-mode": "Game Mode: setup's installer-time route to the bundled service script; the Game Mode card in the Tools tab runs the same script directly (GameMode.swift)", "--experimental": "the Experimental features pane", "--autologin-off": "the automatic login switch",
}


class Options(unittest.TestCase):
    def test_every_build_option_has_a_checkbox_or_is_set_by_the_window(self):
        flags = set(re.findall(r'add_argument\("(--[a-z-]+)"', MAIN))
        self.assertGreaterEqual(len(flags), 9)
        missing = sorted(f for f in flags if f not in FORM and f not in SET_BY_THE_WINDOW)
        self.assertEqual(missing, [], "add a control for each in windows/App/MainForm.cs")

    def test_every_stick_writer_option_is_passed_by_the_window(self):
        body = USB[USB.index("def cli_write"):USB.index('if __name__ == "__main__"')]
        flags = set(re.findall(r'"(--[a-z-]+)"', body))
        self.assertGreaterEqual(len(flags), 9)
        self.assertEqual(sorted(f for f in flags if f not in FORM), [])

    def test_every_mac_setup_option_is_reachable_from_the_mac_app(self):
        loop = SETUP[SETUP.index("while [ $# -gt 0 ]; do case"):SETUP.index("STOP unknown option")]
        flags = set(re.findall(r"(--[a-z-]+)\)", loop))
        self.assertGreaterEqual(len(flags), 15)
        missing = sorted(f for f in flags if f not in MAC_SRC and f not in SET_BY_THE_MAC_APP)
        self.assertEqual(missing, [])
        # and the ones the table says are set by a button really are mentioned by the Swift or the page
        unreachable = sorted(f for f in SET_BY_THE_MAC_APP if f in flags and f not in MAC_SRC)
        self.assertEqual(unreachable, [])

    def test_the_ryzen_power_profile_is_one_pane_with_limits_on_off_and_status(self):
        page = (ROOT / "mac/Resources/index.html").read_text()
        for el in ("ryzon", "ryzoff", "ryzstat", "ryst", "rysl", "ryfa", "rytm"):
            self.assertIn(f'id="{el}"', page)
        for gone in ("ryinstall", "ryremove", "rystatus"):
            self.assertNotIn(f'id="{gone}"', page)       # the second pane (a user-chosen RyzenAdj) is gone
        self.assertNotIn('case "ryzen":', MAC_SRC)
        self.assertEqual(page.count("Ryzen laptop power profile"), 1)
        self.assertIn('"--ryzen-limits", limits', MAC_SRC)
        self.assertIn('"--ryzen-power", "status"', MAC_SRC)

    def test_gpu_boost_has_its_pane_and_the_app_reads_its_status_without_a_password(self):
        page = (ROOT / "mac/Resources/index.html").read_text()
        for el in ("boston", "bostoff", "bostrm", "bostat", "bostr"):
            self.assertIn(f'id="{el}"', page)
        self.assertIn("--gpu-boost", MAC_SRC)
        self.assertIn("GPUBoost.describe", MAC_SRC)
        # no Windows flag exists for it: the daemon is part of the Mac driver package, so the stick writer and the build have nothing to expose
        self.assertNotIn("gpu-boost", MAIN + USB)

    def test_the_mac_app_explains_the_vmd_route_and_names_the_external_drive_checkbox(self):
        page = (ROOT / "mac/Resources/index.html").read_text()
        self.assertIn('id="vmdpane"', page)
        self.assertIn("Install macOS on an external drive", page)
        self.assertIn("vmdOrRaid", MAC_SRC)
        self.assertIn("Install macOS on an external drive", FORM)

    def test_the_new_windows_choices_are_off_by_default_and_rebuild_on_change(self):
        for cb in ("persistNvram", "externalTarget", "newIdentity"):
            self.assertIn(cb, FORM)
        self.assertIn("cb.AutoSize = true; cb.Checked = false;", FORM)
        self.assertIn("(persistNvram.Checked ? \" --persistent-nvram-amd\" : \"\")", FORM)
        self.assertIn("(externalTarget.Checked ? \" --external-target\" : \"\")", FORM)
        self.assertIn("(newIdentity.Checked ? \" --new-identity\" : \"\")", FORM)


if __name__ == "__main__":
    unittest.main()
