"""Windows tools start by their System32 path (1.7 log: WinError 2 starting plain "powershell"), and a NUL drive letter
counts as no letter (1.6/1.7: Format-Volume "Invalid property" + format.com "Required parameter missing")."""
import os
import tempfile
import unittest
from unittest import mock

from p1401 import usbwriter
from tests.test_unstable_serial import PICK


class SystemTools(unittest.TestCase):
    def test_a_tool_present_under_system32_is_used_by_full_path(self):
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "System32", "WindowsPowerShell", "v1.0"))
        exe = os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        open(exe, "w").close()
        with mock.patch.dict(os.environ, {"SystemRoot": root}):
            self.assertEqual(usbwriter._system_tool("WindowsPowerShell", "v1.0", "powershell.exe"), exe)

    def test_a_missing_tool_falls_back_to_its_name(self):
        with mock.patch.dict(os.environ, {"SystemRoot": tempfile.mkdtemp()}):
            self.assertEqual(usbwriter._system_tool("diskpart.exe"), "diskpart.exe")

    def test_the_letter_check_rejects_anything_but_a_to_z(self):
        import inspect
        src = inspect.getsource(usbwriter.write)
        self.assertIn("'^[A-Za-z]$'", src)
        self.assertIn("-lt 5 -and -not $letter;", src)
        self.assertNotIn("-and -not $letter.Trim();", src)


if __name__ == "__main__":
    unittest.main()
