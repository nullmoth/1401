"""The stick's driver package falls back to the site's copy only when GitHub fails, and a mirror file is checked against
the pinned SHA-256 exactly as a GitHub one is: a wrong byte is refused and nothing is written to the stick."""
import hashlib
import os
import tempfile
import unittest

from p1401 import nullmoth

GH = "https://github.com/nullmoth/nvidia-macos-driver/releases/download/"


class MirrorAddress(unittest.TestCase):
    def test_release_file_maps_to_the_site(self):
        self.assertEqual(nullmoth.mirror_of(GH + "v2.8/nullmoth-nvidia-2.8.tar.gz"),
                         "https://nullmothsystems.com/download/nvidia/v2.8/nullmoth-nvidia-2.8.tar.gz")

    def test_everything_else_has_no_mirror(self):
        for url in ("https://github.com/nullmoth/1401/releases/download/v2.8/x.zip",
                    "https://example.com/nullmoth/nvidia-macos-driver/releases/download/v2.8/x.tar.gz",
                    "http://github.com/nullmoth/nvidia-macos-driver/releases/download/v2.8/x.tar.gz",
                    GH + "v2.8/../../x", GH + "v2.8/a/b", GH + "latest/x", GH + "v2.8/.hidden", "", None):
            self.assertIsNone(nullmoth.mirror_of(url), url)


class Stage(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.cache, self.usb = os.path.join(self.t.name, "cache"), os.path.join(self.t.name, "usb")
        os.makedirs(self.cache)
        os.makedirs(self.usb)
        self.good = b"the driver package bytes"
        self.saved = dict(nullmoth.PACKAGE)
        nullmoth.PACKAGE.update(name="nullmoth-nvidia-2.8.tar.gz", url=GH + "v2.8/nullmoth-nvidia-2.8.tar.gz",
                                sha256=hashlib.sha256(self.good).hexdigest())
        self.calls = []

    def tearDown(self):
        nullmoth.PACKAGE.clear()
        nullmoth.PACKAGE.update(self.saved)
        self.t.cleanup()

    def fetcher(self, github_ok, mirror_bytes):
        def fetch(url, path):
            self.calls.append(url)
            if url.startswith("https://github.com/"):
                if not github_ok:
                    raise OSError("HTTP Error 504: Gateway Timeout")
                data = self.good
            else:
                data = mirror_bytes
            with open(path, "wb") as fh:
                fh.write(data)
        return fetch

    def staged(self):
        p = os.path.join(self.usb, "NullMoth", nullmoth.PACKAGE["name"])
        return open(p, "rb").read() if os.path.exists(p) else None

    def test_github_working_never_touches_the_mirror(self):
        nullmoth.stage(self.usb, self.cache, fetch=self.fetcher(True, b"unused"))
        self.assertEqual(self.calls, [nullmoth.PACKAGE["url"]])
        self.assertEqual(self.staged(), self.good)

    def test_github_down_uses_the_mirror_copy(self):
        nullmoth.stage(self.usb, self.cache, fetch=self.fetcher(False, self.good))
        self.assertEqual(self.calls, [nullmoth.PACKAGE["url"], nullmoth.mirror_of(nullmoth.PACKAGE["url"])])
        self.assertEqual(self.staged(), self.good)

    def test_a_tampered_mirror_file_is_refused_and_nothing_is_staged(self):
        with self.assertRaises(RuntimeError):
            nullmoth.stage(self.usb, self.cache, fetch=self.fetcher(False, b"the driver package bytez"))
        self.assertIsNone(self.staged())
        self.assertFalse(os.path.exists(os.path.join(self.cache, nullmoth.PACKAGE["name"])))


if __name__ == "__main__":
    unittest.main()
