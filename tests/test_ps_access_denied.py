"""Windows refusing to start PowerShell ("[WinError 5] Access is denied" in CreateProcess, security software) is retried
once, and if it persists the STOP names the cause instead of a raw PermissionError (2.0.4 write logs, 10-16)."""
import subprocess
import unittest
from unittest.mock import patch

from p1401 import usbwriter


class AccessDenied(unittest.TestCase):
    def run_ps(self, effects):
        with patch.object(usbwriter.platform, "system", return_value="Windows"), \
             patch.object(usbwriter, "_system_tool", return_value="powershell.exe"), \
             patch.object(usbwriter.time, "sleep") as slept, \
             patch.object(usbwriter.subprocess, "run", side_effect=effects) as run:
            try:
                return usbwriter._ps("Get-Disk"), run.call_count, slept.call_count, None
            except usbwriter.UsbError as e:
                return None, run.call_count, slept.call_count, str(e)

    def test_a_single_refusal_is_retried(self):
        ok = subprocess.CompletedProcess([], 0, stdout="fine", stderr="")
        out, calls, sleeps, err = self.run_ps([PermissionError(13, "Access is denied"), ok])
        self.assertEqual((out, calls, sleeps, err), ("fine", 2, 1, None))

    def test_a_lasting_refusal_names_security_software(self):
        out, calls, sleeps, err = self.run_ps([PermissionError(13, "Access is denied")] * 2)
        self.assertIsNone(out)
        self.assertEqual(calls, 2)
        self.assertIn("refused to start PowerShell", err)
        self.assertIn("antivirus", err)

    def test_other_errors_are_not_retried(self):
        bad = subprocess.CompletedProcess([], 1, stdout="", stderr="Format-Volume failed")
        out, calls, sleeps, err = self.run_ps([bad])
        self.assertEqual((calls, sleeps), (1, 0))
        self.assertIn("Format-Volume failed", err)


if __name__ == "__main__":
    unittest.main()
