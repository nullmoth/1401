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


class Write(unittest.TestCase):
    """The raw erase: partition table dropped before the zero writes; a refused write takes the disk offline and is
    tried once more; a stick that refuses even then stops with what to do. Fake kernel32, no disk."""
    def run_wipe(self, refuse_until_offline, refuse_always=False):
        log = []
        state = {"offline": False}

        def ioctl(k, h, code, inbuf=b"", outsize=0):
            log.append(("ioctl", code))
            if code == rawdisk.IOCTL_DISK_SET_DISK_ATTRIBUTES:
                state["offline"] = bool(inbuf[8])
            return True, b"", 0

        def write_at(k, h, off, data):
            log.append(("write", off))
            if refuse_always or (refuse_until_offline and not state["offline"]):
                return 1
            return 0
        with patch.object(rawdisk, "_k32", lambda: type("K", (), {"CloseHandle": lambda *a: None})()), \
                patch.object(rawdisk, "_volumes_on", lambda k, d: []), patch.object(rawdisk, "_open", lambda k, p: 7), \
                patch.object(rawdisk, "_ioctl", ioctl), patch.object(rawdisk, "_write_at", write_at):
            said = []
            try:
                rawdisk.wipe_mbr_fat32(3, 16 << 30, 1 << 30, say=said.append)
                return None, log, said, state
            except rawdisk.DiskError as e:
                return str(e), log, said, state

    def test_partition_table_goes_before_the_first_write(self):
        err, log, _, _ = self.run_wipe(False)
        self.assertIsNone(err)
        first_write = next(i for i, x in enumerate(log) if x[0] == "write")
        self.assertIn(("ioctl", rawdisk.IOCTL_DISK_DELETE_DRIVE_LAYOUT), log[:first_write])

    def test_a_refused_write_is_retried_once_with_the_disk_offline(self):
        err, log, said, state = self.run_wipe(True)
        self.assertIsNone(err, err)
        self.assertTrue(any("took the stick offline" in s for s in said))
        self.assertFalse(state["offline"], "the disk must be back online afterwards")

    def test_negative_control_a_stick_that_always_refuses_stops_with_the_fix(self):
        err, log, _, _ = self.run_wipe(False, refuse_always=True)
        self.assertIn("Windows error 1", err)
        self.assertIn("Use another USB stick", err)
        self.assertEqual(sum(1 for x in log if x[0] == "write"), 2, "one write and exactly one retry")


if __name__ == "__main__":
    unittest.main()
