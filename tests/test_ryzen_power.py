"""mac/Resources/nullmoth-ryzen-power.sh: the LaunchDaemon it writes, and every input it refuses."""
import os
import plistlib
import subprocess
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "mac", "Resources", "nullmoth-ryzen-power.sh")


def run(root, *args):
    env = dict(os.environ, NM_ROOT=root)
    return subprocess.run(["/bin/bash", SCRIPT, *args], capture_output=True, text=True, env=env)


def plist(root):
    with open(os.path.join(root, "Library/LaunchDaemons/com.nullmoth.ryzen-power.plist"), "rb") as fh:
        return plistlib.load(fh)


class RyzenPower(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def test_the_default_profile_is_a_quiet_battery_profile_in_milliwatts(self):
        r = run(self.root, "install")
        self.assertEqual(r.returncode, 0, r.stderr)
        p = plist(self.root)
        self.assertEqual(p["ProgramArguments"][0], "/usr/local/bin/ryzenadj")
        self.assertEqual(p["ProgramArguments"][1:],
                         ["--stapm-limit=13000", "--slow-limit=14000", "--fast-limit=15000", "--tctl-temp=70", "--power-saving"])
        self.assertTrue(p["RunAtLoad"])
        self.assertEqual(p["StartInterval"], 30)

    def test_chosen_limits_and_a_binary_path_are_written(self):
        r = run(self.root, "install", "--stapm", "25", "--slow", "28", "--fast", "35", "--temp", "85", "--ryzenadj", "/opt/ryzenadj/bin/ryzenadj")
        self.assertEqual(r.returncode, 0, r.stderr)
        a = plist(self.root)["ProgramArguments"]
        self.assertEqual((a[0], a[1], a[2], a[3], a[4]), ("/opt/ryzenadj/bin/ryzenadj", "--stapm-limit=25000", "--slow-limit=28000",
                                                           "--fast-limit=35000", "--tctl-temp=85"))

    def test_bad_input_is_refused_and_nothing_is_written(self):
        for args in (["--stapm", "4"], ["--fast", "66"], ["--stapm", "abc"], ["--temp", "101"], ["--temp", ""],
                     ["--stapm", "20", "--slow", "15"], ["--slow", "30", "--fast", "20"], ["--ryzenadj", "relative/ryzenadj"],
                     ["--ryzenadj", "/tmp/a<b"], ["--bogus"]):
            r = run(self.root, "install", *args)
            self.assertNotEqual(r.returncode, 0, args)
            self.assertFalse(os.path.exists(os.path.join(self.root, "Library/LaunchDaemons/com.nullmoth.ryzen-power.plist")), args)

    def test_status_and_remove(self):
        self.assertIn("not installed", run(self.root, "status").stdout)
        run(self.root, "install", "--stapm", "20", "--slow", "20", "--fast", "20")
        s = run(self.root, "status").stdout
        self.assertIn("installed", s)
        self.assertIn("--stapm-limit=20000", s)
        self.assertEqual(run(self.root, "remove").returncode, 0)
        self.assertIn("not installed", run(self.root, "status").stdout)

    def test_a_reinstall_replaces_the_profile_whole(self):
        run(self.root, "install", "--stapm", "30", "--slow", "30", "--fast", "30")
        run(self.root, "install")
        self.assertIn("--stapm-limit=13000", plist(self.root)["ProgramArguments"])


if __name__ == "__main__":
    unittest.main()
