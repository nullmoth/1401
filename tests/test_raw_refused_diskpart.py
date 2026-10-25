"""A stick whose raw sector write ends with access denied (5) or an I/O device error (1117) is erased with diskpart
instead of stopping the write (two 2.5.4 sticks stopped on 1117); any other raw error still stops."""
import unittest
from unittest.mock import patch

from p1401 import rawdisk, usbwriter

DISK = {"Number": 2, "FriendlyName": "Generic Flash Disk", "SerialNumber": "1", "Size": 16 * 2**30, "BusType": "USB"}


def write_with(err):
    parts = []
    with patch("p1401.validate.validate", return_value={"ok": True}), \
         patch.object(usbwriter, "_ps", return_value="LETTER=Q"), \
         patch.object(usbwriter, "_free_letter", return_value="Q"), \
         patch.object(rawdisk, "wipe_mbr_fat32", side_effect=rawdisk.DiskError(
             f"could not write to the stick (Windows error {err}). Use another USB stick")), \
         patch.object(usbwriter, "current_number", return_value=2), patch.object(usbwriter, "release"), \
         patch.object(usbwriter, "_diskpart", side_effect=parts.append), \
         patch.object(usbwriter.os.path, "isdir", return_value=True), \
         patch.object(usbwriter, "_write_payload", return_value={"root": "Q:\\"}), patch("builtins.print"):
        usbwriter.write(DISK, "efi", {})
    return parts


class RawRefused(unittest.TestCase):
    def test_io_device_error_falls_back_to_diskpart(self):
        self.assertEqual(len(write_with(1117)), 1)

    def test_access_denied_still_falls_back(self):
        self.assertEqual(len(write_with(5)), 1)

    def test_another_error_still_stops(self):
        with self.assertRaises(rawdisk.DiskError):
            write_with(1167)

    def test_an_error_that_only_starts_with_5_is_not_access_denied(self):
        with self.assertRaises(rawdisk.DiskError):
            write_with(55)


if __name__ == "__main__":
    unittest.main()
