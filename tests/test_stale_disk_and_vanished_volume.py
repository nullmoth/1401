"""Two 2.0.2 write failures that were not the stick: a disk number Windows had already reassigned (the write stopped
before touching anything and told the user the stick was faulty), and a volume that went away between being listed and
being opened for the lock ("cannot open \\\\?\\Volume{...} (Windows error 2)")."""
import unittest
from unittest.mock import patch

from p1401 import rawdisk, usbwriter


class StaleNumber(unittest.TestCase):
    def test_a_reassigned_number_says_so_and_does_not_blame_the_stick(self):
        with patch.object(usbwriter, "list_disks", return_value=[{"Number": 3, "BusType": "USB", "Size": 16 * 10**9}]), \
             patch("builtins.print") as out:
            rc = usbwriter.cli_write(["2", "efi", "24"])
        line = " ".join(str(c.args[0]) for c in out.call_args_list if c.args)
        self.assertEqual(rc, 1)
        self.assertIn("1401-DISK-RENUMBERED", line)
        self.assertNotIn(usbwriter.STICK_ADVICE.strip()[:40], line)
        self.assertIn("USB: 3: ? 14.9 GiB", line)   # the log names where the stick went (2.0.3 logs could not)

    def test_the_window_reloads_its_list_on_that_stop(self):
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[1] / "windows/App/MainForm.cs").read_text()
        self.assertIn('l.Contains("1401-DISK-RENUMBERED"))) FillDisks();', src)


class VanishedVolume(unittest.TestCase):
    def run_wipe(self, vol_error):
        said = []

        def opener(k, p):
            if p.startswith("\\\\?\\Volume"):
                raise rawdisk.DiskError(f"cannot open {p} ({vol_error})")
            return 7
        with patch.object(rawdisk, "_k32", lambda: type("K", (), {"CloseHandle": lambda *a: None})()), \
             patch.object(rawdisk, "_volumes_on", lambda k, d: ["\\\\?\\Volume{6cff5f1e}"]), \
             patch.object(rawdisk, "_open", opener), patch.object(rawdisk, "_lock_volume", lambda k, h: True), \
             patch.object(rawdisk, "_ioctl", lambda k, h, code, inbuf=b"", outsize=0: (True, b"", 0)), \
             patch.object(rawdisk, "_write_at", lambda k, h, off, data: 0):
            rawdisk.wipe_mbr_fat32(3, 16 << 30, 1 << 30, say=said.append)
        return said

    def test_a_volume_that_went_away_is_skipped_and_the_erase_goes_on(self):
        said = self.run_wipe("Windows error 2")
        self.assertTrue(any("went away" in s for s in said), said)

    def test_any_other_open_error_still_stops(self):
        with self.assertRaises(rawdisk.DiskError):
            self.run_wipe("Windows error 5")


if __name__ == "__main__":
    unittest.main()
