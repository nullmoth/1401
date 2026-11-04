#!/usr/bin/env python3
"""Real Mac Pros: a Mac Pro (2019) started by Apple's firmware installs with NVRAM boot-args (no OpenCore), and a real Mac
set up by OpenCore Legacy Patcher keeps its own model through Tahoe preparation. Runs the setup's real code against stub
nvram/sysctl/system_profiler/csrutil and a temp state folder, in both directions."""
import os
import pathlib
import plistlib
import subprocess
import tarfile
import tempfile
import unittest

SETUP = pathlib.Path(__file__).resolve().parents[1] / "Resources/nullmoth-setup.sh"
S = SETUP.read_text()


def cut(start, end):
    assert S.count(start) == 1 and S.count(end) == 1, f"anchor moved in nullmoth-setup.sh: {start[:50]!r} / {end[:50]!r}"
    return S[S.index(start):S.index(end)]


WANT = cut('WANT_ARGS="nvfb=1', "\n# The NVIDIA display card").strip()
HELPERS = cut("native_macpro() {", "\n# Every log query has its own time cap")
NATIVE = cut('[ -z "$CFG" ] && [ "$EFI" = auto ] && native_macpro && NATIVE=1', "else   # the OpenCore path")
PREP = cut('if [ "$UPD" = prepare ] && oclp_real_mac; then', "# Existing BAR and kernel-placement settings")


def env(t, oc=False, model="MacPro7,1", t2=True, sip="disabled", args=""):
    bins = os.path.join(t, "bin")
    os.makedirs(bins, exist_ok=True)
    nvf = os.path.join(t, "nvram.args")
    with open(nvf, "w") as f:
        f.write(args)
    stubs = {
        "nvram": f'''case "$1" in
  *opencore-version) {"echo 'x\tREL-108'; exit 0" if oc else "exit 1"};;
  boot-args) printf 'boot-args\\t%s\\n' "$(cat {nvf})";;
  boot-args=*) printf '%s' "${{1#boot-args=}}" > {nvf};;
  -d) : > {nvf};;
esac''',
        "sysctl": f'echo "{model}"',
        "system_profiler": f'{"echo \'      Model Name: Apple T2 Security Chip\'" if t2 else "echo"}',
        "csrutil": f'echo "System Integrity Protection status: {sip}."',
    }
    for n, body in stubs.items():
        p = os.path.join(bins, n)
        with open(p, "w") as f:
            f.write("#!/bin/bash\n" + body + "\n")
        os.chmod(p, 0o755)
    return bins, nvf


def sh(t, body, bins):
    script = (f'PATH="{bins}:/usr/bin:/bin"\nstep() {{ echo "STEP $*"; }}; ok() {{ echo "OK $*"; }}; note() {{ echo "NOTE $*"; }}\n'
              'stop() { echo "STOP $*"; exit 1; }\nDROP_ARGS="nv_disable=1 -wegnoegpu"\n' + WANT + "\n" + HELPERS + "\n" + body)
    r = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=60, cwd=t)
    return r.returncode, r.stdout


def pkg(t, rc=0):
    root = os.path.join(t, "pkgsrc/pkgroot")
    os.makedirs(root)
    with open(os.path.join(root, "install.sh"), "w") as f:
        f.write(f"#!/bin/bash\nexit {rc}\n")
    os.chmod(os.path.join(root, "install.sh"), 0o755)
    p = os.path.join(t, "p.tar.gz")
    with tarfile.open(p, "w:gz") as z:
        z.add(root, arcname="pkgroot")
    return p


def native_run(t, bins, dry=0, extra=""):
    st = os.path.join(t, "st")
    body = (f'CFG=""; EFI=auto; UPD=""; USBMAP=""; VERB=""; EFIREAD=""; DRY={dry}; NATIVE=0; PKG="{pkg(t)}"\n'
            f'ST="{st}"; STATE="$ST/state"\n{extra}\n' + NATIVE + 'fi\necho "NATIVE=$NATIVE"\n')
    return sh(t, body, bins), st


class Detection(unittest.TestCase):
    def check(self, want, **kw):
        t = tempfile.mkdtemp()
        bins, _ = env(t, **kw)
        rc, _ = sh(t, "native_macpro", bins)
        self.assertEqual(rc == 0, want)

    def test_a_mac_pro_2019_on_apples_firmware_is_native(self):
        self.check(True)

    def test_a_pc_set_up_as_macpro71_without_t2_is_not_native(self):
        self.check(False, t2=False)

    def test_a_mac_pro_that_opencore_started_is_not_native(self):
        self.check(False, oc=True)

    def test_another_t2_mac_is_not_native(self):
        self.check(False, model="MacBookPro16,1")


class NativeInstall(unittest.TestCase):
    def test_install_writes_the_driver_args_into_nvram_and_records_them(self):
        t = tempfile.mkdtemp()
        bins, nvf = env(t, args="-v nv_disable=1")
        (rc, out), st = native_run(t, bins)
        self.assertEqual(rc, 0, out)
        live = open(nvf).read().split()
        self.assertIn("nvaccel=1", live)
        self.assertIn("-v", live)                         # the user's own argument stays
        self.assertNotIn("nv_disable=1", live)            # it hides the card
        rec = open(os.path.join(st, "state")).read()
        self.assertIn("NATIVE=1", rec)
        self.assertIn("amfi_get_out_of_my_way=0x1", rec)

    def test_sip_on_stops_and_changes_nothing(self):
        t = tempfile.mkdtemp()
        bins, nvf = env(t, sip="enabled", args="-v")
        (rc, out), st = native_run(t, bins)
        self.assertNotEqual(rc, 0)
        self.assertIn("csrutil disable", out)
        self.assertEqual(open(nvf).read(), "-v")
        self.assertFalse(os.path.exists(os.path.join(st, "state")))

    def test_opencore_options_are_refused_on_a_native_mac_pro(self):
        t = tempfile.mkdtemp()
        bins, nvf = env(t, args="-v")
        (rc, out), _ = native_run(t, bins, extra='VERB=on')
        self.assertNotEqual(rc, 0)
        self.assertEqual(open(nvf).read(), "-v")

    def test_a_reinstall_keeps_the_first_installs_args_recorded_as_added(self):
        t = tempfile.mkdtemp()
        bins, nvf = env(t, args="-v")
        (rc, out), st = native_run(t, bins)
        self.assertEqual(rc, 0, out)
        os.remove(os.path.join(t, "p.tar.gz")); __import__("shutil").rmtree(os.path.join(t, "pkgsrc"))
        (rc, out), st = native_run(t, bins)
        self.assertEqual(rc, 0, out)
        self.assertIn("nvaccel=1", open(os.path.join(st, "state")).read().split("ADDED_ARGS=")[1].splitlines()[0])

    def test_without_a_mac_pro_the_opencore_path_is_taken(self):
        t = tempfile.mkdtemp()
        bins, nvf = env(t, oc=True, args="-v")
        (rc, out), _ = native_run(t, bins)
        self.assertIn("NATIVE=0", out)
        self.assertEqual(open(nvf).read(), "-v")


class NativeRemove(unittest.TestCase):
    def test_removal_takes_out_only_the_added_args(self):
        t = tempfile.mkdtemp()
        bins, nvf = env(t, args="-v keepsyms=1 nvfb=1 nvaccel=1")
        rc, out = sh(t, 'strip_native_args "nvfb=1 nvaccel=1"', bins)
        self.assertEqual(rc, 0, out)
        self.assertEqual(open(nvf).read().split(), ["-v", "keepsyms=1"])

    def test_removal_of_every_arg_deletes_the_variable(self):
        t = tempfile.mkdtemp()
        bins, nvf = env(t, args="nvfb=1")
        rc, out = sh(t, 'strip_native_args "nvfb=1"', bins)
        self.assertEqual((rc, open(nvf).read()), (0, ""))


class OclpRealMac(unittest.TestCase):
    def prep(self, cfg):
        t = tempfile.mkdtemp()
        bins, _ = env(t, oc=True)
        c = os.path.join(t, "config.plist")
        with open(c, "wb") as f:
            plistlib.dump(cfg, f)
        body = (f'C="{c}"; UPD=prepare; EDITS=(); ADDK=(); FETCH=(); KX={t}\n'
                'has() { plutil -extract "$1" raw -o - "$C" >/dev/null 2>&1; }; get() { plutil -extract "$1" raw -o - "$C" 2>/dev/null; }\n'
                'kpos() { :; }; fetch_kext() { :; }\n' + PREP + 'echo "EDITS=${#EDITS[@]}"\n')
        return sh(t, body, bins)

    def test_a_real_mac_pro_51_keeps_its_model(self):
        rc, out = self.prep({"NVRAM": {"Add": {"4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102": {"OCLP-Model": "MacPro5,1"}}},
                             "PlatformInfo": {"Generic": {"SystemProductName": "MacPro5,1"}}})
        self.assertEqual(rc, 0, out)
        self.assertIn("real MacPro5,1", out)
        self.assertIn("EDITS=0", out)

    def test_a_pc_on_a_dropped_model_is_still_moved_to_macpro71(self):
        rc, out = self.prep({"PlatformInfo": {"Generic": {"SystemProductName": "iMacPro1,1"}}})
        self.assertEqual(rc, 0, out)
        self.assertIn("-> MacPro7,1", out)
        self.assertNotIn("EDITS=0", out)


if __name__ == "__main__":
    unittest.main()
