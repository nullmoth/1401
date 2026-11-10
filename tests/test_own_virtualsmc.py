"""The VirtualSMC set NullMoth builds from source replaces the downloaded release in the EFI, all or nothing.

Set VIRTUALSMC_ZIP=<the built VirtualSMC-*-nm29.zip> to also run the swap on the real package (vendor/smcsuperio/build.sh)."""
import sys
import hashlib
import io
import json
import os
import pathlib
import tempfile
import unittest
import zipfile
from unittest import mock

from p1401 import licenses, own_virtualsmc

ROOT = pathlib.Path(__file__).resolve().parents[1]


def package(kexts=own_virtualsmc.KEXTS, tamper=None, extra=None):
    """A package laid out like the real one: Kexts/<k>.kext/Contents/MacOS/<k> + SHA256SUMS."""
    buf, sums = io.BytesIO(), []
    with zipfile.ZipFile(buf, "w") as z:
        for k in kexts:
            body = f"ours {k}".encode()
            z.writestr(f"Kexts/{k}.kext/Contents/MacOS/{k}", body if k != tamper else b"changed")
            z.writestr(f"Kexts/{k}.kext/Contents/Info.plist", "<plist/>")
            sums.append(f"{hashlib.sha256(body).hexdigest()}  {k}.kext")
        z.writestr("SHA256SUMS", "\n".join(sums) + "\n")
        if extra:
            z.writestr(extra, b"x")
    data = buf.getvalue()
    return data, {"version": "t", "url": "https://nullmothsystems.com/mirror/x", "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def efi(root, names):
    k = pathlib.Path(root, "EFI", "OC", "Kexts")
    for n in names:
        (k / f"{n}.kext" / "Contents" / "MacOS").mkdir(parents=True)
        (k / f"{n}.kext" / "Contents" / "MacOS" / n).write_bytes(b"downloaded")
    return k


def body(kdir, n):
    return (kdir / f"{n}.kext" / "Contents" / "MacOS" / n).read_bytes()


class Swap(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.addCleanup(self.t.cleanup)

    def run_swap(self, data, pin, names=("VirtualSMC", "SMCProcessor", "SMCSuperIO")):
        kdir = efi(self.t.name, names)
        notices = []
        with mock.patch.object(own_virtualsmc, "PACKAGE", pin):
            got = own_virtualsmc.replace(self.t.name, notices, fetch=lambda url: data)
        return kdir, got, notices

    def test_every_kext_of_the_set_in_the_efi_is_replaced(self):
        data, pin = package()
        kdir, got, notices = self.run_swap(data, pin)
        self.assertEqual(got, ["VirtualSMC", "SMCProcessor", "SMCSuperIO"])
        for n in got:
            self.assertEqual(body(kdir, n), f"ours {n}".encode())
        self.assertFalse((kdir / ".nullmoth-virtualsmc").exists())
        self.assertIn("built by NullMoth", notices[-1])

    def test_a_package_that_does_not_match_its_pin_changes_nothing(self):
        data, pin = package()
        kdir, got, notices = self.run_swap(data + b"!", pin)
        self.assertEqual(got, [])
        self.assertEqual(body(kdir, "SMCSuperIO"), b"downloaded")
        self.assertIn("kept the downloaded VirtualSMC release", notices[-1])

    def test_one_bad_kext_keeps_the_whole_downloaded_set(self):
        data, pin = package(tamper="SMCSuperIO")
        kdir, got, _ = self.run_swap(data, pin)
        self.assertEqual(got, [])
        self.assertEqual([body(kdir, n) for n in ("VirtualSMC", "SMCProcessor", "SMCSuperIO")], [b"downloaded"] * 3)

    def test_a_package_missing_a_kext_the_efi_has_changes_nothing(self):
        data, pin = package(kexts=("VirtualSMC", "SMCProcessor"))
        kdir, got, _ = self.run_swap(data, pin)
        self.assertEqual(got, [])
        self.assertEqual(body(kdir, "VirtualSMC"), b"downloaded")

    def test_a_path_outside_the_package_is_refused(self):
        data, pin = package(extra="../escape")
        kdir, got, _ = self.run_swap(data, pin)
        self.assertEqual(got, [])
        self.assertFalse(pathlib.Path(self.t.name, "EFI", "OC", "escape").exists())

    def test_an_efi_without_virtualsmc_is_left_alone(self):
        data, pin = package()
        kdir, got, notices = self.run_swap(data, pin, names=("Lilu",))
        self.assertEqual((got, notices), ([], []))

    def test_no_network_keeps_the_download_and_says_so(self):
        kdir = efi(self.t.name, ("VirtualSMC",))
        notices = []
        def offline(url):
            raise OSError("unreachable")
        self.assertEqual(own_virtualsmc.replace(self.t.name, notices, fetch=offline), [])
        self.assertEqual(body(kdir, "VirtualSMC"), b"downloaded")
        self.assertIn("OSError", notices[-1])

    @unittest.skipUnless(os.environ.get("VIRTUALSMC_ZIP"), "set VIRTUALSMC_ZIP to the built package")
    def test_the_real_package_matches_its_pin_and_swaps_in(self):
        data = pathlib.Path(os.environ["VIRTUALSMC_ZIP"]).read_bytes()
        kdir = efi(self.t.name, own_virtualsmc.KEXTS)
        notices = []
        got = own_virtualsmc.replace(self.t.name, notices, fetch=lambda url: data)
        self.assertEqual(got, list(own_virtualsmc.KEXTS), notices)
        self.assertIn(b"ITE IT8696E", body(kdir, "SMCSuperIO"))


class Pins(unittest.TestCase):
    def test_the_pin_is_in_the_mirror_manifest_and_ours_to_host(self):
        p = own_virtualsmc.PACKAGE
        entries = json.loads((ROOT / "p1401/mirror.json").read_text())["entries"]
        self.assertEqual(entries[p["url"]], {"sha256": p["sha256"], "size": p["size"]})
        self.assertTrue(p["url"].endswith(p["sha256"]))
        self.assertTrue(licenses.hostable(p["url"])[0])

    def test_the_build_recipe_and_patch_carry_the_fixes(self):
        v = ROOT / "vendor/smcsuperio"
        patch = (v / "smcsuperio-29.patch").read_text()
        for line in ('!strcmp(getModelName(), "ITE IT8689E")', 'extReg = extReg || !strcmp(detectedDevice->getModelName(), m)',
                     '!strcmp(detectedDevice->getModelName(), "ITE IT8665E") || !strcmp(detectedDevice->getModelName(), "ITE IT8625E")',
                     '"ITE IT8696E"', "ITE IT8698E"):
            self.assertIn(line, patch)
        build = (v / "build.sh").read_text()
        self.assertIn("VSMC=b5c62c2311540c529c00996d0d9cec33f8e571c9", build)
        self.assertIn('[ "$W_N" = 0 ]', build)
        self.assertTrue((v / "LICENSE-VirtualSMC.txt").read_text().startswith("Copyright"))

    def test_the_build_swaps_after_the_efi_is_written(self):
        src = (ROOT / "p1401/engine.py").read_text()
        self.assertIn("own_virtualsmc.replace(out_dir, h.notices)", src)

# Needs macOS tools or inputs that exist only where the release is built. The Windows package check counts a skipped
# test as a failure, so these are not collected there; the Mac release step runs them.
if sys.platform != "darwin":
    del Swap.test_the_real_package_matches_its_pin_and_swaps_in


if __name__ == "__main__":
    unittest.main()
