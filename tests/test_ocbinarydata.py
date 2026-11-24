"""A build continues without OcBinaryData when GitHub cannot deliver it: HFS+ comes from OpenCore's own driver, a
build that needs apfs_aligned.efi stops with a network message, and OpenCore is not recorded as fully downloaded."""
import os
import plistlib
import tempfile
import unittest
import zipfile

from p1401 import ocbinarydata


def driver(path, enabled=True):
    return {"Arguments": "", "Comment": "", "Enabled": enabled, "LoadEarly": False, "Path": path}


class Fetcher:
    def __init__(self, ok):
        self.ok, self.asked = ok, []

    def download_and_save_file(self, url, path, sha256_hash=None):
        self.asked.append(url)
        if self.ok == "raise":
            raise RuntimeError("timed out")
        if self.ok:
            with open(path, "wb") as fh:
                fh.write(b"real")
        return bool(self.ok)


class Gathering:
    def __init__(self):
        self.saved = []

    def _save_download_history(self, history, product_name, product_id, url, sha):
        self.saved.append(product_name)


class Base(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        ocbinarydata.reset()

    def tearDown(self):
        ocbinarydata.reset()
        self.t.cleanup()

    def classes(self, ok):
        f = type("F", (Fetcher,), {})
        g = type("G", (Gathering,), {})
        ocbinarydata.install(f, g)
        return f(ok), g()

    def config(self, drivers):
        p = os.path.join(self.t.name, "config.plist")
        with open(p, "wb") as fh:
            plistlib.dump({"UEFI": {"Drivers": drivers}}, fh)
        return p


class Download(Base):
    def test_a_failed_download_leaves_an_empty_archive_and_the_build_goes_on(self):
        for ok in (False, "raise"):
            ocbinarydata.reset()
            f, _ = self.classes(ok)
            path = os.path.join(self.t.name, "OcBinaryData.zip")
            self.assertTrue(f.download_and_save_file(ocbinarydata.URL, path))
            self.assertTrue(ocbinarydata.missing())
            with zipfile.ZipFile(path) as z:
                self.assertEqual(z.namelist(), ["OcBinaryData-master/"])

    def test_opencore_is_not_recorded_as_complete_when_it_was_missing(self):
        f, g = self.classes(False)
        f.download_and_save_file(ocbinarydata.URL, os.path.join(self.t.name, "o.zip"))
        g._save_download_history({}, "OpenCorePkg", "id", "u", "s")
        g._save_download_history({}, "Lilu", "id", "u", "s")
        self.assertEqual(g.saved, ["Lilu"])

    def test_negative_control_a_working_download_changes_nothing(self):
        f, g = self.classes(True)
        self.assertTrue(f.download_and_save_file(ocbinarydata.URL, os.path.join(self.t.name, "o.zip")))
        self.assertFalse(ocbinarydata.missing())
        g._save_download_history({}, "OpenCorePkg", "id", "u", "s")
        self.assertEqual(g.saved, ["OpenCorePkg"])

    def test_negative_control_other_failed_downloads_still_fail(self):
        f, _ = self.classes(False)
        self.assertFalse(f.download_and_save_file("https://github.com/x/Lilu.zip", os.path.join(self.t.name, "l.zip")))
        self.assertFalse(ocbinarydata.missing())


class Config(Base):
    def test_hfsplus_becomes_the_open_driver(self):
        for name in ocbinarydata.HFS:
            ocbinarydata._state["missing"] = True
            p = self.config([driver(name), driver("OpenRuntime.efi")])
            notices = []
            changes = ocbinarydata.apply(p, notices)
            with open(p, "rb") as fh:
                paths = [d["Path"] for d in plistlib.load(fh)["UEFI"]["Drivers"]]
            self.assertEqual(paths, ["OpenHfsPlus.efi", "OpenRuntime.efi"])
            self.assertEqual(changes[0]["before"], name)
            self.assertTrue(notices)

    def test_a_macos_that_needs_apfs_aligned_stops_with_a_network_message(self):
        ocbinarydata._state["missing"] = True
        p = self.config([driver("HfsPlus.efi"), driver("apfs_aligned.efi")])
        with self.assertRaisesRegex(ocbinarydata.NeedsOcBinaryData, "VPN"):
            ocbinarydata.apply(p, [])

    def test_negative_control_nothing_changes_when_ocbinarydata_arrived(self):
        p = self.config([driver("HfsPlus.efi"), driver("apfs_aligned.efi")])
        with open(p, "rb") as fh:
            before = fh.read()
        self.assertEqual(ocbinarydata.apply(p, []), [])
        with open(p, "rb") as fh:
            self.assertEqual(fh.read(), before)


if __name__ == "__main__":
    unittest.main()
