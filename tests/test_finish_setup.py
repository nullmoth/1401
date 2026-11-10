"""The Recovery script that finishes a new macOS install without the setup screens (issue #86).

macOS 26 cannot draw its first setup screens without a graphics driver: black screen, cursor only, and the NVIDIA
driver can only be installed once macOS is running. p1401/finish-setup.sh makes the first account from Recovery
(the same dscl steps support walked users through by hand on 11-03, which worked), marks setup done and logs in by
itself. It runs here against a fake Data volume with dscl, diskutil, chown, defaults and stty replaced. The writer
puts it on the stick."""
import os
import stat
import subprocess
import tempfile
import sys
import unittest
from pathlib import Path

from p1401 import usbwriter

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "p1401" / "finish-setup.sh"
USER = "testuser"  # the account the tests make
ACCT = "/Local/Default/Users/" + USER
KEY = [125, 137, 82, 35, 210, 188, 221, 234, 163, 185, 31]

FAKES = {
    # dscl -f <node> localhost <verb> ...: logged; -read UniqueID answers from users/<name>.uid; FAIL_VERB fails a verb
    "dscl": r'''#!/bin/bash
echo "dscl $*" >> "$T/calls"
shift 3
verb=$1
if [ "$verb" = -read ]; then f="$NODE/users/${2##*/}.uid"; [ -f "$f" ] && echo "UniqueID: $(cat "$f")"; exit 0; fi
[ -n "${FAIL_VERB:-}" ] && [ "$verb" = "$FAIL_VERB" ] && exit 1
exit 0''',
    "chown": '#!/bin/bash\necho "chown $*" >> "$T/calls"\nexit 0',
    "defaults": '#!/bin/bash\necho "defaults $*" >> "$T/calls"\nexit 0',
    "stty": '#!/bin/bash\nexit 0',
    "diskutil": r'''#!/bin/bash
echo "diskutil $*" >> "$T/calls"
case "$1 $2" in
  "apfs list") printf '|   |   APFS Volume Disk (Role):   disk4s1 (Data)\n|   |   Name:                      MacOS - Data (Case-insensitive)\n|   |   APFS Volume Disk (Role):   disk4s2 (Recovery)\n';;
  "info disk4s1") [ -f "$T/mounted" ] && echo "   Mount Point:               $DATAVOL";;
  "info disk4s2") echo "   Mount Point:               /System/Volumes/Recovery";;
  "mount disk4s1") : > "$T/mounted";;
esac
exit 0''',
}


def decode_kcpassword(data):
    out = bytes(b ^ KEY[i % 11] for i, b in enumerate(data))
    return out.split(b"\0", 1)[0]


class FinishSetup(unittest.TestCase):
    def make(self, users=None):
        t = Path(tempfile.mkdtemp(prefix="finish-"))
        fake = t / "bin"
        fake.mkdir()
        for name, body in FAKES.items():
            p = fake / name
            p.write_text(body + "\n")
            p.chmod(p.stat().st_mode | stat.S_IXUSR)
        data = t / "MacOS - Data"
        node = data / "private/var/db/dslocal/nodes/Default"
        (node / "users").mkdir(parents=True)
        (data / "private/etc").mkdir(parents=True)
        (data / "Library/Preferences").mkdir(parents=True)
        (data / "Users").mkdir()
        for name, uid in (users or {"root": 0, "daemon": 1, "_mbsetupuser": 248}).items():
            (node / "users" / f"{name}.plist").write_text("")
            (node / "users" / f"{name}.uid").write_text(str(uid))
        return t, data, node

    def run_script(self, t, data, node, args, stdin="secret\nsecret\n", env=None):
        e = dict(os.environ, T=str(t), NODE=str(node), DATAVOL=str(data), PATH=f"{t / 'bin'}:/usr/bin:/bin:/usr/sbin:/sbin")
        e.update(env or {})
        p = subprocess.run(["/bin/bash", str(SCRIPT), *args], input=stdin, capture_output=True, text=True, env=e,
                           timeout=60)
        calls = (t / "calls").read_text() if (t / "calls").exists() else ""
        return p, calls

    def test_new_install_gets_an_admin_account_and_skips_setup(self):
        t, data, node = self.make()
        p, calls = self.run_script(t, data, node, ["--data", str(data), "--user", USER, "--name", "Alex Doe"])
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn(f"-create {ACCT} UniqueID 501", calls)
        self.assertIn(f"-create {ACCT} PrimaryGroupID 20", calls)
        self.assertIn(f"-create {ACCT} NFSHomeDirectory /Users/{USER}", calls)
        self.assertIn(f"-passwd {ACCT} secret", calls)
        self.assertIn(f"-append /Local/Default/Groups/admin GroupMembership {USER}", calls)
        self.assertRegex(calls, r"GeneratedUID [0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}")
        self.assertTrue((data / "private/var/db/.AppleSetupDone").exists())
        self.assertTrue((data / "Users" / USER).is_dir())

    def test_logs_in_by_itself(self):
        t, data, node = self.make()
        for pw in ("secret", "twelve-chars", "a"):
            with self.subTest(pw=pw):
                (data / "private/var/db/.AppleSetupDone").unlink(missing_ok=True)
                p, calls = self.run_script(t, data, node, ["--data", str(data), "--user", USER], stdin=f"\n{pw}\n{pw}\n")
                self.assertEqual(p.returncode, 0, p.stdout)
                kc = (data / "private/etc/kcpassword").read_bytes()
                self.assertEqual(len(kc) % 12, 0, kc)
                self.assertGreater(len(kc), len(pw), "a NUL terminator always follows the password")
                self.assertEqual(decode_kcpassword(kc), pw.encode())
                self.assertIn(f"com.apple.loginwindow autoLoginUser {USER}", calls)

    def test_no_autologin_writes_no_password_file(self):
        t, data, node = self.make()
        p, calls = self.run_script(t, data, node, ["--data", str(data), "--user", USER, "--name", "A", "--no-autologin"])
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertFalse((data / "private/etc/kcpassword").exists())
        self.assertNotIn("autoLoginUser", calls)

    def test_a_system_that_is_set_up_is_left_alone(self):
        t, data, node = self.make()
        (data / "private/var/db/.AppleSetupDone").write_text("")
        p, calls = self.run_script(t, data, node, ["--data", str(data), "--user", USER, "--name", "A"])
        self.assertEqual(p.returncode, 1)
        self.assertIn("already finished", p.stdout)
        self.assertNotIn("-create", calls)

    def test_a_system_with_an_account_is_left_alone(self):
        t, data, node = self.make({"root": 0, "jamie": 501})
        p, calls = self.run_script(t, data, node, ["--data", str(data), "--user", USER, "--name", "A"])
        self.assertEqual(p.returncode, 1)
        self.assertIn("already has an account (jamie)", p.stdout)
        self.assertNotIn("-create", calls)
        self.assertFalse((data / "private/var/db/.AppleSetupDone").exists())

    def test_bad_names_and_passwords_change_nothing(self):
        for args, stdin, word in ((["--user", "Alex"], "x\nx\n", "lower-case"), (["--user", "9lives"], "x\nx\n", "start"),
                                  (["--user", "root"], "x\nx\n", "macOS uses"), (["--user", USER], "x\ny\n", "differ"),
                                  (["--user", USER], "\n\n", "empty")):
            with self.subTest(args=args, word=word):
                t, data, node = self.make()
                p, calls = self.run_script(t, data, node, ["--data", str(data), "--name", "A", *args], stdin=stdin)
                self.assertEqual(p.returncode, 1, p.stdout)
                self.assertIn(word, p.stdout)
                self.assertNotIn("-create", calls)
                self.assertFalse((data / "private/var/db/.AppleSetupDone").exists())

    def test_a_name_with_a_newline_is_refused_and_autologin_leaves_a_marker_and_a_warning(self):
        t, data, node = self.make()
        p, calls = self.run_script(t, data, node, ["--data", str(data), "--name", "A", "--user", "alex\nBad Name"], stdin="x\nx\n")
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertIn("one line", p.stdout)
        self.assertNotIn("-create", calls)
        t, data, node = self.make()
        p, calls = self.run_script(t, data, node, ["--data", str(data), "--user", USER], stdin="\nsecret\nsecret\n")
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertEqual((data / "private/var/db/.nullmoth-autologin").read_text(), USER + "\n")
        self.assertIn("anyone who can read this disk", p.stdout)

    def test_a_failed_write_removes_the_partial_account(self):
        t, data, node = self.make()
        p, calls = self.run_script(t, data, node, ["--data", str(data), "--user", USER, "--name", "A"],
                                   env={"FAIL_VERB": "-passwd"})
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertIn(f"-delete {ACCT}", calls)
        self.assertFalse((data / "private/var/db/.AppleSetupDone").exists())
        self.assertFalse((data / "private/etc/kcpassword").exists())

    def test_finds_and_mounts_the_data_volume_by_itself(self):
        t, data, node = self.make()
        p, calls = self.run_script(t, data, node, ["--user", USER, "--name", "A"])
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("diskutil mount disk4s1", calls)
        self.assertNotIn("diskutil mount disk4s2", calls, "Recovery's own volume is not an install")
        self.assertTrue((data / "private/var/db/.AppleSetupDone").exists())

    def test_the_stick_carries_the_script(self):
        root = Path(tempfile.mkdtemp(prefix="stick-"))
        dst = Path(usbwriter.copy_finish_setup(str(root)))
        self.assertEqual(dst, root / "NullMoth" / "finish-setup.sh")
        self.assertEqual(dst.read_bytes(), SCRIPT.read_bytes())

    def test_negative_control_the_28_stick_had_no_way_past_the_setup_screens(self):
        old = subprocess.run(["git", "-C", str(ROOT), "show", "003c087:p1401/usbwriter.py"], capture_output=True, text=True)
        self.assertEqual(old.returncode, 0, old.stderr)
        self.assertNotIn("finish-setup", old.stdout)
        gone = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", "003c087:p1401/finish-setup.sh"], capture_output=True)
        self.assertNotEqual(gone.returncode, 0)

def load_tests(loader, tests, pattern):
    """These tests run the Mac side (bash and macOS tools), so they are collected on a Mac only: the Windows package
    check counts a skipped test as a failure, and the Mac release step runs them."""
    return tests if sys.platform == "darwin" else unittest.TestSuite()


if __name__ == "__main__":
    unittest.main()
