"""PowerShell and diskpart print in the console's code page. On a Chinese Windows reading PowerShell's output as UTF-8
raised UnicodeDecodeError and the write stopped with an empty "UsbError:" (1.14.1 write logs)."""
import subprocess
import unittest
from unittest import mock

from p1401 import usbwriter


class CodePage(unittest.TestCase):
    def test_powershell_is_told_to_write_utf8_and_bad_bytes_never_stop_the_write(self):
        seen = {}

        def run(cmd, **kw):
            seen["cmd"], seen["kw"] = cmd, kw
            return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")
        with mock.patch("platform.system", return_value="Windows"), mock.patch("subprocess.run", run):
            usbwriter._ps("Get-Disk")
        self.assertTrue(seen["cmd"][-1].startswith("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "))
        self.assertTrue(seen["cmd"][-1].endswith("Get-Disk"))
        self.assertEqual(seen["kw"].get("encoding"), "utf-8")
        self.assertEqual(seen["kw"].get("errors"), "replace")

    def test_a_failing_command_still_reports_its_own_message(self):
        def run(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="Access denied")
        with mock.patch("platform.system", return_value="Windows"), mock.patch("subprocess.run", run):
            with self.assertRaises(usbwriter.UsbError) as cm:
                usbwriter._ps("Clear-Disk")
        self.assertIn("Access denied", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
