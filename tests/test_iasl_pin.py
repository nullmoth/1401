"""Windows iasl is the pinned ACPICA release: the engine's link is replaced, the download is hash-checked, and an
iasl.exe that is not the pinned build is removed before the engine looks for one."""
import os
import tempfile
import unittest

from p1401 import iasl_pin


def make_dsdt_class(folder, log):
    class Fetcher:
        def download_and_save_file(self, url, path, sha256_hash=None):
            log.append((url, sha256_hash))
            return True

    def check_iasl(self, legacy=False, try_downloading=True):
        exe = os.path.join(folder, "iasl.exe")
        log.append(("check", os.path.exists(exe)))
        return exe if os.path.exists(exe) else None

    def _download_and_extract(self, temp, url):
        self.fetcher.download_and_save_file(url, os.path.join(temp, os.path.basename(url)))

    cls = type("DSDT", (), {"get_latest_iasl": lambda self: "https://github.com/open-acpica/acpica/releases/download/"
                                                          "20251212/iasl-win-20251212.zip",
                            "check_iasl": check_iasl, "_download_and_extract": _download_and_extract})
    cls.fetcher = Fetcher()
    return cls


class Pin(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.log = []
        self.cls = make_dsdt_class(self.t.name, self.log)
        # check_iasl looks beside the module that defines the engine's check_iasl; here that is this test's folder
        self.exe = os.path.join(os.path.dirname(os.path.realpath(__file__)), "iasl.exe")

    def tearDown(self):
        if os.path.exists(self.exe):
            os.remove(self.exe)
        self.t.cleanup()

    def test_the_engine_asks_for_the_pinned_release(self):
        iasl_pin.install(self.cls, "win32")
        self.assertEqual(self.cls().get_latest_iasl(), iasl_pin.URL)
        self.assertIn("20260408", iasl_pin.URL)

    def test_the_pinned_download_is_hash_checked(self):
        iasl_pin.install(self.cls, "win32")
        self.cls()._download_and_extract(self.t.name, iasl_pin.URL)
        self.assertEqual(self.log[-1], (iasl_pin.URL, iasl_pin.ZIP_SHA256))

    def test_negative_control_other_downloads_keep_their_own_hash(self):
        iasl_pin.install(self.cls, "win32")
        self.cls()._download_and_extract(self.t.name, "https://example.com/other.zip")
        self.assertEqual(self.log[-1], ("https://example.com/other.zip", None))

    def test_a_stale_iasl_is_removed_before_the_engine_looks(self):
        with open(self.exe, "wb") as fh:
            fh.write(b"the 20251212 build")
        iasl_pin.install(self.cls, "win32")
        self.cls().check_iasl()
        self.assertFalse(os.path.exists(self.exe))

    def test_negative_control_off_windows_nothing_is_removed(self):
        with open(self.exe, "wb") as fh:
            fh.write(b"some iasl")
        iasl_pin.install(self.cls, "darwin")
        self.cls().check_iasl()
        self.assertTrue(os.path.exists(self.exe))

    def test_stale_is_false_for_the_pinned_build_and_a_missing_file(self):
        self.assertFalse(iasl_pin.stale(os.path.join(self.t.name, "absent.exe")))
        p = os.path.join(self.t.name, "x.exe")
        with open(p, "wb") as fh:
            fh.write(b"x")
        self.assertTrue(iasl_pin.stale(p))


if __name__ == "__main__":
    unittest.main()
