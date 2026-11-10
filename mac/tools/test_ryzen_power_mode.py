#!/usr/bin/env python3
"""Ryzen power profile (setup --ryzen-power on|off): the kext and the job are installed only when asked and only on a Ryzen,
the kernel collection must contain the kext or everything is put back, a refused job rolls the kext and boot argument back,
and off removes the job, the kext and only the nmsmn argument."""
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
BLOCK = between('if [ -n "${RYZEN:-}" ]; then', '  cleanup; echo "RESULT ok"; exit 0\nfi\n')


def run(mode, cpu="AMD Ryzen 7 7840U w/ Radeon 780M Graphics", kext=True, binary=True, collection_takes_it=True, job_ok=True,
        boot_args="keepsyms=1", with_state=True, limits=""):
    t = pathlib.Path(tempfile.mkdtemp())
    (t / "ext").mkdir(); (t / "ns/kexts").mkdir(parents=True); (t / "ns/ryzenadj").mkdir()
    if kext:
        k = t / "ns/kexts/NMSMN.kext/Contents"; (k / "MacOS").mkdir(parents=True)
        (k / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.nullmoth.NMSMN"}))
        (k / "MacOS/NMSMN").write_bytes(b"x")
    if binary:
        (t / "ns/ryzenadj/ryzenadj").write_bytes(b"x")
    if mode == "off":
        (t / "ext/NMSMN.kext").mkdir()
    fake = t / "power.sh"
    fake.write_text(f'#!/bin/bash\necho "$@" >> {t}/job.log\n[ "$1" = remove ] && exit 0\nexit {0 if job_ok else 1}\n')
    cfg = t / "config.plist"
    B = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
    cfg.write_bytes(plistlib.dumps({"NVRAM": {"Add": {B: {"boot-args": boot_args}}}}))
    (t / "ns/state").write_text("x")
    block = BLOCK.replace("/Library/Extensions", str(t / "ext")).replace("/Library/NullMoth/kexts", str(t / "ns/kexts")) \
                 .replace("/Library/NullMoth/ryzenadj", str(t / "ns/ryzenadj")).replace("/Library/KernelCollections", str(t / "kc")) \
                 .replace('"$(dirname "$0")/nullmoth-ryzen-power.sh"', f'"{fake}"')
    script = f'''
stop() {{ echo "STOP $*"; exit 1; }}; step() {{ :; }}; ok() {{ echo "OK $*"; }}; note() {{ echo "NOTE $*"; }}; ro_why() {{ :; }}
cleanup() {{ :; }}; chown() {{ :; }}; sw_vers() {{ echo 15.8; }}
sysctl() {{ echo "{cpu}"; }}
nvram() {{ [ "$1" = boot-args ] && echo "boot-args	{boot_args}"; return 0; }}
kmutil() {{ case "$1" in inspect) {'echo com.nullmoth.NMSMN' if collection_takes_it else 'true'};; *) true;; esac; }}
PKG=""; SHA=""; RYZEN={mode}; RYZENLIM="{limits}"; ST={t / "ns"}; STATE={t / "ns/state"}; C={cfg}; B={B}
{"rm -f $STATE" if not with_state else ""}
{FUNCS}
{block}'''
    p = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=60)
    args = plistlib.loads(cfg.read_bytes())["NVRAM"]["Add"][B]["boot-args"]
    log = (t / "job.log").read_text() if (t / "job.log").exists() else ""
    return p.stdout, args, t, log


class RyzenPower(unittest.TestCase):
    def test_on_installs_the_kext_sets_the_argument_and_installs_the_job(self):
        out, args, t, log = run("on")
        self.assertTrue((t / "ext/NMSMN.kext/Contents/MacOS/NMSMN").exists(), out)
        self.assertEqual(args.split(), ["keepsyms=1", "nmsmn=1"])
        self.assertIn("install --ryzenadj", log)
        self.assertTrue((t / "ns/ryzen-power").exists())

    def test_chosen_limits_reach_the_job(self):
        _, _, _, log = run("on", limits="25:28:35:85")
        self.assertIn("--stapm 25 --slow 28 --fast 35 --temp 85", log)

    def test_bad_limits_stop_before_anything_changes(self):
        out, args, t, log = run("on", limits="25:x:35:85")
        self.assertIn("STOP --ryzen-limits takes four whole numbers", out)
        self.assertEqual(args, "keepsyms=1")
        self.assertFalse((t / "ext/NMSMN.kext").exists())
        self.assertEqual(log, "")

    def test_a_mac_without_a_ryzen_is_refused_and_unchanged(self):
        out, args, t, log = run("on", cpu="13th Gen Intel(R) Core(TM) i7-1360P")
        self.assertIn("STOP this Mac does not have a Ryzen processor", out)
        self.assertEqual(args, "keepsyms=1")
        self.assertFalse((t / "ext/NMSMN.kext").exists())

    def test_a_package_without_the_parts_stops_before_changing_anything(self):
        for kw in ({"kext": False}, {"binary": False}):
            out, args, t, log = run("on", **kw)
            self.assertIn("STOP the Ryzen power parts are not on this Mac", out)
            self.assertEqual(args, "keepsyms=1")
            self.assertFalse((t / "ext/NMSMN.kext").exists())

    def test_a_collection_that_does_not_contain_the_kext_puts_everything_back(self):
        out, args, t, log = run("on", collection_takes_it=False)
        self.assertIn("STOP the kernel collection did not take NMSMN", out)
        self.assertFalse((t / "ext/NMSMN.kext").exists())
        self.assertEqual(args, "keepsyms=1")
        self.assertNotIn("install", log)

    def test_a_refused_job_rolls_the_kext_and_the_argument_back(self):
        out, args, t, log = run("on", job_ok=False)
        self.assertIn("STOP the power-limit job was refused", out)
        self.assertFalse((t / "ext/NMSMN.kext").exists())
        self.assertEqual(args, "keepsyms=1")
        self.assertIn("remove", log)
        self.assertFalse((t / "ns/ryzen-power").exists())

    def test_without_the_nvidia_driver_it_will_not_turn_on(self):
        out, args, _, _ = run("on", with_state=False)
        self.assertIn("STOP the NVIDIA driver is not installed", out)
        self.assertEqual(args, "keepsyms=1")

    def test_off_removes_the_job_the_kext_the_record_and_only_the_nmsmn_argument(self):
        out, args, t, log = run("off", boot_args="keepsyms=1 nmsmn=1 nvfb=1")
        self.assertEqual(args.split(), ["keepsyms=1", "nvfb=1"])
        self.assertFalse((t / "ext/NMSMN.kext").exists())
        self.assertIn("remove", log)

    def test_the_switch_is_off_by_default_nothing_here_runs_without_the_option(self):
        self.assertIn('if [ -n "${RYZEN:-}" ]; then', T)
        self.assertEqual(T.count("--ryzen-power) RYZEN=$2"), 1)

    def test_a_bad_value_is_refused(self):
        out, args, _, _ = run("maybe")
        self.assertIn("STOP --ryzen-power takes on, off or status", out)


if __name__ == "__main__":
    unittest.main()
