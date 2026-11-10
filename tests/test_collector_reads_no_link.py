"""Send logs runs as root and reads logs by fixed names, some in /var/tmp where any account can create files. A link
planted under one of those names would put a root-only file's contents into the report. The reader refuses a link."""
import pathlib
import subprocess
import tempfile
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
T = (ROOT / "mac/Resources/nullmoth-setup.sh").read_text()
a = T.index("m27_tail() {")
FUNC = T[a:T.index("\n}\n", a) + 3]


def tail(root, path):
    script = f'M27_ROOT="{root}"\n{FUNC}\nm27_tail "label" {path} 1000\n'
    return subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=30).stdout


class Reader(unittest.TestCase):
    def setUp(self):
        self.t = pathlib.Path(tempfile.mkdtemp())
        (self.t / "var/tmp").mkdir(parents=True)
        self.secret = self.t / "secret"; self.secret.write_text("ROOT-ONLY-CONTENT\n")

    def test_a_planted_link_is_not_read(self):
        (self.t / "var/tmp/ws-gate.log").symlink_to(self.secret)
        out = tail(self.t, "/var/tmp/ws-gate.log")
        self.assertIn("a link, not a log", out)
        self.assertNotIn("ROOT-ONLY-CONTENT", out)

    def test_a_real_log_is_read(self):
        (self.t / "var/tmp/ws-gate.log").write_text("gate passed\n")
        self.assertIn("gate passed", tail(self.t, "/var/tmp/ws-gate.log"))

    def test_control_the_reader_before_the_change_followed_the_link(self):
        old = FUNC.replace('  if [ -L "$f" ]; then echo "(a link, not a log: not read)"   # some of these names are in folders any account can write\n  elif [ ! -e "$f" ]', '  if [ ! -e "$f" ]')
        self.assertNotEqual(old, FUNC)
        (self.t / "var/tmp/ws-gate.log").symlink_to(self.secret)
        script = f'M27_ROOT="{self.t}"\n{old}\nm27_tail "label" /var/tmp/ws-gate.log 1000\n'
        out = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=30).stdout
        self.assertIn("ROOT-ONLY-CONTENT", out)

def load_tests(loader, tests, pattern):
    """These tests run the Mac side (bash and macOS tools), so they are collected on a Mac only: the Windows package
    check counts a skipped test as a failure, and the Mac release step runs them."""
    return tests if sys.platform == "darwin" else unittest.TestSuite()


if __name__ == "__main__":
    unittest.main()
