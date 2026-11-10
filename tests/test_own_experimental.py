"""NullMoth's experimental EFI drivers go into the EFI switched off, only where they fit, all or nothing.

Set EFI_DRIVERS_ZIP=<the built NullMoth-EFI-drivers.zip> to also run the placement on the real package."""
import hashlib
import io
import json
import os
import pathlib
import plistlib
import tempfile
import unittest
import zipfile
from unittest import mock

from p1401 import licenses, own_experimental as oe

ROOT = pathlib.Path(__file__).resolve().parents[1]


def package(tamper=None, drop=None):
    buf, sums = io.BytesIO(), []
    with zipfile.ZipFile(buf, "w") as z:
        for k in oe.DRIVERS:
            if k == drop:
                continue
            body = f"ours {k}".encode()
            z.writestr(f"Kexts/{k}.kext/Contents/MacOS/{k}", b"changed" if k == tamper else body)
            z.writestr(f"Kexts/{k}.kext/Contents/Info.plist", "<plist/>")
            sums.append(f"{hashlib.sha256(body).hexdigest()}  {k}.kext")
        z.writestr("SHA256SUMS", "\n".join(sums) + "\n")
    data = buf.getvalue()
    return data, {"version": "t", "url": "https://nullmothsystems.com/mirror/x", "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def efi(root, kexts):
    oc = pathlib.Path(root, "EFI", "OC")
    for n in kexts:
        (oc / "Kexts" / f"{n}.kext" / "Contents").mkdir(parents=True)
    cfg = {"Kernel": {"Add": [{"BundlePath": f"{n}.kext", "Enabled": True} for n in kexts]}, "NVRAM": {"Add": {}}}
    (oc / "config.plist").write_bytes(plistlib.dumps(cfg, sort_keys=False))
    return oc


def entries(oc):
    return plistlib.loads((oc / "config.plist").read_bytes())["Kernel"]["Add"]


LAPTOP = ("Lilu", "VirtualSMC", "SMCBatteryManager")
DESKTOP = ("Lilu", "VirtualSMC", "SMCSuperIO")


class Place(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.addCleanup(self.t.cleanup)

    def run_place(self, kexts, nvidia, data=None, pin=None):
        oc = efi(self.t.name, kexts)
        if data is None:
            data, pin = package()
        notices = []
        with mock.patch.object(oe, "PACKAGE", pin):
            got = oe.place(self.t.name, notices, nvidia=nvidia, fetch=lambda url: data)
        return oc, got, notices

    def test_a_laptop_with_an_nvidia_card_gets_both_switched_off_after_what_they_need(self):
        oc, got, notices = self.run_place(LAPTOP, True)
        self.assertEqual(got, ["NMKbdBacklight", "NMHDA"])
        add = entries(oc)
        self.assertEqual([e["BundlePath"] for e in add][-2:], ["NMKbdBacklight.kext", "NMHDA.kext"])
        for e in add[-2:]:
            self.assertIs(e["Enabled"], False)
            self.assertEqual((e["Arch"], e["PlistPath"], e["MinKernel"]), ("x86_64", "Contents/Info.plist", "24.0.0"))
            self.assertTrue((oc / "Kexts" / e["BundlePath"] / e["ExecutablePath"]).is_file())
        self.assertEqual(add[-1]["MaxKernel"], "24.99.99")     # Apple's HD Audio driver ends with macOS 15
        self.assertEqual(add[-2]["MaxKernel"], "")
        self.assertTrue(all(e["Enabled"] for e in add[:-2]))    # nothing the engine wrote is touched
        self.assertFalse((oc / "Kexts/.nullmoth-experimental").exists())
        self.assertIn("switched off", notices[-1])

    def test_a_desktop_gets_no_keyboard_driver(self):
        oc, got, _ = self.run_place(DESKTOP, True)
        self.assertEqual(got, ["NMHDA"])
        self.assertFalse((oc / "Kexts/NMKbdBacklight.kext").exists())

    def test_without_the_nvidia_driver_there_is_no_display_audio_driver(self):
        oc, got, _ = self.run_place(LAPTOP, False)
        self.assertEqual(got, ["NMKbdBacklight"])

    def test_an_efi_without_lilu_is_left_alone(self):
        oc, got, notices = self.run_place(("FakeSMC",), True)
        self.assertEqual((got, notices), ([], []))
        self.assertEqual(len(entries(oc)), 1)

    def test_a_package_that_does_not_match_its_pin_changes_nothing(self):
        data, pin = package()
        oc, got, notices = self.run_place(LAPTOP, True, data + b"!", pin)
        self.assertEqual(got, [])
        self.assertEqual(len(entries(oc)), len(LAPTOP))
        self.assertFalse((oc / "Kexts/NMHDA.kext").exists())
        self.assertIn("were not added", notices[-1])

    def test_one_bad_driver_means_none_is_placed(self):
        data, pin = package(tamper="NMHDA")
        oc, got, _ = self.run_place(LAPTOP, True, data, pin)
        self.assertEqual(got, [])
        self.assertFalse((oc / "Kexts/NMKbdBacklight.kext").exists())
        self.assertEqual(len(entries(oc)), len(LAPTOP))

    def test_no_network_leaves_the_efi_whole_and_says_so(self):
        oc = efi(self.t.name, LAPTOP)
        notices = []
        def offline(url):
            raise OSError("unreachable")
        self.assertEqual(oe.place(self.t.name, notices, nvidia=True, fetch=offline), [])
        self.assertEqual(len(entries(oc)), len(LAPTOP))
        self.assertIn("OSError", notices[-1])

    def test_a_second_build_over_the_same_efi_adds_nothing_twice(self):
        oc, got, _ = self.run_place(LAPTOP, True)
        data, pin = package()
        with mock.patch.object(oe, "PACKAGE", pin):
            again = oe.place(self.t.name, [], nvidia=True, fetch=lambda url: data)
        self.assertEqual(again, [])
        self.assertEqual([e["BundlePath"] for e in entries(oc)].count("NMHDA.kext"), 1)

    @unittest.skipUnless(os.environ.get("EFI_DRIVERS_ZIP"), "set EFI_DRIVERS_ZIP to the built package")
    def test_the_real_package_matches_its_pin_and_is_placed(self):
        data = pathlib.Path(os.environ["EFI_DRIVERS_ZIP"]).read_bytes()
        oc = efi(self.t.name, LAPTOP)
        notices = []
        got = oe.place(self.t.name, notices, nvidia=True, fetch=lambda url: data)
        self.assertEqual(got, ["NMKbdBacklight", "NMHDA"], notices)
        info = plistlib.loads((oc / "Kexts/NMKbdBacklight.kext/Contents/Info.plist").read_bytes())
        self.assertIn("com.apple.iokit.IOHIDFamily", info["OSBundleLibraries"])


class Pins(unittest.TestCase):
    def test_the_pin_is_in_the_mirror_manifest_and_ours_to_host(self):
        p = oe.PACKAGE
        e = json.loads((ROOT / "p1401/mirror.json").read_text())["entries"]
        self.assertEqual(e[p["url"]], {"sha256": p["sha256"], "size": p["size"]})
        self.assertTrue(p["url"].endswith(p["sha256"]))
        self.assertTrue(licenses.hostable(p["url"])[0])

    def test_the_build_places_them_after_the_virtualsmc_swap_and_knows_the_nvidia_notice(self):
        src = (ROOT / "p1401/engine.py").read_text()
        self.assertLess(src.index("own_virtualsmc.replace(out_dir, h.notices)"), src.index("own_experimental.place(out_dir, h.notices, nvidia="))
        self.assertIn('h.notices.append(NVIDIA_NOTICE + ", ".join(hit)', src)


if __name__ == "__main__":
    unittest.main()
