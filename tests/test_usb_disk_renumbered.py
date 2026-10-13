"""A stick that came back from an offline/online cycle under a new disk number is found again before diskpart runs
(1.15 log: diskpart "select disk 3" -> "The disk you specified is not valid")."""
import inspect
import unittest
from unittest import mock

from p1401 import usbwriter

STICK = {"Number": 3, "FriendlyName": "ADATA USB Flash Drive", "SerialNumber": "2A57", "BusType": "USB", "Size": 32017047552}


class Renumbered(unittest.TestCase):
    def number(self, ps_out):
        with mock.patch.object(usbwriter.platform, "system", return_value="Windows"), \
             mock.patch.object(usbwriter, "_ps", return_value=ps_out) as ps:
            return usbwriter.current_number(STICK), ps.call_args[0][0]

    def test_the_new_number_is_used(self):
        n, script = self.number("NUMBER=4\n")
        self.assertEqual(n, 4)
        self.assertIn("'2A57'", script)

    def test_no_single_match_keeps_the_picked_number(self):
        self.assertEqual(self.number("")[0], 3)
        self.assertEqual(self.number("NUMBER=\n")[0], 3)

    def test_off_windows_the_picked_number_stands(self):
        with mock.patch.object(usbwriter.platform, "system", return_value="Darwin"):
            self.assertEqual(usbwriter.current_number(STICK), 3)

    def test_both_diskpart_fallbacks_look_the_stick_up_again(self):
        src = inspect.getsource(usbwriter.write)
        self.assertEqual(src.count("n = current_number(disk)"), 2)
        self.assertEqual(src.count('_diskpart(diskpart_script({**disk, "Number": n}, letter))'), 2)
        self.assertNotIn("_diskpart(diskpart_script(disk, letter))", src)


if __name__ == "__main__":
    unittest.main()


class PowerShellTimeout(unittest.TestCase):
    """A PowerShell step that runs past the limit is a UsbError the format step falls back from, not a raw TimeoutExpired."""

    def test_timeout_is_a_usb_error(self):
        import subprocess
        def boom(*a, **k):
            raise subprocess.TimeoutExpired(cmd="powershell", timeout=300)
        with mock.patch.object(usbwriter.platform, "system", return_value="Windows"), \
             mock.patch.object(usbwriter.subprocess, "run", boom):
            with self.assertRaises(usbwriter.UsbError) as cm:
                usbwriter._ps("Format-Volume ...")
        self.assertIn("did not finish preparing", str(cm.exception))

    def test_the_format_fallback_accepts_a_timeout(self):
        src = inspect.getsource(usbwriter.write)
        self.assertIn('"did not finish preparing" not in str(e)', src)
