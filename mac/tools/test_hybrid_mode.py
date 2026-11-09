#!/usr/bin/env python3
"""Hybrid laptop mode (setup --hybrid): the Intel panel driver is installed and nmhybrid written only when asked, the kernel
collection must contain the kext or everything is put back, and off removes the kext and the boot argument."""
import pathlib
import plistlib
import subprocess
import tempfile
import unittest

SETUP = pathlib.Path(__file__).resolve().parents[1] / "Resources/nullmoth-setup.sh"
T = SETUP.read_text()


def between(start, end):
    a = T.index(start)
    return T[a:T.index(end, a) + len(end)]


FUNCS = between("has() {", "\nget() {")[:-len("\nget() {")] + "\n" + between("get() {", "; }\n") + "\n"
BLOCK = between('if [ -n "${HYBRID:-}" ]; then', '  cleanup; echo "RESULT ok"; exit 0\nfi\n')


def run(level, kext=True, collection_takes_it=True, boot_args="keepsyms=1 nmhybrid=2", with_state=True):
    t = pathlib.Path(tempfile.mkdtemp())
    (t / "ext").mkdir(); (t / "ns/kexts").mkdir(parents=True)
    if kext:
        k = t / "ns/kexts/NMIntelFB.kext/Contents"; (k / "MacOS").mkdir(parents=True)
        (k / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.nullmoth.NMIntelFB"}))
        (k / "MacOS/NMIntelFB").write_bytes(b"x")
    if level == "off":
        (t / "ext/NMIntelFB.kext").mkdir()
    cfg = t / "config.plist"
    B = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
    cfg.write_bytes(plistlib.dumps({"NVRAM": {"Add": {B: {"boot-args": boot_args}}}}))
    (t / "ns/state").write_text("x")
    block = BLOCK.replace("/Library/Extensions", str(t / "ext")).replace("/Library/NullMoth/kexts", str(t / "ns/kexts")) \
                 .replace("/Library/KernelCollections", str(t / "kc"))
    script = f'''
stop() {{ echo "STOP $*"; exit 1; }}; step() {{ :; }}; ok() {{ echo "OK $*"; }}; note() {{ echo "NOTE $*"; }}; ro_why() {{ :; }}
cleanup() {{ :; }}; chown() {{ :; }}; sw_vers() {{ echo 15.8; }}
nvram() {{ [ "$1" = boot-args ] && echo "boot-args	{boot_args}"; return 0; }}
kmutil() {{ case "$1" in inspect) {'echo com.nullmoth.NMIntelFB' if collection_takes_it else 'true'};; *) true;; esac; }}
PKG=""; SHA=""; HYBRID={level}; ST={t / "ns"}; STATE={t / "ns/state"}; C={cfg}; B={B}
{"rm -f $STATE" if not with_state else ""}
{FUNCS}
{block}'''
    p = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=60)
    args = plistlib.loads(cfg.read_bytes())["NVRAM"]["Add"][B]["boot-args"]
    return p.stdout, args, t


class Hybrid(unittest.TestCase):
    def test_copy_installs_the_kext_and_sets_level_1_replacing_an_old_level(self):
        out, args, t = run("copy")
        self.assertTrue((t / "ext/NMIntelFB.kext/Contents/MacOS/NMIntelFB").exists(), out)
        self.assertEqual(args.split(), ["keepsyms=1", "nmhybrid=1"])
        self.assertEqual((t / "ns/hybrid").read_text(), "LEVEL=1\n")

    def test_import_is_level_2(self):
        _, args, _ = run("import", boot_args="keepsyms=1")
        self.assertEqual(args.split(), ["keepsyms=1", "nmhybrid=2"])

    def test_a_collection_that_does_not_contain_the_kext_puts_everything_back(self):
        out, args, t = run("copy", collection_takes_it=False, boot_args="keepsyms=1")
        self.assertIn("STOP the kernel collection did not take NMIntelFB", out)
        self.assertFalse((t / "ext/NMIntelFB.kext").exists())
        self.assertEqual(args, "keepsyms=1")

    def test_a_package_without_the_kext_stops_before_changing_anything(self):
        out, args, t = run("copy", kext=False, boot_args="keepsyms=1")
        self.assertIn("STOP the Intel panel driver (NMIntelFB) is not on this Mac", out)
        self.assertEqual(args, "keepsyms=1")
        self.assertFalse((t / "ext/NMIntelFB.kext").exists())

    def test_without_the_nvidia_driver_it_will_not_turn_on(self):
        out, args, _ = run("copy", with_state=False, boot_args="keepsyms=1")
        self.assertIn("STOP the NVIDIA driver is not installed", out)
        self.assertEqual(args, "keepsyms=1")

    def test_off_removes_the_kext_the_record_and_only_the_hybrid_argument(self):
        out, args, t = run("off", boot_args="keepsyms=1 nmhybrid=1 nvfb=1")
        self.assertEqual(args.split(), ["keepsyms=1", "nvfb=1"])
        self.assertFalse((t / "ext/NMIntelFB.kext").exists())
        self.assertFalse((t / "ns/hybrid").exists())

    def test_the_uninstallers_know_the_kext_and_the_argument(self):
        self.assertIn("NMIntelFB", (SETUP.parent / "nullmoth-uninstall.sh").read_text().split("KEXTS=", 1)[1].split("\n", 1)[0])
        self.assertIn("nmhybrid=*", T)


if __name__ == "__main__":
    unittest.main()
