"""The stick carries NVIDIA's driver package (the source of the GPU firmware, which NullMoth no longer ships) so the Mac
installer works without internet; a wrong file never reaches the stick, and failing to fetch it never fails the write."""
import hashlib
import os
import tempfile
import unittest

from p1401 import nullmoth


class StageFirmware(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.cache, self.usb = os.path.join(self.t.name, "cache"), os.path.join(self.t.name, "usb")
        os.makedirs(self.cache)
        os.makedirs(self.usb)
        self.good = b"nvidia driver package bytes" * 100
        self.saved = dict(nullmoth.FIRMWARE_RUN)
        nullmoth.FIRMWARE_RUN.update(sha256=hashlib.sha256(self.good).hexdigest())
        self.calls = []

    def tearDown(self):
        nullmoth.FIRMWARE_RUN.clear()
        nullmoth.FIRMWARE_RUN.update(self.saved)
        self.t.cleanup()

    def fetcher(self, data):
        def fetch(url, path):
            self.calls.append(url)
            with open(path, "wb") as fh:
                fh.write(data)
        return fetch

    def on_stick(self):
        p = os.path.join(self.usb, "NullMoth", nullmoth.FIRMWARE_RUN["name"])
        return open(p, "rb").read() if os.path.exists(p) else None

    def test_a_download_that_matches_its_pin_is_copied_to_the_stick(self):
        dst = nullmoth.stage_firmware(self.usb, self.cache, fetch=self.fetcher(self.good))
        self.assertEqual(self.calls, [nullmoth.FIRMWARE_RUN["url"]])
        self.assertEqual(self.on_stick(), self.good)
        self.assertTrue(dst.endswith(nullmoth.FIRMWARE_RUN["name"]))

    def test_the_download_comes_from_nvidia_and_nowhere_else(self):
        self.assertTrue(nullmoth.FIRMWARE_RUN["url"].startswith("https://download.nvidia.com/XFree86/Linux-x86_64/"))

    def test_a_cached_copy_that_matches_is_not_downloaded_again(self):
        with open(os.path.join(self.cache, nullmoth.FIRMWARE_RUN["name"]), "wb") as fh:
            fh.write(self.good)
        nullmoth.stage_firmware(self.usb, self.cache, fetch=self.fetcher(b"never used"))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.on_stick(), self.good)

    def test_a_download_that_differs_by_one_byte_never_reaches_the_stick(self):
        got = nullmoth.stage_firmware(self.usb, self.cache, fetch=self.fetcher(self.good[:-1] + b"X"))
        self.assertIsNone(got)
        self.assertIsNone(self.on_stick())
        self.assertFalse(os.path.exists(os.path.join(self.cache, nullmoth.FIRMWARE_RUN["name"])))

    def test_a_failed_download_does_not_fail_the_write(self):
        def down(url, path):
            raise OSError("no network")
        self.assertIsNone(nullmoth.stage_firmware(self.usb, self.cache, fetch=down))
        self.assertIsNone(self.on_stick())

    def test_the_pin_matches_the_driver_installer_when_the_driver_tree_is_known(self):
        drv = os.environ.get("NULLMOTH_DRIVER")
        f = os.path.join(drv or "", "package", "fw_fetch.sh")
        if not os.path.isfile(f):
            self.skipTest("NULLMOTH_DRIVER not set")
        src = open(f).read()
        self.assertIn("SHA_RUN=" + self.saved["sha256"], src)
        self.assertIn(self.saved["name"].replace("620.70.06", "$VER"), src)


if __name__ == "__main__":
    unittest.main()
