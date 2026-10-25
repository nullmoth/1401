"""DISK-LIST-EMPTY: Get-Disk and MSFT_Disk list nothing (no Storage Management Provider) while classic WMI lists the
disks. 1401 lists them through Win32_DiskDrive, checks the stick there and erases it with diskpart alone."""
import json
import unittest
from unittest.mock import patch

from p1401 import usbwriter

STICK = {"Index": 3, "Model": "SanDisk Ultra", "SerialNumber": " 4C53 ", "PNPDeviceID": "USBSTOR\\DISK&VEN_SANDISK\\1",
         "InterfaceType": "USB", "MediaType": "Removable Media", "Size": 15998753280, "IsSystem": False, "IsBoot": False}
SYSTEM = {"Index": 0, "Model": "Samsung SSD 980", "SerialNumber": "S1", "PNPDeviceID": "SCSI\\DISK&VEN_NVME\\1",
          "InterfaceType": "SCSI", "MediaType": "Fixed hard disk media", "Size": 500105249280, "IsSystem": True, "IsBoot": True}
TRUE_SIZE = 16005464064   # what MSFT_Disk (the window) reports for the same stick: Win32 rounds down to whole cylinders


def ps_without_storage(wmi):
    """A PowerShell on which every storage-provider query is empty and classic WMI answers."""
    calls = []

    def ps(script):
        calls.append(script)
        if "Win32_DiskDrive | ForEach-Object" in script:
            return json.dumps(wmi)
        return ""
    return ps, calls


class WmiListing(unittest.TestCase):
    def listed(self, wmi):
        ps, calls = ps_without_storage(wmi)
        with patch.object(usbwriter, "_ps", ps), patch.object(usbwriter, "_repair_storage_wmi", return_value=False), \
             patch("builtins.print") as out:
            disks = usbwriter.list_disks()
        return disks, " ".join(str(c.args[0]) for c in out.call_args_list if c.args)

    def test_disks_come_from_win32_diskdrive_when_the_storage_service_lists_none(self):
        disks, said = self.listed([SYSTEM, STICK])
        self.assertEqual([d["Number"] for d in disks], [0, 3])
        stick = disks[1]
        self.assertEqual((stick["BusType"], stick["FriendlyName"], stick["SerialNumber"], stick["Via"]),
                         ("USB", "SanDisk Ultra", "4C53", "Win32_DiskDrive"))
        self.assertIn("read from Win32_DiskDrive instead", said)

    def test_the_disk_windows_runs_from_is_refused(self):
        disks, _ = self.listed([SYSTEM, STICK])
        ok, why = usbwriter.eligible(disks[0])
        self.assertFalse(ok)
        self.assertTrue(any("booted from" in w for w in why) and any("system partition" in w for w in why), why)
        self.assertTrue(usbwriter.eligible(disks[1])[0])

    def test_a_usbstor_device_counts_as_usb_whatever_its_interface_says(self):
        disks, _ = self.listed([{**STICK, "InterfaceType": "SCSI"}])
        self.assertEqual(disks[0]["BusType"], "USB")

    def test_get_disk_results_still_win_when_present(self):
        def ps(script):
            if script.startswith("Get-Disk"):
                return json.dumps([{"Number": 3, "BusType": "USB", "Size": TRUE_SIZE}])
            raise AssertionError("no fallback query when Get-Disk answers: " + script[:60])
        with patch.object(usbwriter, "_ps", ps):
            self.assertNotIn("Via", usbwriter.list_disks()[0])


class WmiRefind(unittest.TestCase):
    def disks(self):
        ps, _ = ps_without_storage([SYSTEM, STICK])
        with patch.object(usbwriter, "_ps", ps), patch.object(usbwriter, "_repair_storage_wmi", return_value=False), \
             patch("builtins.print"):
            return usbwriter.list_disks()

    def test_the_window_stick_is_found_despite_the_cylinder_rounded_size(self):
        hit = usbwriter.refind(self.disks(), "USBSTOR-WINDOW-ID", str(TRUE_SIZE), "SanDisk Ultra")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["Number"], 3)

    def test_a_size_far_from_the_stick_does_not_match(self):
        self.assertIsNone(usbwriter.refind(self.disks(), "", str(TRUE_SIZE + 64 * 2**20), "SanDisk Ultra"))
        self.assertIsNone(usbwriter.refind(self.disks(), "", str(STICK["Size"] - 1), "SanDisk Ultra"))


class WmiWrite(unittest.TestCase):
    def test_the_check_reads_only_classic_wmi_and_names_every_identity_field(self):
        d = {"Number": 3, "FriendlyName": "SanDisk Ultra", "SerialNumber": "4C53", "Size": STICK["Size"], "BusType": "USB",
             "Via": "Win32_DiskDrive"}
        s = usbwriter.wmi_check_script(d)
        for need in ("Win32_DiskDrive", "-ne 15998753280", "'SanDisk Ultra'", "'4C53'", "$sys -contains 3",
                     "$boot -contains 3", "1401-OS-PARTITIONS"):
            self.assertIn(need, s)
        for storage in ("Get-Disk", "Get-Partition", "MSFT_Disk", "Clear-Disk", "Format-Volume"):
            self.assertNotIn(storage, s)
        self.assertNotIn("1401-OS-PARTITIONS", usbwriter.wmi_check_script(d, erase_os=True))

    def test_the_erase_is_diskpart_alone_and_never_a_storage_cmdlet(self):
        d = {"Number": 3, "FriendlyName": "SanDisk Ultra", "SerialNumber": "4C53", "Size": STICK["Size"], "BusType": "USB",
             "Via": "Win32_DiskDrive"}
        scripts, parts = [], []
        with patch.object(usbwriter, "_ps", side_effect=lambda s: scripts.append(s) or ""), \
             patch.object(usbwriter, "_diskpart", side_effect=parts.append), \
             patch.object(usbwriter, "_free_letter", return_value="Q"), \
             patch.object(usbwriter.os.path, "isdir", return_value=True), patch("builtins.print"):
            root = usbwriter._write_wmi_erase(d, erase_os=False)
        self.assertEqual(root, "Q:\\")
        self.assertEqual(len(parts), 1)
        self.assertIn("select disk 3", parts[0])
        self.assertIn("format fs=fat32 quick", parts[0])
        self.assertTrue(all("Get-Disk" not in s and "Get-Partition" not in s for s in scripts), scripts)

    def test_a_refused_check_erases_nothing(self):
        d = {"Number": 3, "FriendlyName": "SanDisk Ultra", "SerialNumber": "4C53", "Size": STICK["Size"], "BusType": "USB",
             "Via": "Win32_DiskDrive"}
        with patch.object(usbwriter, "_ps", side_effect=usbwriter.UsbError("1401: disk 3 is not the USB stick")), \
             patch.object(usbwriter, "_diskpart") as dp, patch("builtins.print"):
            with self.assertRaises(usbwriter.UsbError):
                usbwriter._write_wmi_erase(d, erase_os=False)
        dp.assert_not_called()

    def test_write_takes_the_wmi_route_for_a_wmi_disk(self):
        d = {"Number": 3, "FriendlyName": "SanDisk Ultra", "SerialNumber": "4C53", "Size": STICK["Size"], "BusType": "USB",
             "Via": "Win32_DiskDrive"}
        with patch("p1401.validate.validate", return_value={"ok": True}), \
             patch.object(usbwriter, "_write_wmi_erase", return_value="Q:\\") as erase, \
             patch.object(usbwriter, "_write_payload", return_value={"root": "Q:\\"}) as payload, \
             patch.object(usbwriter, "check_script", side_effect=AssertionError("Get-Disk check on a WMI disk")):
            self.assertEqual(usbwriter.write(d, "efi", {}), {"root": "Q:\\"})
        erase.assert_called_once()
        payload.assert_called_once()


if __name__ == "__main__":
    unittest.main()
