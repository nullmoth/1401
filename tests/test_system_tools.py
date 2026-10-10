"""Windows tools start by their System32 path (1.7 log: WinError 2 starting plain "powershell"), and a NUL drive letter
counts as no letter (1.6/1.7: Format-Volume "Invalid property" + format.com "Required parameter missing")."""
import os
import tempfile
import unittest
from unittest import mock

from p1401 import usbwriter
from tests.test_unstable_serial import PICK


class SystemTools(unittest.TestCase):
    def test_a_tool_present_under_system32_is_used_by_full_path(self):
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "System32", "WindowsPowerShell", "v1.0"))
        exe = os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        open(exe, "w").close()
        with mock.patch.dict(os.environ, {"SystemRoot": root}):
            self.assertEqual(usbwriter._system_tool("WindowsPowerShell", "v1.0", "powershell.exe"), exe)

    def test_a_missing_tool_falls_back_to_its_name(self):
        with mock.patch.dict(os.environ, {"SystemRoot": tempfile.mkdtemp()}):
            self.assertEqual(usbwriter._system_tool("diskpart.exe"), "diskpart.exe")

    def test_the_letter_check_rejects_anything_but_a_to_z(self):
        import inspect
        src = inspect.getsource(usbwriter.write)
        self.assertIn("'^[A-Za-z]$'", src)
        self.assertIn("-lt 5 -and -not $letter;", src)
        self.assertNotIn("-and -not $letter.Trim();", src)


class RawWriteFallback(unittest.TestCase):
    def run_write(self, err):
        calls = []
        from p1401 import rawdisk
        def wipe(*a, **k):
            raise rawdisk.DiskError(f"could not write to the stick (Windows error {err}). help")
        with mock.patch.object(usbwriter, "eligible", lambda d, allow_large=False: (True, [])), \
             mock.patch("p1401.validate.validate", lambda d: {"ok": True}), \
             mock.patch.object(usbwriter, "_ps", lambda s: calls.append("ps") or ""), \
             mock.patch.object(rawdisk, "wipe_mbr_fat32", wipe), \
             mock.patch.object(usbwriter, "_free_letter", lambda: "Q"), \
             mock.patch.object(usbwriter, "release", lambda n: calls.append("release")), \
             mock.patch.object(usbwriter, "_diskpart", lambda s: calls.append("diskpart")):
            try:
                usbwriter.write(PICK, tempfile.mkdtemp(), {})
            except Exception as e:  # noqa: BLE001 - the root never appears in a test; what ran before it is the point
                return calls, e
        return calls, None

    def test_a_stick_refusing_raw_writes_is_erased_with_diskpart(self):
        calls, _ = self.run_write(5)
        self.assertIn("diskpart", calls)

    def test_any_other_raw_write_error_still_stops(self):
        from p1401 import rawdisk
        calls, e = self.run_write(1)
        self.assertNotIn("diskpart", calls)
        self.assertIsInstance(e, rawdisk.DiskError)


class PartitionNotShown(unittest.TestCase):
    def test_a_partition_windows_never_showed_gets_a_diskpart_erase_and_a_second_look(self):
        calls, n = [], {"ps": 0}
        from p1401 import rawdisk
        def ps(script):
            n["ps"] += 1
            if "did not show its new partition" in script and n["ps"] == 2:
                raise usbwriter.UsbError("1401: the stick was erased but Windows did not show its new partition. Unplug")
            calls.append("ps")
            return ""
        with mock.patch.object(usbwriter, "eligible", lambda d, allow_large=False: (True, [])), \
             mock.patch("p1401.validate.validate", lambda d: {"ok": True}), \
             mock.patch.object(usbwriter, "_ps", ps), mock.patch.object(rawdisk, "wipe_mbr_fat32", lambda *a, **k: None), \
             mock.patch.object(usbwriter, "_free_letter", lambda: "Q"), \
             mock.patch.object(usbwriter, "release", lambda x: calls.append("release")), \
             mock.patch.object(usbwriter, "_diskpart", lambda x: calls.append("diskpart")), \
             mock.patch.object(usbwriter.os.path, "isdir", lambda p: False), mock.patch.object(usbwriter.time, "sleep", lambda s: None):
            with self.assertRaises(usbwriter.UsbError):  # the drive root never appears in a test
                usbwriter.write(PICK, tempfile.mkdtemp(), {})
        self.assertEqual(calls[-3:], ["release", "diskpart", "ps"])

    def test_after_diskpart_the_letter_it_assigned_is_used_without_searching_again(self):
        calls, n = [], {"ps": 0}
        from p1401 import rawdisk
        def ps(script):
            n["ps"] += 1
            if "did not show its new partition" in script:
                # the stick that is never found by the search, before or after diskpart
                raise usbwriter.UsbError("1401: the stick was erased but Windows did not show its new partition. Unplug")
            calls.append("ps")
            return ""
        made = {"diskpart": False}
        def dp(script):
            made["diskpart"] = True
            calls.append("diskpart")
        with mock.patch.object(usbwriter, "eligible", lambda d, allow_large=False: (True, [])), \
             mock.patch("p1401.validate.validate", lambda d: {"ok": True}), \
             mock.patch.object(usbwriter, "_ps", ps), mock.patch.object(rawdisk, "wipe_mbr_fat32", lambda *a, **k: None), \
             mock.patch.object(usbwriter, "_free_letter", lambda: "Q"), \
             mock.patch.object(usbwriter, "release", lambda x: calls.append("release")), \
             mock.patch.object(usbwriter, "_diskpart", dp), \
             mock.patch.object(usbwriter.os.path, "isdir", lambda p: made["diskpart"] and p.startswith("Q:")), \
             mock.patch.object(usbwriter.time, "sleep", lambda s: None):
            try:
                usbwriter.write(PICK, tempfile.mkdtemp(), {})
            except usbwriter.UsbError as e:
                self.assertNotIn("did not show its new partition", str(e))
            except Exception:  # noqa: BLE001 - later stages (the Apple download) are not part of this test
                pass
        self.assertEqual(calls[-2:], ["release", "diskpart"])


if __name__ == "__main__":
    unittest.main()
