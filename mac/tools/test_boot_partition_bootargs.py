#!/usr/bin/env python3
"""Two OpenCore partitions and no serial match: the one whose config sets exactly this boot's boot-args and model is the
one that started the Mac (user reports 10-10: "startup partition could not be confirmed" with disk0s1 + disk2s1).
Runs the setup's real step against stub nvram/sysctl and two fake partitions, in both directions."""
import os
import pathlib
import plistlib
import subprocess
import tempfile
import unittest

SETUP = pathlib.Path(__file__).resolve().parents[1] / "Resources/nullmoth-setup.sh"
START = "    # Still two or more (user reports 10-10"
END = '    if [ "$BOOT_BOUND" != 1 ]; then\n      for d in $found; do echo "NOTE candidate $d"; done'
LIVE = "-v keepsyms=1 nvfb=1 nvaccel=1"


def run(cfgs, model="iMacPro1,1", oc=True):
    s = SETUP.read_text()
    assert s.count(START) == 1 and s.count(END) == 1, "anchors moved in nullmoth-setup.sh"
    t = tempfile.mkdtemp()
    for d, (args, m) in cfgs.items():
        os.makedirs(os.path.join(t, d, "EFI/OC"))
        with open(os.path.join(t, d, "EFI/OC/config.plist"), "wb") as f:
            plistlib.dump({"NVRAM": {"Add": {"7C436110-AB2A-4BBB-A880-FE41995C9F82": {"boot-args": args}}},
                           "PlatformInfo": {"Generic": {"SystemProductName": m}}}, f)
    bins = os.path.join(t, "bin")
    os.makedirs(bins)
    nv = (f'case "$1" in *opencore-version) {"echo REL-108; exit 0" if oc else "exit 1"};; *) echo "boot-args\t{LIVE}";; esac')
    for name, body in (("nvram", nv), ("sysctl", f'echo "{model}"')):
        p = os.path.join(bins, name)
        with open(p, "w") as f:
            f.write("#!/bin/bash\n" + body + "\n")
        os.chmod(p, 0o755)
    script = (f'PATH="{bins}:/usr/bin:/bin"; ok() {{ echo "OK $*"; }}\n'
              f'mount_efi() {{ MOUNT_POINT="{t}/$1"; }}\nocrel_in() {{ echo EFI/OC; }}\n'
              f'found="{" ".join(cfgs)}"; BOOT_BOUND=0\n' + s[s.index(START):s.index(END)] + '\necho "RESULT $BOOT_BOUND $found"\n')
    r = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip().splitlines()[-1]


class BootArgsPick(unittest.TestCase):
    def test_the_one_config_matching_this_boots_bootargs_and_model_is_picked(self):
        self.assertEqual(run({"disk0s1": (LIVE, "iMacPro1,1"), "disk2s1": ("-v keepsyms=1", "iMacPro1,1")}), "RESULT 1 disk0s1")

    def test_two_identical_configs_still_stop_and_ask(self):
        self.assertEqual(run({"disk0s1": (LIVE, "iMacPro1,1"), "disk2s1": (LIVE, "iMacPro1,1")}), "RESULT 0 disk0s1 disk2s1")

    def test_matching_bootargs_with_another_model_is_not_picked(self):
        self.assertEqual(run({"disk0s1": (LIVE, "MacPro7,1"), "disk2s1": ("-v", "iMacPro1,1")}), "RESULT 0 disk0s1 disk2s1")


class SingleCandidate(unittest.TestCase):
    def test_the_only_opencore_partition_on_a_mac_opencore_started_is_picked(self):
        self.assertEqual(run({"disk0s2": ("-v", "MacPro7,1")}), "RESULT 1 disk0s2")

    def test_one_partition_without_opencore_having_started_the_mac_still_asks(self):
        self.assertEqual(run({"disk0s2": ("-v", "MacPro7,1")}, oc=False), "RESULT 0 disk0s2")


if __name__ == "__main__":
    unittest.main()
