#!/usr/bin/env python3
"""setup --autologin-off turns off only the automatic login 1401's Recovery script created (named in its marker file)."""
import pathlib
import subprocess
import tempfile
import unittest

T = (pathlib.Path(__file__).resolve().parents[1] / "Resources/nullmoth-setup.sh").read_text()
a = T.index('if [ "${AUTOLOGINOFF:-0}" = 1 ]; then')
BLOCK = T[a:T.index('  cleanup; echo "RESULT ok"; exit 0\nfi\n', a) + len('  cleanup; echo "RESULT ok"; exit 0\nfi\n')]


def go(marker, current):
    t = pathlib.Path(tempfile.mkdtemp())
    m, kc = t / "marker", t / "kcpassword"
    kc.write_text("x")
    if marker is not None:
        m.write_text(marker + "\n")
    blk = BLOCK.replace("/private/var/db/.nullmoth-autologin", str(m)).replace("/etc/kcpassword", str(kc))
    script = ('ok() { echo "OK $*"; }; stop() { echo "STOP $*"; exit 1; }; cleanup() { :; }; AUTOLOGINOFF=1\n'
              'defaults() { case "$1" in read) echo "%s";; delete) echo DELETED >> %s/calls;; esac; }\n' % (current, t) + blk)
    p = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=30)
    return p.stdout, m.exists(), kc.exists(), (t / "calls").exists()


class AutologinOff(unittest.TestCase):
    def test_the_login_1401_made_is_turned_off_with_its_password_file(self):
        out, marker, kc, deleted = go("alex", "alex")
        self.assertEqual((marker, kc, deleted), (False, False, True), out)

    def test_a_login_the_user_made_is_not_touched(self):
        out, marker, kc, deleted = go("alex", "someoneelse")
        self.assertEqual((marker, kc, deleted), (False, True, False), out)

    def test_no_marker_means_nothing_to_do(self):
        out, marker, kc, deleted = go(None, "alex")
        self.assertEqual((kc, deleted), (True, False), out)


if __name__ == "__main__":
    unittest.main()
