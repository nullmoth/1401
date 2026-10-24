"""The Windows package's Python runtime is pinned in windows/release-inputs.json and installed over the baseline by
tools/windows_release.py (10-22): the baseline's CPython 3.12.10 gets no more binary security releases, and its
certifi 2026.7.22 still trusted the emSign CAs whose intermediate keys were compromised (GHSA-6q48-6c7w-9gw2)."""
import hashlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import windows_release  # noqa: E402


def zipped(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


class Pins(unittest.TestCase):
    inputs = json.loads((REPO / "windows/release-inputs.json").read_text())

    def test_every_runtime_file_is_https_and_sha256_pinned(self):
        rt = self.inputs["runtime"]
        for url, digest in [(rt["python_url"], rt["python_sha256"])] + [(w["url"], w["sha256"]) for w in rt["wheels"]]:
            self.assertTrue(url.startswith("https://www.python.org/") or url.startswith("https://files.pythonhosted.org/"), url)
            self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_the_runtime_version_and_the_embed_file_agree(self):
        rt = self.inputs["runtime"]
        self.assertIn(f"/python-{rt['python']}-embed-amd64.zip", rt["python_url"])
        self.assertTrue(all(f"-cp{rt['python'].replace('.', '')[:3]}-" in w["url"] or "none-any" in w["url"]
                            for w in rt["wheels"]), "a compiled wheel is for a different Python")

    def test_certifi_postdates_the_emsign_revocation(self):
        got = tuple(int(x) for x in self.inputs["runtime_packages"]["certifi"].split("."))
        # 2026.10.19 still carried the emSign Root CA - C1 and emSign ECC Root CA - C3; 2026.10.23 is the first without them
        self.assertGreaterEqual(got, (2026, 10, 23))
        self.assertTrue(any(f"certifi-{self.inputs['runtime_packages']['certifi']}-" in w["url"]
                            for w in self.inputs["runtime"]["wheels"]))


class Install(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.files = {
            "https://www.python.org/ftp/python/3.13.9/python-3.13.9-embed-amd64.zip":
                zipped({"python.exe": b"MZ", "python313._pth": "python313.zip\n.\n#import site\n"}),
            "https://files.pythonhosted.org/x/pywin32-312-cp313-cp313-win_amd64.whl":
                zipped({"pywin32_system32/pywintypes313.dll": b"MZ", "pywin32.pth": "win32\n"}),
        }
        self.rt = {"python": "3.13.9", "python_url": next(iter(self.files)),
                   "python_sha256": hashlib.sha256(next(iter(self.files.values()))).hexdigest(),
                   "wheels": [{"url": u, "sha256": hashlib.sha256(b).hexdigest()} for u, b in list(self.files.items())[1:]]}
        (self.root / "python").mkdir()
        (self.root / "python" / "python312.dll").write_bytes(b"old")

    def tearDown(self):
        self.tmp.cleanup()

    def fake_get(self, url):
        return io.BytesIO(self.files[url])

    def install(self):
        with patch.object(windows_release, "get", side_effect=self.fake_get):
            windows_release.install_runtime(self.rt, self.root / "python", self.root / "cache")

    def test_the_baseline_runtime_is_replaced_and_the_search_path_is_1401s(self):
        self.install()
        py = self.root / "python"
        self.assertFalse((py / "python312.dll").exists())
        self.assertEqual((py / "python313._pth").read_text(),
                         "python313.zip\n.\nLib\\site-packages\n..\\app\nimport site\n")
        self.assertTrue((py / "Lib/site-packages/pywin32_system32/pywintypes313.dll").is_file())
        site = (py / "Lib/site-packages/sitecustomize.py").read_text()
        self.assertIn('"%d%d" % _sys.version_info[:2]', site)
        self.assertNotIn("pywintypes312.dll", site)

    def test_a_file_that_differs_from_its_pin_stops_the_build(self):
        self.rt["wheels"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
            self.install()

    def test_an_archive_member_that_escapes_the_folder_stops_the_build(self):
        bad = zipped({"../evil.dll": b"MZ"})
        url = self.rt["wheels"][0]["url"]
        self.files[url] = bad
        self.rt["wheels"][0]["sha256"] = hashlib.sha256(bad).hexdigest()
        with self.assertRaisesRegex(RuntimeError, "Unsafe wheel ZIP member"):
            self.install()
        self.assertFalse((self.root / "evil.dll").exists())


class PackagedTexts(unittest.TestCase):
    """The packaged NOTICE.md was the 1.14.3 baseline's (3.7 KB) in every release since: the credits added later never
    reached Windows users. The build copies this release's NOTICE.md and LICENSE, and the window links to it."""

    def test_the_build_copies_this_releases_notice_and_licence(self):
        src = (REPO / "tools/windows_release.py").read_text()
        prep = src.split("def prepare(", 1)[1]
        self.assertIn("for name in ('NOTICE.md', 'LICENSE'):", prep)
        self.assertIn("shutil.copyfile(REPO / name, app / name)", prep)
        self.assertLess(prep.index("extract_baseline("), prep.index("for name in ('NOTICE.md', 'LICENSE'):"))

    def test_the_window_opens_the_packaged_credits(self):
        form = (REPO / "windows/App/MainForm.cs").read_text()
        self.assertIn('creditsLink.Text = Loc.T("Credits")', form)
        self.assertIn('Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "engine", "app", "NOTICE.md")', form)
        self.assertIn("creditsLink, drvLink", form)


if __name__ == "__main__":
    unittest.main()
