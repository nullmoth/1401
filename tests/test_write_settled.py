"""A stick that re-mounts under the open recovery image does not end the download (1.5.0 log 10-10: PermissionError
[Errno 13] on the image write right after Windows took the stick offline and back)."""
import os
import tempfile
import unittest

from p1401 import apple


class Flaky:
    def __init__(self, real):
        self.real = real

    def write(self, b):
        self.real.close()
        raise PermissionError(13, "Permission denied")

    def close(self):
        self.real.close()


class WriteSettled(unittest.TestCase):
    def test_a_write_refused_once_lands_at_the_same_offset_after_reopening(self):
        path = os.path.join(tempfile.mkdtemp(), "BaseSystem.dmg.part")
        with open(path, "wb") as f:
            f.write(b"A" * 10)
        fh = apple._write_settled(Flaky(open(path, "r+b")), path, 10, b"B" * 5, sleep=lambda s: None)
        fh.close()
        self.assertEqual(open(path, "rb").read(), b"A" * 10 + b"B" * 5)

    def test_a_stick_that_never_comes_back_still_fails_loudly(self):
        path = os.path.join(tempfile.mkdtemp(), "gone.part")
        with self.assertRaises(OSError):
            apple._write_settled(apple._Broken(), path, 0, b"x", tries=3, sleep=lambda s: None)


if __name__ == "__main__":
    unittest.main()
