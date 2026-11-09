"""The full macOS installer path: catalog parse, choice, resumable verified download, xar structure and checksums, the data
partition layout and diskpart text. Synthetic catalogs and a synthetic xar; nothing is downloaded."""
import gzip
import hashlib
import io
import os
import plistlib
import struct
import tempfile
import unittest
import zlib

from p1401 import fullinstaller as f


def make_xar(files, toc_sum=True, corrupt=None):
    """files: {name: bytes}. A real-shaped xar: header, zlib TOC, heap with the TOC checksum first."""
    heap = bytearray(); entries = []
    ck_len = 20
    heap += b"\0" * ck_len
    for i, (name, data) in enumerate(files.items(), 1):
        off = len(heap); heap += data
        d = hashlib.sha1(data).hexdigest()
        entries.append(f'<file id="{i}"><name>{name}</name><type>file</type><data><offset>{off}</offset><length>{len(data)}</length>'
                       f'<size>{len(data)}</size><archived-checksum style="sha1">{d}</archived-checksum></data></file>')
    toc = (f'<?xml version="1.0" encoding="UTF-8"?><xar><toc><checksum style="sha1"><offset>0</offset><size>{ck_len}</size></checksum>'
           + "".join(entries) + "</toc></xar>").encode()
    ctoc = zlib.compress(toc)
    heap[0:ck_len] = hashlib.sha1(ctoc).digest() if toc_sum else b"\1" * ck_len
    head = XAR = b"xar!" + struct.pack(">HHQQI", 28, 1, len(ctoc), len(toc), 1)
    out = bytearray(head + ctoc + heap)
    if corrupt:
        out[-1] ^= 0xFF
    return bytes(out)


PKG_FILES = {"Distribution": b"<installer-gui-script/>", "InstallAssistant.pkg/Payload": os.urandom(5000), "Scripts": os.urandom(777)}

DIST = '''<installer-gui-script><title>macOS Tahoe</title><auxinfo><dict><key>BUILD</key><string>25B78</string>
<key>VERSION</key><string>%s</string></dict></auxinfo></installer-gui-script>'''


def catalog(*entries):
    prods = {}
    for pid, ver, url, size, digest in entries:
        prods[pid] = {"PostDate": "2026-10-01T00:00:00Z", "Distributions": {"English": f"https://x/{pid}.dist"},
                      "Packages": [{"URL": "https://x/other.pkg", "Size": 1}, {"URL": url, "Size": size, **({"Digest": digest} if digest else {})}]}
    prods["noinstaller"] = {"Packages": [{"URL": "https://x/Update.pkg", "Size": 5}]}
    return plistlib.dumps({"Products": prods})


class Catalog(unittest.TestCase):
    def test_installer_products_are_found_with_title_version_build_size_and_digest(self):
        data = gzip.compress(catalog(("001", "26.1", "https://x/001/InstallAssistant.pkg", 18000, "AB" * 20)))
        (p,) = f.parse_catalog(data, {"https://x/001.dist": DIST % "26.1"})
        self.assertEqual((p["title"], p["version"], p["build"], p["size"], p["digest"]), ("macOS Tahoe", "26.1", "25B78", 18000, "ab" * 20))

    def test_the_newest_product_for_the_major_is_chosen(self):
        data = catalog(("a", "26.0", "https://x/a/InstallAssistant.pkg", 1, ""), ("b", "26.1", "https://x/b/InstallAssistant.pkg", 1, ""),
                       ("c", "15.7", "https://x/c/InstallAssistant.pkg", 1, ""), ("d", "26.1.1", "https://x/d/InstallAssistant.pkg", 1, ""))
        dists = {f"https://x/{k}.dist": DIST % v for k, v in (("a", "26.0"), ("b", "26.1"), ("c", "15.7"), ("d", "26.1.1"))}
        prods = f.parse_catalog(data, dists)
        self.assertEqual(f.choose(prods, 26)["product"], "d")
        self.assertEqual(f.choose(prods, 15)["product"], "c")
        self.assertIsNone(f.choose(prods, 14))

    def test_a_non_https_package_and_a_broken_catalog_are_refused(self):
        self.assertEqual(f.parse_catalog(catalog(("a", "26.0", "http://x/a/InstallAssistant.pkg", 1, ""))), [])
        with self.assertRaises(f.FullInstallerError):
            f.parse_catalog(b"not a plist")


class Xar(unittest.TestCase):
    def path(self, data):
        p = os.path.join(tempfile.mkdtemp(), "i.pkg"); open(p, "wb").write(data); return p

    def test_a_good_package_verifies_and_names_its_files(self):
        self.assertEqual(f.verify_xar(self.path(make_xar(PKG_FILES))), sorted(PKG_FILES))

    def test_a_flipped_byte_in_a_file_is_caught(self):
        with self.assertRaises(f.FullInstallerError) as e:
            f.verify_xar(self.path(make_xar(PKG_FILES, corrupt=True)))
        self.assertIn("fails its checksum", str(e.exception))

    def test_a_wrong_table_of_contents_checksum_is_caught(self):
        with self.assertRaises(f.FullInstallerError) as e:
            f.verify_xar(self.path(make_xar(PKG_FILES, toc_sum=False)))
        self.assertIn("table of contents fails", str(e.exception))

    def test_a_cut_short_download_and_a_non_xar_are_caught(self):
        good = make_xar(PKG_FILES)
        with self.assertRaises(f.FullInstallerError):
            f.verify_xar(self.path(good[:-300]))
        with self.assertRaises(f.FullInstallerError) as e:
            f.verify_xar(self.path(b"PK\x03\x04" + b"0" * 100))
        self.assertIn("no xar header", str(e.exception))

    def test_a_table_of_contents_that_declares_entities_is_refused(self):
        toc = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><xar><toc/></xar>'
        c = zlib.compress(toc)
        data = b"xar!" + struct.pack(">HHQQI", 28, 1, len(c), len(toc), 1) + c + b"\0" * 20
        with self.assertRaises(f.FullInstallerError):
            f.verify_xar(self.path(data))


class Fetch(unittest.TestCase):
    def opener(self, blob, drop_after=None):
        calls = []
        def op(url, start):
            calls.append(start)
            part = blob[start:]
            if drop_after and start == 0:
                class S(io.BytesIO):
                    def read(s, n=-1):
                        b = io.BytesIO.read(s, n)
                        if not b: raise OSError("connection reset")
                        return b
                return S(part[:drop_after]), None
            return io.BytesIO(part), None
        op.calls = calls
        return op

    def test_a_dropped_connection_resumes_and_the_package_verifies(self):
        blob = make_xar(PKG_FILES)
        prod = {"url": "https://x/InstallAssistant.pkg", "size": len(blob), "digest": hashlib.sha1(blob).hexdigest()}
        op = self.opener(blob, drop_after=2000)
        d = tempfile.mkdtemp()
        path = f.fetch(prod, d, opener=op)
        self.assertEqual(open(path, "rb").read(), blob)
        self.assertEqual(op.calls[0], 0); self.assertGreater(op.calls[1], 0)
        self.assertFalse(os.path.exists(path + ".part"))

    def test_a_wrong_digest_throws_the_download_away(self):
        blob = make_xar(PKG_FILES)
        d = tempfile.mkdtemp()
        with self.assertRaises(f.FullInstallerError) as e:
            f.fetch({"url": "https://x/InstallAssistant.pkg", "size": len(blob), "digest": "0" * 40}, d, opener=self.opener(blob))
        self.assertIn("digest", str(e.exception))
        self.assertEqual(os.listdir(d), [])

    def test_a_server_that_never_finishes_is_reported_with_the_byte_count(self):
        blob = make_xar(PKG_FILES)
        with self.assertRaises(f.FullInstallerError) as e:
            f.fetch({"url": "https://x/InstallAssistant.pkg", "size": len(blob) + 10, "digest": ""}, tempfile.mkdtemp(),
                    opener=self.opener(blob), tries=3)
        self.assertIn(f"stopped at {len(blob)} of {len(blob) + 10}", str(e.exception))

    def test_only_https_addresses_are_opened(self):
        with self.assertRaises(f.FullInstallerError):
            f._open_range("http://x/a.pkg", 0)


class Stick(unittest.TestCase):
    def test_layout_and_placement_read_back(self):
        blob = make_xar(PKG_FILES)
        src = os.path.join(tempfile.mkdtemp(), "i.pkg"); open(src, "wb").write(blob)
        root = tempfile.mkdtemp()
        names = f.place(root, src, {"title": "macOS Tahoe", "version": "26.1"})
        self.assertEqual(names, sorted([f.SCRIPT_NAME, "README.txt", f.PACKAGE_NAME]))
        self.assertEqual(open(os.path.join(root, f.PACKAGE_NAME), "rb").read(), blob)
        self.assertTrue(open(os.path.join(root, f.SCRIPT_NAME)).read().startswith("#!/bin/bash"))
        self.assertIn("macOS Tahoe 26.1", open(os.path.join(root, "README.txt")).read())

    def test_a_stick_that_loses_data_is_caught(self):
        src = os.path.join(tempfile.mkdtemp(), "i.pkg"); open(src, "wb").write(make_xar(PKG_FILES))
        def bad_copy(s, d, progress=None):
            data = bytearray(open(s, "rb").read()); data[100] ^= 1; open(d, "wb").write(data)
        with self.assertRaises(f.FullInstallerError) as e:
            f.place(tempfile.mkdtemp(), src, {}, copy=bad_copy)
        self.assertIn("reads back different", str(e.exception))

    def test_diskpart_text_makes_one_exfat_partition_and_refuses_odd_input(self):
        t = f.diskpart_script(3, "e", 2048)
        self.assertEqual(t.split("\r\n")[:4], ["select disk 3", "create partition primary", "format fs=exfat label=NMINSTALL quick", "assign letter=E"])
        for args in (("3; clean", "E", 1), (3, "EE", 1), (3, "1", 1)):
            with self.assertRaises(f.FullInstallerError):
                f.diskpart_script(*args)

    def test_a_small_stick_is_refused_with_its_size(self):
        with self.assertRaises(f.FullInstallerError) as e:
            f.check_stick(16 << 30)
        self.assertIn("at least 32 GB", str(e.exception))
        f.check_stick(64 << 30)

    def test_the_helper_script_parses_in_bash(self):
        import subprocess
        p = subprocess.run(["/bin/bash", "-n"], input=f.SCRIPT, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)


if __name__ == "__main__":
    unittest.main()
