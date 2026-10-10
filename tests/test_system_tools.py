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


if __name__ == "__main__":
    unittest.main()
