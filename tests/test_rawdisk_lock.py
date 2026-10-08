"""Volume lock before erasing the stick: retry, then a forced dismount, then lock again. No disk is touched."""
import unittest
from unittest.mock import patch

from p1401 import rawdisk


class Lock(unittest.TestCase):
    def run_lock(self, locks_after):
        calls = []

        def ioctl(k, h, code, inbuf=b"", outsize=0):
            calls.append(code)
            locks = calls.count(rawdisk.FSCTL_LOCK_VOLUME)
            return (code == rawdisk.FSCTL_LOCK_VOLUME and locks_after is not None and locks >= locks_after), b"", 0
        with patch.object(rawdisk, "_ioctl", ioctl):
            got = rawdisk._lock_volume(None, None, sleep=lambda s: None)
        return got, calls

    def test_a_free_volume_locks_without_a_dismount(self):
        got, calls = self.run_lock(1)
        self.assertTrue(got)
        self.assertNotIn(rawdisk.FSCTL_DISMOUNT_VOLUME, calls)

    def test_a_held_volume_locks_after_the_forced_dismount(self):
        got, calls = self.run_lock(41)
        self.assertTrue(got)
        self.assertEqual(calls.count(rawdisk.FSCTL_DISMOUNT_VOLUME), 1)
        self.assertLess(calls.index(rawdisk.FSCTL_DISMOUNT_VOLUME), len(calls) - 1)

    def test_negative_control_a_volume_that_never_locks_still_stops(self):
        got, calls = self.run_lock(None)
        self.assertFalse(got)
        self.assertEqual(calls.count(rawdisk.FSCTL_LOCK_VOLUME), 60)


if __name__ == "__main__":
    unittest.main()
