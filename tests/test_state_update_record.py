"""Send logs records what the macOS 26 update preparation left behind (driver issue #484): the user had to edit boot-args
by hand after updating, and the upload could not say whether the preparation or its finish step had run."""
import pathlib
import subprocess
import tempfile
import sys
import unittest

SETUP = pathlib.Path(__file__).resolve().parents[1] / "mac/Resources/nullmoth-setup.sh"
TEXT = SETUP.read_text()


def block():
    a = TEXT.index('    echo; echo "== macOS update record')
    b = TEXT.index("\n", TEXT.index('echo "-nvoff in NVRAM boot-args:', a))
    return TEXT[a:b + 1]


def run(files, bootargs):
    st = pathlib.Path(tempfile.mkdtemp())
    for name, body in files.items():
        (st / name).write_text(body)
    stubs = ("sw_vers() { echo 26.7.2; }\n"
             f"nvram() {{ [ \"$1\" = boot-args ] && printf 'boot-args\\t%s\\n' '{bootargs}'; }}\n")
    out = subprocess.run(["/bin/bash", "-c", stubs + f"ST='{st}'\n{{\n" + block() + "}\n"],
                         capture_output=True, text=True, timeout=30)
    return out.stdout + out.stderr


class UpdateRecord(unittest.TestCase):
    def test_a_parked_mac_shows_the_pending_update_and_nvoff(self):
        text = run({"update-pending": "FROM=15\nBAR0=-1\n", "os-major": "15\n"}, "nvfb=1 -nvoff -v")
        self.assertIn("running macOS major: 26; set up for: 15", text)
        self.assertIn("  FROM=15", text)
        self.assertIn("osupdate.log: absent", text)
        self.assertIn("-nvoff in NVRAM boot-args: yes", text)

    def test_a_finished_update_says_none_and_no(self):
        text = run({"os-major": "26\n", "osupdate.log": "a\nb\n"}, "nvfb=1 nvaccel=1")
        self.assertIn("update-pending: (none)", text)
        self.assertIn("osupdate.log: 2 lines", text)
        self.assertIn("-nvoff in NVRAM boot-args: no", text)
        self.assertNotIn("not found", text)

def load_tests(loader, tests, pattern):
    """These tests run the Mac side (bash and macOS tools), so they are collected on a Mac only: the Windows package
    check counts a skipped test as a failure, and the Mac release step runs them."""
    return tests if sys.platform == "darwin" else unittest.TestSuite()


if __name__ == "__main__":
    unittest.main()
