"""mac/Resources/nullmoth-ryzen-power.sh: the LaunchDaemon it writes, and every input it refuses."""
import os
import plistlib
import subprocess
import tempfile
import unittest
import hashlib
import stat

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "mac", "Resources", "nullmoth-ryzen-power.sh")


def run(root, *args):
    env = dict(os.environ, NM_ROOT=root, NM_TRUST_UID=str(os.getuid()))
    return subprocess.run(["/bin/bash", SCRIPT, *args], capture_output=True, text=True, env=env)


def plist(root):
    with open(os.path.join(root, "Library/LaunchDaemons/com.nullmoth.ryzen-power.plist"), "rb") as fh:
        return plistlib.load(fh)


class RyzenPower(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.src = os.path.join(os.path.realpath(tempfile.mkdtemp()), "ryzenadj")
        with open(self.src, "wb") as fh:
            fh.write(b"#!/bin/sh\necho ryzenadj\n")
        os.chmod(self.src, 0o755)
        self.sha = hashlib.sha256(open(self.src, "rb").read()).hexdigest()

    def install(self, *args, src=None, sha=None):
        return run(self.root, "install", "--ryzenadj", src or self.src, "--sha256", sha or self.sha, *args)

    def dest(self):
        return os.path.join(self.root, "Library/PrivilegedHelperTools/ryzenadj")

    def installed(self):
        return os.path.exists(os.path.join(self.root, "Library/LaunchDaemons/com.nullmoth.ryzen-power.plist"))

    def test_the_default_profile_is_a_quiet_battery_profile_in_milliwatts(self):
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        p = plist(self.root)
        self.assertEqual(p["ProgramArguments"][0], self.dest())
        self.assertEqual(p["ProgramArguments"][1:],
                         ["--stapm-limit=13000", "--slow-limit=14000", "--fast-limit=15000", "--tctl-temp=70", "--power-saving"])
        self.assertTrue(p["RunAtLoad"])
        self.assertEqual(p["StartInterval"], 30)

    def test_chosen_limits_and_a_binary_path_are_written(self):
        r = self.install("--stapm", "25", "--slow", "28", "--fast", "35", "--temp", "85")
        self.assertEqual(r.returncode, 0, r.stderr)
        a = plist(self.root)["ProgramArguments"]
        self.assertEqual((a[0], a[1], a[2], a[3], a[4]), (self.dest(), "--stapm-limit=25000", "--slow-limit=28000",
                                                           "--fast-limit=35000", "--tctl-temp=85"))

    def test_bad_input_is_refused_and_nothing_is_written(self):
        for args in (["--stapm", "4"], ["--fast", "66"], ["--stapm", "abc"], ["--temp", "101"], ["--temp", ""],
                     ["--stapm", "20", "--slow", "15"], ["--slow", "30", "--fast", "20"], ["--bogus"]):
            r = self.install(*args)
            self.assertNotEqual(r.returncode, 0, args)
            self.assertFalse(self.installed(), args)

    def test_status_and_remove(self):
        self.assertIn("not installed", run(self.root, "status").stdout)
        self.install("--stapm", "20", "--slow", "20", "--fast", "20")
        s = run(self.root, "status").stdout
        self.assertIn("installed", s)
        self.assertIn("--stapm-limit=20000", s)
        self.assertEqual(run(self.root, "remove").returncode, 0)
        self.assertIn("not installed", run(self.root, "status").stdout)

    def test_a_reinstall_replaces_the_profile_whole(self):
        self.install("--stapm", "30", "--slow", "30", "--fast", "30")
        self.install()
        self.assertIn("--stapm-limit=13000", plist(self.root)["ProgramArguments"])

    def test_the_job_runs_a_verified_root_owned_copy_not_the_users_file(self):
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(plist(self.root)["ProgramArguments"][0], self.dest())
        self.assertNotEqual(self.dest(), self.src)
        self.assertEqual(stat.S_IMODE(os.stat(self.dest()).st_mode), 0o755)
        self.assertEqual(hashlib.sha256(open(self.dest(), "rb").read()).hexdigest(), self.sha)
        with open(self.src, "ab") as fh:        # changing the original afterwards changes nothing that runs
            fh.write(b"evil")
        self.assertEqual(hashlib.sha256(open(self.dest(), "rb").read()).hexdigest(), self.sha)

    def test_a_binary_that_does_not_match_the_hash_is_refused(self):
        r = self.install(sha="0" * 64)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.installed())
        self.assertFalse(os.path.exists(self.dest()))
        self.assertNotEqual(run(self.root, "install", "--ryzenadj", self.src).returncode, 0)   # no hash at all

    def test_a_symlinked_binary_or_path_is_refused(self):
        link = os.path.join(os.path.dirname(self.src), "link")
        os.symlink(self.src, link)
        self.assertNotEqual(self.install(src=link).returncode, 0)
        d = os.path.join(os.path.dirname(os.path.dirname(self.src)), "dirlink")
        os.symlink(os.path.dirname(self.src), d)
        self.assertNotEqual(self.install(src=os.path.join(d, "ryzenadj")).returncode, 0)
        self.assertFalse(self.installed())

    def test_a_destination_directory_others_can_write_is_refused(self):
        d = os.path.join(self.root, "Library/PrivilegedHelperTools")
        os.makedirs(d)
        os.chmod(d, 0o777)
        r = self.install()
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.installed())
        self.assertFalse(os.path.exists(self.dest()))
        os.chmod(d, 0o755)
        os.chmod(os.path.join(self.root, "Library"), 0o775 | 0o002)
        self.assertNotEqual(self.install().returncode, 0)

    def test_a_directory_owned_by_someone_else_is_refused(self):
        env = dict(os.environ, NM_ROOT=self.root, NM_TRUST_UID=str(os.getuid() + 12345))
        r = subprocess.run(["/bin/bash", SCRIPT, "install", "--ryzenadj", self.src, "--sha256", self.sha], capture_output=True, text=True, env=env)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(self.dest()))


if __name__ == "__main__":
    unittest.main()
