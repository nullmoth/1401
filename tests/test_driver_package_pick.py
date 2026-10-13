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


class Ranged(io.BytesIO):
    def __init__(self, body, start, total):
        super().__init__(body)
        self.headers = {"Content-Range": f"bytes {start}-{start + len(body) - 1}/{total}", "Content-Length": str(len(body))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ranges(req):
    return req.headers.get("Range") if hasattr(req, "headers") else None


class ShortDownload(unittest.TestCase):
    def run_fetch(self, bodies, tries=8):
        seen = []
        path = os.path.join(tempfile.mkdtemp(), "pkg.part")

        def opener(req, timeout=60):
            seen.append(_ranges(req))
            b = bodies.pop(0)
            if isinstance(b, Exception):
                raise b
            return b
        with mock.patch("urllib.request.urlopen", opener), mock.patch.object(usbwriter.time, "sleep", lambda s: None):
            usbwriter._fetch("https://example.invalid/pkg", path, tries=tries)
        return open(path, "rb").read(), seen

    def test_a_short_body_is_resumed_from_where_it_stopped(self):
        data, seen = self.run_fetch([Resp(b"abc", 10), Ranged(b"3456789", 3, 10)])
        self.assertEqual(data, b"abc3456789")
        self.assertEqual(seen, [None, "bytes=3-"])

    def test_a_dropped_connection_is_resumed(self):
        import http.client
        data, seen = self.run_fetch([Resp(b"0123", 10), http.client.RemoteDisconnected("gone"), Ranged(b"456789", 4, 10)])
        self.assertEqual(data, b"0123456789")
        self.assertEqual(seen[-1], "bytes=4-")

    def test_a_server_that_ignores_the_range_starts_over(self):
        data, _ = self.run_fetch([Resp(b"abc", 10), Resp(b"0123456789", 10)])
        self.assertEqual(data, b"0123456789")

    def test_a_body_that_stays_short_is_an_error_not_a_success(self):
        with self.assertRaises(OSError):
            self.run_fetch([Resp(b"abc", 10), Resp(b"abc", 10), Resp(b"abc", 10)], tries=3)


if __name__ == "__main__":
    unittest.main()
