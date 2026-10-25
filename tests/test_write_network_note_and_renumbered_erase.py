"""Two 2.0.1 write failures: the no-installer-network STOP that had no way past it, and a stick renumbered before the
raw erase ("cannot open \\\\.\\PhysicalDrive1 (Windows error 2)")."""
import tempfile
import unittest
from unittest.mock import patch

from p1401 import netsupport, rawdisk, usbwriter


class Reached(Exception):
    pass


class NetworkNote(unittest.TestCase):
    def test_a_pc_without_installer_network_still_gets_its_stick_written(self):
        # 26 write logs on 2.0.0/2.0.1 stopped here; the window has no --allow-online, so nobody could get past it
        disk = {"Number": 2, "BusType": "USB", "Size": 16 * 10**9}
        with tempfile.TemporaryDirectory() as efi:
            netsupport.write_marker(efi, {"offline_recommended": True, "wifi": "unsupported", "ethernet": False})
            with patch.object(usbwriter, "list_disks", return_value=[disk]), \
                 patch.object(usbwriter, "eligible", return_value=(True, [])), \
                 patch("p1401.machine_handoff.verified", return_value=None), \
                 patch("p1401.apple.local_image", return_value=None), \
                 patch("p1401.apple.image_info", side_effect=Reached) as info, \
                 patch("builtins.print") as out:
                with self.assertRaises(Reached):
                    usbwriter.cli_write(["2", efi, "24"])
            info.assert_called_once_with(24)
            lines = [str(c.args[0]) for c in out.call_args_list if c.args]
            self.assertTrue(any(l.startswith("NOTE ") and "no network adapter" in l for l in lines), lines)
            self.assertFalse(any(l.startswith("STOP ") for l in lines), lines)

    def test_the_note_no_longer_sends_users_after_the_same_recovery_image(self):
        self.assertNotIn("BaseSystem", netsupport.OFFLINE_INSTALLER_MESSAGE)
        self.assertNotIn("--allow-online", netsupport.OFFLINE_INSTALLER_MESSAGE)


class RenumberedErase(unittest.TestCase):
    def setUp(self):
        self.disk = {"Number": 1, "BusType": "USB", "Size": 16 * 10**9, "FriendlyName": "TOSHIBA USB FLASH DRIVE",
                     "SerialNumber": "S1"}

    def run_write(self, wipe_effects, now):
        with tempfile.TemporaryDirectory() as efi, \
             patch.object(usbwriter, "eligible", return_value=(True, [])), \
             patch("p1401.validate.validate", return_value={"ok": True}), \
             patch.object(usbwriter, "check_script", return_value=""), \
             patch.object(usbwriter, "_free_letter", return_value="Z"), \
             patch.object(usbwriter, "current_number", return_value=now), \
             patch.object(usbwriter, "_ps", side_effect=["", Reached()]), \
             patch.object(rawdisk, "wipe_mbr_fat32", side_effect=wipe_effects) as wipe:
            with self.assertRaises(Reached):
                usbwriter.write(self.disk, efi, {})
            return [c.args[0] for c in wipe.call_args_list]

    def test_a_stick_that_came_back_as_another_disk_is_found_and_erased(self):
        gone = rawdisk.DiskError(r"cannot open \\.\PhysicalDrive1 (Windows error 2)")
        self.assertEqual(self.run_write([gone, None], now=4), [1, 4])

    def test_a_stick_that_is_really_gone_still_stops(self):
        gone = rawdisk.DiskError(r"cannot open \\.\PhysicalDrive1 (Windows error 2)")
        with self.assertRaises(rawdisk.DiskError):
            self.run_write([gone], now=1)

    def test_other_errors_never_erase_a_second_disk(self):
        other = rawdisk.DiskError("could not write to the stick (Windows error 1167)")  # 1117 now falls back to diskpart
        with patch.object(usbwriter, "current_number", return_value=4) as moved, self.assertRaises(rawdisk.DiskError):
            with tempfile.TemporaryDirectory() as efi, \
                 patch.object(usbwriter, "eligible", return_value=(True, [])), \
                 patch("p1401.validate.validate", return_value={"ok": True}), \
                 patch.object(usbwriter, "check_script", return_value=""), \
                 patch.object(usbwriter, "_free_letter", return_value="Z"), \
                 patch.object(usbwriter, "_ps", return_value=""), \
                 patch.object(rawdisk, "wipe_mbr_fat32", side_effect=[other]) as wipe:
                usbwriter.write(self.disk, efi, {})
        self.assertEqual(wipe.call_count, 1)
        moved.assert_not_called()


if __name__ == "__main__":
    unittest.main()
