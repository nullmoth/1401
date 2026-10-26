"""Stripped-down Windows builds drop powershell.exe from System32 (2.5.5 write logs, five runs on one PC). The writer
then takes any Windows PowerShell on PATH, then PowerShell 7, and only stops when there is none at all."""
import os
import unittest
from unittest.mock import patch

from p1401 import usbwriter


class PowerShellFallback(unittest.TestCase):
    def pick(self, system32, which, files=()):
        with patch.object(usbwriter, "_system_tool", return_value=system32), \
             patch.object(usbwriter.shutil, "which", side_effect=lambda n: which.get(n)), \
             patch.object(usbwriter.os.path, "isfile", side_effect=lambda p: p == system32 and system32 != "powershell.exe" or p in files), \
             patch.dict(os.environ, {"ProgramFiles": r"C:\Program Files"}, clear=False):
            return usbwriter.powershell()

    def test_system32_powershell_is_used_when_present(self):
        sys32 = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
        self.assertEqual(self.pick(sys32, {"pwsh.exe": r"C:\x\pwsh.exe"}), sys32)

    def test_powershell_on_path_comes_before_pwsh(self):
        self.assertEqual(self.pick("powershell.exe", {"powershell.exe": r"D:\ps\powershell.exe", "pwsh.exe": r"C:\x\pwsh.exe"}),
                         r"D:\ps\powershell.exe")

    def test_powershell_7_is_used_when_windows_powershell_is_gone(self):
        self.assertEqual(self.pick("powershell.exe", {"pwsh.exe": r"C:\x\pwsh.exe"}), r"C:\x\pwsh.exe")
        installed = os.path.join(r"C:\Program Files", "PowerShell", "7", "pwsh.exe")
        self.assertEqual(self.pick("powershell.exe", {}, files=(installed,)), installed)

    def test_with_no_powershell_at_all_the_writer_still_stops_with_its_message(self):
        self.assertEqual(self.pick("powershell.exe", {}), "powershell.exe")


if __name__ == "__main__":
    unittest.main()
