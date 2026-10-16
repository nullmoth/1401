#!/usr/bin/env python3
"""Shaneee's Fix PAT is swapped for Algrey's on a user's own AMD config (user report 10-10: RmInitAdapter failed
(0x25:0x40:1310) with Shaneee's on; Algrey's reached the desktop). Runs the setup's real step on stub configs, both ways."""
import os
import pathlib
import plistlib
import subprocess
import tempfile
import unittest

SETUP = pathlib.Path(__file__).resolve().parents[1] / "Resources/nullmoth-setup.sh"
START = "# AMD (AMD Vanilla patches)"
END = 'del=$(plutil -extract NVRAM.Delete.$B'


def run(patches):
    s = SETUP.read_text()
    assert s.count(START) == 1 and s.count(END) == 1, "anchors moved in nullmoth-setup.sh"
    t = tempfile.mkdtemp()
    cfg = os.path.join(t, "config.plist")
    with open(cfg, "wb") as f:
        plistlib.dump({"Kernel": {"Patch": [{"Comment": c, "Enabled": e, "MinKernel": k} for c, e, k in patches]}}, f)
    script = (f'C="{cfg}"; EDITS=()\nget() {{ plutil -extract "$1" raw -o - "$C" 2>/dev/null; }}\n'
              + s[s.index(START):s.index(END)] + '\nprintf "%s\\n" "${EDITS[@]}"\n')
    r = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return [l for l in r.stdout.splitlines() if l and not l.startswith("CHANGE")]


SH15, AL15 = "Shaneee / Zormeister | _mtrr_update_action | Fix PAT | 15.0+", "Algrey / Zormeister | _mtrr_update_action | Fix PAT | 15.0+"
SH13, AL13 = "Shaneee | _mtrr_update_action | Fix PAT | 10.13+", "algrey | _mtrr_update_action | fix PAT | 10.13+"


class PatSwap(unittest.TestCase):
    def test_shaneee_on_with_algrey_off_is_swapped_for_the_same_kernel_range(self):
        got = run([(AL13, False, "17.0.0"), (SH13, False, "17.0.0"), (AL15, False, "24.0.0"), (SH15, True, "24.0.0")])
        self.assertEqual(got, ["Kernel.Patch.3.Enabled|-bool|false", "Kernel.Patch.2.Enabled|-bool|true"])

    def test_algrey_already_on_changes_nothing(self):
        self.assertEqual(run([(AL15, True, "24.0.0"), (SH15, False, "24.0.0")]), [])

    def test_shaneee_on_without_an_algrey_entry_is_left_alone(self):
        self.assertEqual(run([(SH15, True, "24.0.0")]), [])

    def test_an_intel_config_with_no_pat_patches_changes_nothing(self):
        self.assertEqual(run([("Some other patch", True, "")]), [])


if __name__ == "__main__":
    unittest.main()
