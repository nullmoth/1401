"""A USB port map the user made replaces the default one: copied in, loaded after USBToolBox.kext, UTBDefault.kext off.
A folder that is not a data-only map is refused by name and the default map stays (1401 #3)."""
import os
import plistlib
import tempfile
import unittest

from p1401 import utbmap


def make_map(root, name="UTBMap.kext", info=None, extra=None):
    kext = os.path.join(root, name)
    os.makedirs(os.path.join(kext, "Contents"))
    info = info if info is not None else {"CFBundleIdentifier": "com.example.UTBMap", "CFBundlePackageType": "KEXT",
                                          "IOKitPersonalities": {"UTBMap": {"IOClass": "USBToolBox", "ports": {"SS04": {"port": 4}}}}}
    with open(os.path.join(kext, "Contents", "Info.plist"), "wb") as f:
        plistlib.dump(info, f)
    for rel, data in (extra or {}).items():
        p = os.path.join(kext, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(data)
    return kext


def efi(add=None):
    out = tempfile.mkdtemp()
    oc = os.path.join(out, "EFI", "OC")
    os.makedirs(os.path.join(oc, "Kexts"))
    add = add if add is not None else [
        {"BundlePath": "Lilu.kext", "Enabled": True}, {"BundlePath": "USBToolBox.kext", "Enabled": True},
        {"BundlePath": "UTBDefault.kext", "Enabled": True}, {"BundlePath": "VirtualSMC.kext", "Enabled": True}]
    with open(os.path.join(oc, "config.plist"), "wb") as f:
        plistlib.dump({"Kernel": {"Add": add}}, f)
    return out


def kexts(out):
    with open(os.path.join(out, "EFI", "OC", "config.plist"), "rb") as f:
        return [(k["BundlePath"], k["Enabled"]) for k in plistlib.load(f)["Kernel"]["Add"]]


class UtbMapImport(unittest.TestCase):
    def test_the_map_is_copied_loaded_after_usbtoolbox_and_the_default_goes_off(self):
        src = make_map(tempfile.mkdtemp())
        out = efi()
        changes = utbmap.apply(out, src)
        self.assertEqual(kexts(out), [("Lilu.kext", True), ("USBToolBox.kext", True), ("UTBMap.kext", True),
                                      ("UTBDefault.kext", False), ("VirtualSMC.kext", True)])
        self.assertTrue(os.path.isfile(os.path.join(out, "EFI", "OC", "Kexts", "UTBMap.kext", "Contents", "Info.plist")))
        self.assertEqual([c["rule"] for c in changes], [utbmap.RULE])

    def test_a_second_import_replaces_the_first_and_does_not_list_it_twice(self):
        out = efi()
        utbmap.apply(out, make_map(tempfile.mkdtemp()))
        utbmap.apply(out, make_map(tempfile.mkdtemp()))
        self.assertEqual([n for n, _ in kexts(out)].count("UTBMap.kext"), 1)

    def test_a_kext_with_a_program_inside_is_refused_and_the_default_stays(self):
        src = make_map(tempfile.mkdtemp(), extra={"Contents/MacOS/UTBMap": b"\xcf\xfa\xed\xfe"})
        out = efi()
        (c,) = utbmap.apply(out, src)
        self.assertEqual(c["after"], "not used")
        self.assertIn("program", c["why"])
        self.assertIn(("UTBDefault.kext", True), kexts(out))
        self.assertNotIn("UTBMap.kext", [n for n, _ in kexts(out)])
        self.assertFalse(os.path.exists(os.path.join(out, "EFI", "OC", "Kexts", "UTBMap.kext")))

    def test_each_kind_of_wrong_folder_is_refused_with_its_reason(self):
        t = tempfile.mkdtemp()
        cases = {
            "no Info.plist": os.makedirs(os.path.join(t, "A.kext", "Contents")) or os.path.join(t, "A.kext"),
            "no personalities": make_map(t, "B.kext", info={"CFBundleIdentifier": "x"}),
            "an executable named": make_map(t, "C.kext", info={"CFBundleIdentifier": "x", "CFBundleExecutable": "X",
                                                                "IOKitPersonalities": {"a": {}}}),
            "a link": None,
        }
        link = make_map(t, "D.kext")
        os.symlink("/etc/hosts", os.path.join(link, "Contents", "hosts"))
        cases["a link"] = link
        big = make_map(t, "E.kext", extra={"Contents/big.bin": b"0" * (utbmap.MAX_BYTES + 1)})
        cases["larger than 1 MB"] = big
        for why, path in cases.items():
            with self.assertRaises(utbmap.Refused, msg=why) as cm:
                utbmap.check(path)
            self.assertTrue(why.split()[-1] in str(cm.exception) or why.split()[0] in str(cm.exception), (why, str(cm.exception)))

    def test_a_build_without_usbtoolbox_does_not_take_a_map_it_cannot_load(self):
        out = efi(add=[{"BundlePath": "Lilu.kext", "Enabled": True}])
        (c,) = utbmap.apply(out, make_map(tempfile.mkdtemp()))
        self.assertEqual(c["after"], "not used")
        self.assertEqual(kexts(out), [("Lilu.kext", True)])


if __name__ == "__main__":
    unittest.main()
