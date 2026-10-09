"""EFI copy onto a fresh stick: a volume that blinks out once is retried; one that stays gone still stops."""
import unittest
from unittest.mock import patch

from p1401 import usbwriter


class CopySettled(unittest.TestCase):
    def run_copy(self, failures):
        calls = []

        def copytree(src, dst, dirs_exist_ok=False):
            calls.append(dirs_exist_ok)
            if len(calls) <= failures:
                raise OSError(21, "The device is not ready")
        with patch.object(usbwriter.shutil, "copytree", copytree), patch.object(usbwriter.os.path, "isdir", lambda p: True):
            try:
                usbwriter._copy_settled("src", "dst", "Z:\\", tries=4, sleep=lambda s: None)
                return None, calls
            except OSError as e:
                return e, calls

    def test_a_volume_that_blinks_once_is_copied_on_the_retry(self):
        err, calls = self.run_copy(1)
        self.assertIsNone(err)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(calls), "a retry must merge into what the first try copied")

    def test_negative_control_a_volume_that_stays_gone_still_stops(self):
        err, calls = self.run_copy(99)
        self.assertIsInstance(err, OSError)
        self.assertEqual(len(calls), 4)


if __name__ == "__main__":
    unittest.main()
