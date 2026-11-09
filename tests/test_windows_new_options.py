"""The Windows window exposes the 2.9 engine options: the full macOS installer (fetched and checked before the stick is erased,
refused on a stick under 32 GB), the user's own USB port map, and the notices for settings taken from known machines.
The C# is built on the mini; these arms pin the wiring to the engine's own command lines."""
import pathlib
import re
import unittest

from p1401 import fullinstaller

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / "windows/App/MainForm.cs").read_text(encoding="utf-8")


class WindowsOptions(unittest.TestCase):
    def test_the_full_installer_is_fetched_before_the_erase_and_passed_to_the_writer(self):
        fetch = SRC.index('"p1401.fullinstaller fetch "')
        write = SRC.index('"p1401.usbwriter write "')
        confirm = SRC.index('Erase {0}')
        self.assertLess(confirm, fetch, "asked once, then the download")
        self.assertLess(fetch, write)
        self.assertIn('args += " --full-installer " + Engine.Q(fullPkg)', SRC)

    def test_a_stick_under_32_gb_is_refused_with_the_number_the_engine_uses(self):
        self.assertIn("d.Size < 32UL * 1024 * 1024 * 1024", SRC)
        self.assertEqual(fullinstaller.MIN_STICK, 32 * (1 << 30))

    def test_the_option_is_off_by_default_and_needs_the_explanation(self):
        self.assertIn("fullInstaller.Checked = false", SRC)
        self.assertIn("32 GB or more", SRC)
        self.assertIn("about 5 GB", SRC)

    def test_the_command_lines_exist_in_the_engine(self):
        self.assertTrue(hasattr(fullinstaller, "cli_fetch"))
        usb = (ROOT / "p1401/usbwriter.py").read_text()
        self.assertIn('"--full-installer"', usb)
        self.assertIn('"--utbmap"', (ROOT / "p1401/__main__.py").read_text())

    def test_the_usb_map_goes_to_the_build_and_changing_it_invalidates_the_build(self):
        self.assertIn('" --utbmap " + Engine.Q(utbMapDir)', SRC)
        self.assertEqual(len(re.findall(r"utbMapDir = ", SRC)) >= 2, True)
        self.assertIn("Show(facts, log, osPick, expDrivers, utbPick)", SRC)

    def test_known_machine_and_usb_map_notices_reach_the_summary(self):
        self.assertIn('"" + rule == "known-machine"', SRC)
        self.assertIn('"" + rule == "usb-map-import"', SRC)
        self.assertIn("Setting known to work on this processor: ", SRC)


if __name__ == "__main__":
    unittest.main()
