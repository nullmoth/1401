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


def ioreg_text(displays):
    """What ioreg prints for display-class PCI functions: (vendor, device) as 16-bit ints, little-endian bytes."""
    out = ""
    for i, (v, d) in enumerate(displays):
        out += (f"  +-o GPU{i}@2  <class IOPCIDevice>\n    | {{\n    |   \"vendor-id\" = <{v & 255:02x}{v >> 8:02x}0000>\n"
                f"    |   \"device-id\" = <{d & 255:02x}{d >> 8:02x}0000>\n    |   \"class-code\" = <00000300>\n    | }}\n")
    return out


def run(level, kext=True, collection_takes_it=True, boot_args="keepsyms=1 nmhybrid=2", with_state=True, displays=(), kexts=("NMIntelFB",)):
    t = pathlib.Path(tempfile.mkdtemp())
    (t / "ext").mkdir(); (t / "ns/kexts").mkdir(parents=True)
    for name in (kexts if kext else ()):
        k = t / f"ns/kexts/{name}.kext/Contents"; (k / "MacOS").mkdir(parents=True)
        (k / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": f"com.nullmoth.{name}"}))
        (k / f"MacOS/{name}").write_bytes(b"x")
    if level == "off":
        (t / "ext/NMIntelFB.kext").mkdir()
        (t / "ext/NMGopFB.kext").mkdir()
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
kmutil() {{ case "$1" in inspect) {'echo com.nullmoth.NMIntelFB; echo com.nullmoth.NMGopFB' if collection_takes_it else 'true'};; *) true;; esac; }}
ioreg() {{ cat <<'EOT'
{ioreg_text(displays)}EOT
}}
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

    def test_a_radeon_680m_laptop_installs_the_firmware_framebuffer_panel_driver_and_not_the_intel_one(self):
        out, args, t = run("copy", displays=[(0x1002, 0x1681)], kexts=("NMGopFB",), boot_args="keepsyms=1")
        self.assertTrue((t / "ext/NMGopFB.kext/Contents/MacOS/NMGopFB").exists(), out)
        self.assertFalse((t / "ext/NMIntelFB.kext").exists())
        self.assertEqual(args.split(), ["keepsyms=1", "nmhybrid=1"])

    def test_an_intel_panel_still_installs_the_intel_driver_only(self):
        out, args, t = run("copy", displays=[(0x8086, 0xA7A0)], kexts=("NMIntelFB", "NMGopFB"), boot_args="keepsyms=1")
        self.assertTrue((t / "ext/NMIntelFB.kext").exists(), out)
        self.assertFalse((t / "ext/NMGopFB.kext").exists())

    def test_an_intel_and_a_radeon_laptop_gets_both(self):
        out, _, t = run("copy", displays=[(0x8086, 0x9A49), (0x1002, 0x15BF)], kexts=("NMIntelFB", "NMGopFB"), boot_args="keepsyms=1")
        self.assertTrue((t / "ext/NMIntelFB.kext").exists() and (t / "ext/NMGopFB.kext").exists(), out)

    def test_a_radeon_macos_drives_itself_does_not_get_the_new_driver(self):
        # Polaris 67EF and Navi 21 73BF have Apple drivers: nothing about them changes, the switch behaves as it always did
        out, _, t = run("copy", displays=[(0x1002, 0x67EF)], kexts=("NMIntelFB", "NMGopFB"), boot_args="keepsyms=1")
        self.assertTrue((t / "ext/NMIntelFB.kext").exists(), out)
        self.assertFalse((t / "ext/NMGopFB.kext").exists())

    def test_a_package_without_the_amd_driver_stops_before_changing_anything(self):
        out, args, t = run("copy", displays=[(0x1002, 0x1681)], kexts=("NMIntelFB",), boot_args="keepsyms=1")
        self.assertIn("STOP the AMD panel driver (NMGopFB) is not on this Mac", out)
        self.assertEqual(args, "keepsyms=1")
        self.assertFalse((t / "ext/NMGopFB.kext").exists())

    def test_off_removes_both_kexts(self):
        _, args, t = run("off", boot_args="keepsyms=1 nmhybrid=1")
        self.assertFalse((t / "ext/NMIntelFB.kext").exists() or (t / "ext/NMGopFB.kext").exists())

    def test_the_radeon_ids_equal_the_ones_the_scan_calls_unsupported_by_apple(self):
        # the shell list and range checks against p1401/amd_gpu: every APU_RDNA / RDNA 3 / RDNA 4 id is taken, no native one is
        import sys; sys.path.insert(0, str(SETUP.parents[2]))
        from p1401 import amd_gpu
        fn = between("hy_amd_gop() {", "; }\n")
        ids = list(range(0x1000, 0x1A00)) + list(range(0x6600, 0x7700))
        r = subprocess.run(["/bin/bash", "-c", fn + "\nfor d in " + " ".join(f"{i:04X}" for i in ids) + "; do hy_amd_gop $d && echo $d; done"],
                           capture_output=True, text=True, timeout=60)
        taken = set(r.stdout.split())
        for dev in ids:
            fam = amd_gpu.classify({"Device ID": f"1002-{dev:04X}"})
            want = fam is not None and fam[1] in (amd_gpu.APU_RDNA, amd_gpu.RDNA3, amd_gpu.RDNA4)
            self.assertEqual(f"{dev:04X}" in taken, want, f"{dev:04X} {fam}")

    def test_the_uninstallers_know_the_kext_and_the_argument(self):
        self.assertIn("NMIntelFB", (SETUP.parent / "nullmoth-uninstall.sh").read_text().split("KEXTS=", 1)[1].split("\n", 1)[0])
        self.assertIn("nmhybrid=*", T)


if __name__ == "__main__":
    unittest.main()
