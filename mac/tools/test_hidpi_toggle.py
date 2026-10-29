"""The app's HiDPI toggle adds or removes exactly nvfbhidpi=1 in the OpenCore boot-args and keeps every other argument.

Runs setup's --hidpi block against a copy of a config; the negative control is an argument that only resembles it.
"""
import pathlib
import plistlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
source = (ROOT / "Resources/nullmoth-setup.sh").read_text()
start = source.index('if [ -n "${HIDPI:-}" ]; then')
end = source.index("\nfi\n", start) + 4
BLOCK = source[start:end]
B = "7C436110-AB2A-4BBB-A880-FE41995C9F82"

HARNESS = r'''
set -u
C="$1"; HIDPI="$2"; B=7C436110-AB2A-4BBB-A880-FE41995C9F82
has() { plutil -extract "$1" raw -o - "$C" >/dev/null 2>&1; }
get() { plutil -extract "$1" raw -o - "$C" 2>/dev/null; }
ok() { echo "OK $*"; }; step() { :; }; note() { :; }; cleanup() { :; }
stop() { echo "STOP $*"; exit 3; }; ro_why() { :; }
nvram() { :; }
''' + BLOCK


def run(args, want):
    with tempfile.TemporaryDirectory() as d:
        cfg = pathlib.Path(d, "config.plist")
        cfg.write_bytes(plistlib.dumps({"NVRAM": {"Add": {B: {"boot-args": args}}}}))
        r = subprocess.run(["/bin/bash", "-c", HARNESS, "h", str(cfg), want], capture_output=True, text=True,
                           env={"PATH": "/usr/bin:/bin"})
        return r.returncode, r.stdout, plistlib.loads(cfg.read_bytes())["NVRAM"]["Add"][B]["boot-args"]


class HiDPIToggle(unittest.TestCase):
    def test_on_adds_the_argument_once_and_keeps_the_rest(self):
        rc, out, args = run("-v nvfb=1 nvaccel=1", "on")
        self.assertEqual(rc, 0, out)
        self.assertEqual(args, "-v nvfb=1 nvaccel=1 nvfbhidpi=1")
        self.assertEqual(run(args, "on")[2], args)

    def test_off_removes_only_it(self):
        self.assertEqual(run("-v nvfbhidpi=1 nvfb=1 nvfbhidpi=10", "off")[2], "-v nvfb=1 nvfbhidpi=10")

    def test_anything_else_is_refused(self):
        rc, out, args = run("-v", "maybe")
        self.assertEqual(rc, 3)
        self.assertEqual(args, "-v")


if __name__ == "__main__":
    unittest.main()
