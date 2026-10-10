"""A stick whose controller reports a new serial on every read is still accepted, and only when it cannot be confused
with another disk (10-10: one SMI stick, 7 writes, 7 serials, each refused "disk 1 is not the USB stick you picked").

Where PowerShell exists (the Windows CI runner) the real check script runs against a mocked Get-Disk; elsewhere the
script's structure is checked."""
import shutil
import subprocess
import tempfile
import unittest

from p1401 import usbwriter

PICK = {"Number": 1, "FriendlyName": "SMI USB DISK", "SerialNumber": "UIWtXGCjyg72Pbiw", "BusType": "USB",
        "Size": 31457280000, "IsBoot": False, "IsSystem": False, "IsOffline": False, "IsReadOnly": False, "PartitionStyle": "MBR"}
PS = shutil.which("pwsh") or shutil.which("powershell")


def disk(num, serial, name="SMI USB DISK", size=31457280000):
    return (f"[pscustomobject]@{{Number={num}; SerialNumber='{serial}'; FriendlyName='{name}'; Size={size}; BusType='USB'; "
            f"IsBoot=$false; IsSystem=$false; PartitionStyle='MBR'}}")


def run_check(disks):
    mock = "function Get-Partition { @() }\nfunction Get-Disk { param($Number, $ErrorAction) $all = @(" + ",".join(disks) + \
           "); if ($null -ne $Number) { $all | Where-Object Number -eq $Number } else { $all } }\n"
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False) as f:
        f.write(mock + usbwriter.check_script(PICK) + "\n'ACCEPTED'\n")
    r = subprocess.run([PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", f.name], capture_output=True, text=True, timeout=60)
    return "ACCEPTED" in r.stdout


class UnstableSerial(unittest.TestCase):
    def test_both_checks_use_the_same_stick_rule(self):
        for script in (usbwriter.check_script(PICK), usbwriter.format_script(PICK)):
            self.assertIn("$twins.Count -eq 1", script)
            self.assertIn("$named.Count -eq 0", script)
            self.assertIn("if (-not $same -or", script)

    @unittest.skipUnless(PS, "PowerShell runs this on the Windows CI runner")
    def test_a_new_serial_on_the_only_matching_stick_is_accepted(self):
        self.assertTrue(run_check([disk(0, "SYS", "Samsung SSD", 1000204886016), disk(1, "TGg51Hf6PzTbgrgh")]))

    @unittest.skipUnless(PS, "PowerShell runs this on the Windows CI runner")
    def test_two_identical_sticks_with_new_serials_are_refused(self):
        self.assertFalse(run_check([disk(1, "AAAA"), disk(2, "BBBB")]))

    @unittest.skipUnless(PS, "PowerShell runs this on the Windows CI runner")
    def test_a_different_model_at_the_same_number_is_refused(self):
        self.assertFalse(run_check([disk(1, "ZZZZ", "SanDisk Ultra")]))

    @unittest.skipUnless(PS, "PowerShell runs this on the Windows CI runner")
    def test_the_picked_serial_moving_to_another_disk_is_refused(self):
        self.assertFalse(run_check([disk(1, "NEW1"), disk(3, "UIWtXGCjyg72Pbiw", "Other", 64000000000)]))


if __name__ == "__main__":
    unittest.main()
