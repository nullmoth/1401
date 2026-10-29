"""The EFI-partition probe the stick writer's WMI route uses, run in real PowerShell on Windows.

On a UEFI Windows the started-from EFI partition is on the disk that holds C: (the CI runner, every normal PC), so the
probe must name that disk; it must also leave no drive letter mounted behind. Elsewhere this test skips.
"""
import json
import subprocess
import sys
import unittest

from p1401 import usbwriter


@unittest.skipUnless(sys.platform == "win32", "needs Windows PowerShell, WMI and mountvol")
class BootEspProbe(unittest.TestCase):
    def run_ps(self, body):
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", body],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_the_probe_names_the_disk_windows_runs_from_and_unmounts(self):
        letters_before = self.run_ps("(Get-WmiObject Win32_LogicalDisk | ForEach-Object { $_.DeviceID }) -join ','")
        out = json.loads(self.run_ps(usbwriter._BOOT_ESP_PS + r"""
$sysd = $env:SystemDrive
$sys = @(Get-WmiObject -Query "ASSOCIATORS OF {Win32_LogicalDisk.DeviceID='$sysd'} WHERE AssocClass=Win32_LogicalDiskToPartition" | ForEach-Object { $_.DiskIndex })
$fw = (Get-ItemProperty HKLM:\\System\\CurrentControlSet\\Control -Name PEFirmwareType -ErrorAction SilentlyContinue).PEFirmwareType
@{ known = $espKnown; esp = $espDisk; sys = @($sys); firmware = $fw } | ConvertTo-Json -Compress"""))
        print("probe:", out)
        if out["firmware"] == 2:     # UEFI: the EFI partition must be found
            self.assertTrue(out["known"], out)
        # On UEFI it is the EFI partition, on legacy BIOS the active partition Windows reports as its system volume
        # (on the CI runner that is C: itself). Either way, when found it is on the disk Windows runs from; when not
        # found the callers keep the conservative rule.
        if out["known"]:
            self.assertIn(out["esp"], out["sys"] if isinstance(out["sys"], list) else [out["sys"]], out)
        letters_after = self.run_ps("(Get-WmiObject Win32_LogicalDisk | ForEach-Object { $_.DeviceID }) -join ','")
        self.assertEqual(letters_before, letters_after, "the probe left a drive letter mounted")


if __name__ == "__main__":
    unittest.main()
