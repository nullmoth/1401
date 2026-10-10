"""The stick gets the driver package this build pins, not an older one left in the same folder, and a driver download
cut short is fetched again instead of failing the write (10-10: a 1.8 app passed the 1.7 package, the stick went to the
network, and the download came back short)."""
import io
import os
import tempfile
import unittest
from unittest import mock

from p1401 import nullmoth, usbwriter


class PinnedPackage(unittest.TestCase):
    def test_the_pinned_version_beside_an_older_one_is_used(self):
        d = tempfile.mkdtemp()
        old = os.path.join(d, "nullmoth-nvidia-1.7.0.tar.gz")
        for name in ("nullmoth-nvidia-1.7.0.tar.gz", nullmoth.PACKAGE["name"]):
            open(os.path.join(d, name), "wb").close()
        self.assertEqual(os.path.basename(usbwriter._pinned_package(old)), nullmoth.PACKAGE["name"])

    def test_without_the_pinned_file_the_passed_one_is_kept(self):
        d = tempfile.mkdtemp()
        old = os.path.join(d, "nullmoth-nvidia-1.7.0.tar.gz")
        open(old, "wb").close()
        self.assertEqual(usbwriter._pinned_package(old), old)


class Resp(io.BytesIO):
    def __init__(self, body, length):
        super().__init__(body)
        self.headers = {"Content-Length": str(length)}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class ShortDownload(unittest.TestCase):
    def test_a_short_body_is_downloaded_again(self):
        bodies = [Resp(b"abc", 10), Resp(b"0123456789", 10)]
        path = os.path.join(tempfile.mkdtemp(), "pkg.part")
        with mock.patch("urllib.request.urlopen", lambda url, timeout=60: bodies.pop(0)), \
             mock.patch.object(usbwriter.time, "sleep", lambda s: None):
            usbwriter._fetch("https://example.invalid/pkg", path)
        self.assertEqual(open(path, "rb").read(), b"0123456789")


if __name__ == "__main__":
    unittest.main()
