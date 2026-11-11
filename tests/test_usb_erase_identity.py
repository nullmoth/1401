"""The erase path re-identifies the disk inside the destructive operation, and never falls back to a stale disk number.

A USB disk that drops off and comes back under another number made the writer's earlier checks (run in a different
PowerShell process) meaningless: the raw erase took only a number, and the diskpart fallbacks reused the picked number
when no unique match was found. These tests pin the three refusals and the number the full-installer partition uses.
"""
import os
import tempfile
import unittest
from unittest import mock

from p1401 import rawdisk, usbwriter

STICK = {"Number": 3, "FriendlyName": "aigo U350", "SerialNumber": "FC262A0B28EE2", "BusType": "USB",
         "Size": 125304832000}


class Identity(unittest.TestCase):
    def test_the_same_serial_number_matches_whatever_the_model_says(self):
        ok, why = rawdisk._identity_matches(STICK, {"SerialNumber": "fc262a0b28ee2", "Model": "U350 USB Device",
                                                    "Size": STICK["Size"]})
        self.assertTrue(ok, why)

    def test_a_different_size_is_always_a_refusal(self):
        ok, why = rawdisk._identity_matches(STICK, {"SerialNumber": STICK["SerialNumber"], "Model": "aigo U350",
                                                    "Size": STICK["Size"] - 1})
        self.assertFalse(ok)
        self.assertIn("size", why)

    def test_a_controller_that_reports_another_serial_is_matched_by_model_and_size(self):
        ok, why = rawdisk._identity_matches(STICK, {"SerialNumber": "NEW-SERIAL-EACH-READ", "Model": "aigo U350 USB Device",
                                                    "Size": STICK["Size"]})
        self.assertTrue(ok, why)

    def test_a_different_disk_with_the_same_size_is_refused(self):
        ok, why = rawdisk._identity_matches(STICK, {"SerialNumber": "SOMEONE-ELSE", "Model": "Samsung Portable SSD",
                                                    "Size": STICK["Size"]})
        self.assertFalse(ok)
        self.assertIn("serial", why)

    def test_a_stick_with_no_serial_is_matched_by_model_and_size(self):
        ok, why = rawdisk._identity_matches({"Size": STICK["Size"], "FriendlyName": "aigo U350"},
                                            {"SerialNumber": "", "Model": "aigo U350 USB Device", "Size": STICK["Size"]})
        self.assertTrue(ok, why)

    def test_nothing_to_compare_is_a_refusal(self):
        ok, _ = rawdisk._identity_matches({"Size": STICK["Size"]}, {"SerialNumber": "", "Model": "", "Size": STICK["Size"]})
        self.assertFalse(ok)


class Wipe(unittest.TestCase):
    def test_a_different_disk_is_refused_before_the_partition_table_is_touched(self):
        log = []

        def ioctl(k, h, code, inbuf=b"", outsize=0):
            log.append(code)
            return True, b"", 0

        with mock.patch.object(rawdisk, "_k32", lambda: type("K", (), {"CloseHandle": lambda *a: None})()), \
             mock.patch.object(rawdisk, "_volumes_on", lambda k, d: []), \
             mock.patch.object(rawdisk, "_open", lambda k, p, access=0: 7), \
             mock.patch.object(rawdisk, "_ioctl", ioctl), \
             mock.patch.object(rawdisk, "_device_identity",
                               lambda k, h: {"SerialNumber": "OTHER", "Model": "Other Disk", "Size": STICK["Size"]}):
            with self.assertRaises(rawdisk.DiskError) as cm:
                rawdisk.wipe_mbr_fat32(3, STICK["Size"], 1 << 30, say=lambda m: None, expected=STICK)
        self.assertIn("not the USB stick that was picked", str(cm.exception))
        self.assertNotIn(rawdisk.IOCTL_DISK_DELETE_DRIVE_LAYOUT, log)

    def test_the_matching_disk_is_erased(self):
        log = []

        def ioctl(k, h, code, inbuf=b"", outsize=0):
            log.append(code)
            return True, b"", 0

        with mock.patch.object(rawdisk, "_k32", lambda: type("K", (), {"CloseHandle": lambda *a: None})()), \
             mock.patch.object(rawdisk, "_volumes_on", lambda k, d: []), \
             mock.patch.object(rawdisk, "_open", lambda k, p, access=0: 7), \
             mock.patch.object(rawdisk, "_ioctl", ioctl), \
             mock.patch.object(rawdisk, "_write_at", lambda k, h, off, data: 0), \
             mock.patch.object(rawdisk, "_device_identity",
                               lambda k, h: {"SerialNumber": STICK["SerialNumber"], "Model": "aigo U350 USB Device",
                                             "Size": STICK["Size"]}):
            rawdisk.wipe_mbr_fat32(3, STICK["Size"], 1 << 30, say=lambda m: None, expected=STICK)
        self.assertIn(rawdisk.IOCTL_DISK_DELETE_DRIVE_LAYOUT, log)

    def test_the_writer_passes_the_picked_identity_to_both_raw_attempts(self):
        import inspect
        src = inspect.getsource(usbwriter.write)
        self.assertEqual(src.count("expected=disk"), 2,
                         "the first attempt and the renumbered retry must both verify the open handle")
        self.assertNotIn("wipe_mbr_fat32(n, int(disk[\"Size\"]), PART_CAP, say=lambda m: print(m, flush=True))", src)


class FinalNumber(unittest.TestCase):
    def test_the_second_partition_is_made_on_the_number_the_write_ended_on(self):
        got = []
        with tempfile.TemporaryDirectory() as root, \
             mock.patch.object(usbwriter, "list_disks", return_value=[dict(STICK, Number=2)]), \
             mock.patch.object(usbwriter, "eligible", return_value=(True, [])), \
             mock.patch.object(usbwriter, "_free_letter", return_value="Q"), \
             mock.patch.object(usbwriter, "_diskpart", side_effect=lambda script: got.append(script)), \
             mock.patch.object(usbwriter.os.path, "isdir", return_value=True), \
             mock.patch.object(usbwriter.time, "sleep", lambda s: None), \
             mock.patch.object(usbwriter, "write", return_value={"root": root, "number": 9}), \
             mock.patch("p1401.machine_handoff.verified", return_value=None), \
             mock.patch("p1401.machine_handoff.opt_in", return_value=None), \
             mock.patch("p1401.netsupport.needs_local_image", return_value=False), \
             mock.patch("p1401.apple.local_image", return_value={"local": True, "name": "local"}), \
             mock.patch("p1401.apple.verify_local", return_value={"bytes": 1, "chunks": 1}), \
             mock.patch("p1401.fullinstaller.check_stick"), \
             mock.patch("p1401.fullinstaller.verify_xar"), \
             mock.patch("p1401.fullinstaller.place"), \
             mock.patch("builtins.print"):
            rc = usbwriter.cli_write(["2", "efi", "26", "--full-installer", os.path.join(root, "InstallAssistant.pkg")])
        self.assertEqual(rc, 0)
        self.assertTrue(got, "the second partition script was never run")
        self.assertIn("select disk 9", got[-1])
        self.assertNotIn("select disk 2", got[-1])


if __name__ == "__main__":
    unittest.main()
