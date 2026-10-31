"""Mac setup stops carry what the report needs (2.6.5 setup logs): the runtime refusal names the macOS this Mac runs,
and the unconfirmed-startup-partition stop prints OpenCore's boot-path and each candidate's identity, while the
"NOTE candidate <disk>" lines the app offers as choices stay exactly as they were."""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

SETUP = pathlib.Path(__file__).resolve().parents[1] / "mac/Resources/nullmoth-setup.sh"
START = '    if [ "$BOOT_BOUND" != 1 ]; then\n      for d in $found; do echo "NOTE candidate $d"; done'
END = "    EFI=${found# }"
# The setup runs under macOS's /bin/bash. Where there is none (the Windows CI runner, whose packaged check refuses
# skipped tests) the same arms read the lines from the script.
BASH = sys.platform != "win32" and os.path.exists("/bin/bash")


def candidate_stop():
    s = SETUP.read_text()
    assert s.count(START) == 1 and s.count(END) == 1, "anchors moved in nullmoth-setup.sh"
    block = s[s.index(START):s.index(END)]
    if not BASH:
        return block
    t = tempfile.mkdtemp()
    stubs = {"nvram": 'case "$1" in *boot-path) printf "x\\tPciRoot(0x0)/USB(0x16,0x0)/HD(1,MBR,0x0F8999F7,0x800,0x400880)/EFI";; *) exit 1;; esac',
             "diskutil": 'printf "   Disk / Partition UUID:     ABCD\\n   Partition Offset:          1048576 Bytes\\n   Device Location:           External\\n"'}
    for name, body in stubs.items():
        p = os.path.join(t, name)
        with open(p, "w") as f:
            f.write("#!/bin/bash\n" + body + "\n")
        os.chmod(p, 0o755)
    script = (f'PATH="{t}:/usr/bin:/bin"; stop() {{ echo "STOP $*"; exit 1; }}\n'
              'found=" disk1s1 disk3s1"; BOOT_BOUND=0\n' + block)
    r = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=30)
    return r.stdout


class SetupStopEvidence(unittest.TestCase):
    def test_the_candidate_stop_prints_the_boot_path_and_each_partition(self):
        out = candidate_stop()
        if BASH:
            self.assertIn("NOTE boot-path: PciRoot(0x0)/USB(0x16,0x0)/HD(1,MBR,0x0F8999F7", out)
            self.assertIn("NOTE partition disk3s1: Disk / Partition UUID=ABCD; Partition Offset=1048576 Bytes;", out)
            self.assertIn("STOP OpenCore's startup partition could not be confirmed", out)
        else:
            self.assertIn('echo "NOTE boot-path:', out)
            self.assertIn('echo "NOTE partition $d:', out)

    def test_the_choice_lines_the_app_reads_are_unchanged(self):
        out = candidate_stop()
        if BASH:
            lines = [l for l in out.splitlines() if l.startswith("NOTE candidate ")]
            self.assertEqual(lines, ["NOTE candidate disk1s1", "NOTE candidate disk3s1"])
        else:
            self.assertIn('for d in $found; do echo "NOTE candidate $d"; done', out)

    def test_the_runtime_refusal_names_this_macs_version(self):
        s = SETUP.read_text()
        line = next(l for l in s.splitlines() if l.startswith('/bin/bash "$RUNTIME_PREFLIGHT"'))
        self.assertIn("cannot load on macOS $(sw_vers -productVersion)", line)


if __name__ == "__main__":
    unittest.main()
