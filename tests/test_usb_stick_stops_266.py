"""Stick stops seen in 2.6.5 write logs: no free letter between G: and Z:, an offline stick, a stick whose drive went
away during the EFI copy, and diskpart's letter never appearing. Each stop names what it saw and what to do. No disk is
touched: every Windows call is replaced."""
import os
import unittest
from unittest.mock import patch

from p1401 import usbwriter

USB = {"Number": 3, "FriendlyName": "Kingston DataTraveler 3.0", "SerialNumber": "X", "BusType": "USB",
       "Size": 32 * 10**9, "IsBoot": False, "IsSystem": False, "IsOffline": False, "IsReadOnly": False}


def letters(used, present=()):
    """_free_letter with these letters listed by Windows and these roots existing."""
    with patch.object(usbwriter.os, "listdrives", create=True, new=lambda: [c + ":\\" for c in used]), \
            patch.object(usbwriter.os.path, "exists", lambda p: p[:1] in present):
        return usbwriter._free_letter()


class DriveLetters(unittest.TestCase):
    def test_z_is_preferred_when_free(self):
        self.assertEqual(letters("CD"), "Z")

    def test_g_to_z_taken_falls_back_to_f_e_d(self):
        self.assertEqual(letters("C" + "GHIJKLMNOPQRSTUVWXYZ"), "F")
        self.assertEqual(letters("CF" + "GHIJKLMNOPQRSTUVWXYZ"), "E")

    def test_negative_control_every_letter_taken_stops_naming_them(self):
        with self.assertRaises(usbwriter.UsbError) as cm:
            letters("ABCDEF" + "GHIJKLMNOPQRSTUVWXYZ")
        self.assertIn("in use: A B C D E F G", str(cm.exception))
        self.assertIn("Disk Management", str(cm.exception))

    def test_a_root_that_exists_without_being_listed_is_still_taken(self):
        self.assertEqual(letters("C", present="Z"), "Y")


class OfflineStick(unittest.TestCase):
    def test_an_offline_stick_says_why_and_how_to_bring_it_online(self):
        ok, why = usbwriter.eligible({**USB, "IsOffline": True, "OfflineReason": 4})
        self.assertFalse(ok)
        self.assertIn("offline (its disk signature collides with another disk's)", why[0])
        self.assertIn("choose Online", why[0])

    def test_an_unknown_reason_still_gives_the_way_out(self):
        ok, why = usbwriter.eligible({**USB, "IsOffline": True})
        self.assertFalse(ok)
        self.assertIn("Windows has this stick offline.", why[0])

    def test_negative_control_an_online_stick_is_accepted(self):
        self.assertTrue(usbwriter.eligible({**USB, "OfflineReason": 4})[0])

    def test_the_disk_list_asks_windows_for_the_reason(self):
        self.assertIn("OfflineReason", usbwriter.FIELDS.split(","))


class DriveWentAway(unittest.TestCase):
    def copy(self, root_there):
        def copytree(src, dst, dirs_exist_ok=False):
            raise FileNotFoundError(3, "The system cannot find the path specified", "E:\\")
        with patch.object(usbwriter.shutil, "copytree", copytree), \
                patch.object(usbwriter.os.path, "isdir", lambda p: root_there):
            usbwriter._copy_settled("src", "E:\\EFI", "E:\\", tries=3, sleep=lambda s: None)

    def test_a_drive_gone_for_every_retry_says_the_stick_dropped_off(self):
        with self.assertRaises(usbwriter.UsbError) as cm:
            self.copy(root_there=False)
        self.assertIn("E:\\ went away", str(cm.exception))
        self.assertIn("back of the PC", str(cm.exception))

    def test_negative_control_a_drive_still_there_keeps_the_real_error(self):
        with self.assertRaises(FileNotFoundError):
            self.copy(root_there=True)


class LetterNeverAppeared(unittest.TestCase):
    def test_the_stop_carries_what_the_stick_search_said(self):
        disk = {**USB, "PartitionStyle": "MBR"}
        with patch.object(usbwriter, "eligible", lambda d, allow_large=False: (True, [])), \
                patch.object(usbwriter, "_ps", lambda script: "NOLETTER partition 1 size 32000000000"), \
                patch.object(usbwriter, "_free_letter", lambda: "Q"), \
                patch.object(usbwriter.os.path, "isdir", lambda p: False), \
                patch.object(usbwriter.time, "sleep", lambda s: None), \
                patch("p1401.validate.validate", lambda d: {"ok": True}), \
                patch("p1401.rawdisk.wipe_mbr_fat32", lambda *a, **k: None), \
                patch.object(usbwriter, "release", lambda n: None, create=True), \
                patch.object(usbwriter, "_diskpart", lambda s: None):
            with self.assertRaises(usbwriter.UsbError) as cm:
                usbwriter.write(disk, "efi", {"local": True})
        self.assertIn("did not appear (the stick search said: NOLETTER partition 1", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
