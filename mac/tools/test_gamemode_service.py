#!/usr/bin/env python3
"""nullmoth-gamemode-service.sh installs the Game Mode daemon and indicator under /Library/NullMoth/gamemode. Run against a
test prefix with a recording launchctl, so nothing real is installed or started."""
import os
import plistlib
import stat
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "Resources", "nullmoth-gamemode-service.sh")


class Env:
    def __init__(self, print_ok=True):
        self.prefix = tempfile.mkdtemp()
        self.log = os.path.join(self.prefix, "launchctl.log")
        self.lc = os.path.join(self.prefix, "launchctl")
        with open(self.lc, "w") as f:
            f.write('#!/bin/bash\necho "$@" >> "%s"\n[ "$1" = print ] && exit %d\nexit 0\n' % (self.log, 0 if print_ok else 1))
        os.chmod(self.lc, os.stat(self.lc).st_mode | stat.S_IXUSR)
        self.policy = os.path.join(self.prefix, "p.py")
        self.ind = os.path.join(self.prefix, "ind")
        for p in (self.policy, self.ind):
            with open(p, "w") as f:
                f.write("x\n")

    def run(self, *args):
        env = {"PATH": "/usr/bin:/bin", "NULLMOTH_GM_PREFIX": self.prefix + "/root", "NULLMOTH_GM_LAUNCHCTL": self.lc, "NULLMOTH_GM_PYTHON": "/usr/bin/true"}
        r = subprocess.run(["/bin/bash", SCRIPT, *args], capture_output=True, text=True, env=env)
        return r.returncode, r.stdout.strip()

    def calls(self):
        return open(self.log).read().splitlines() if os.path.exists(self.log) else []

    def path(self, p):
        return os.path.join(self.prefix, "root", p.lstrip("/"))


class Service(unittest.TestCase):
    def test_install_copies_the_two_files_writes_both_plists_and_loads_the_daemon(self):
        e = Env()
        rc, out = e.run("install", e.policy, e.ind)
        self.assertEqual((rc, out), (0, "installed"))
        for f in ("nullmoth-gamemode-policy.py", "nullmoth-gamemode-indicator"):
            self.assertTrue(os.access(e.path("/Library/NullMoth/gamemode/" + f), os.X_OK), f)
        with open(e.path("/Library/LaunchDaemons/com.nullmoth.gamemode.plist"), "rb") as f:
            d = plistlib.load(f)
        self.assertEqual(d["Label"], "com.nullmoth.gamemode")
        self.assertEqual(d["ProgramArguments"][1:], ["/Library/NullMoth/gamemode/nullmoth-gamemode-policy.py", "watch", "5"])
        self.assertTrue(d["KeepAlive"] and d["RunAtLoad"])
        with open(e.path("/Library/LaunchAgents/com.nullmoth.gamemode.indicator.plist"), "rb") as f:
            a = plistlib.load(f)
        self.assertEqual(a["ProgramArguments"], ["/Library/NullMoth/gamemode/nullmoth-gamemode-indicator"])
        self.assertEqual(a["LimitLoadToSessionType"], "Aqua")
        self.assertTrue(any(c.startswith("bootstrap system ") for c in e.calls()))

    def test_the_services_run_from_the_root_owned_folder_never_from_where_the_files_came_from(self):
        e = Env()
        e.run("install", e.policy, e.ind)
        with open(e.path("/Library/LaunchDaemons/com.nullmoth.gamemode.plist"), "rb") as f:
            args = plistlib.load(f)["ProgramArguments"]
        self.assertTrue(all(not a.startswith(e.prefix) for a in args))

    def test_remove_unloads_and_deletes_everything(self):
        e = Env()
        e.run("install", e.policy, e.ind)
        rc, out = e.run("remove")
        self.assertEqual((rc, out), (0, "removed"))
        self.assertFalse(os.path.exists(e.path("/Library/NullMoth/gamemode")))
        self.assertFalse(os.path.exists(e.path("/Library/LaunchDaemons/com.nullmoth.gamemode.plist")))
        self.assertFalse(os.path.exists(e.path("/Library/LaunchAgents/com.nullmoth.gamemode.indicator.plist")))
        self.assertTrue(any(c.startswith("bootout system/com.nullmoth.gamemode") for c in e.calls()))

    def test_status_reports_installed_and_running_or_not(self):
        e = Env(print_ok=True)
        self.assertEqual(e.run("status"), (0, "not installed , running"))
        e.run("install", e.policy, e.ind)
        self.assertEqual(e.run("status"), (0, "installed , running"))
        self.assertEqual(Env(print_ok=False).run("status"), (0, "not installed , stopped"))

    def test_install_with_a_missing_file_is_refused(self):
        e = Env()
        self.assertEqual(e.run("install", e.policy, "/nonexistent/x")[0], 2)

    def test_a_word_it_does_not_know_is_refused(self):
        self.assertEqual(Env().run("sideways")[0], 2)

    def test_without_a_prefix_and_without_root_install_and_remove_are_refused(self):
        if os.getuid() == 0:
            self.skipTest("running as root")
        r = subprocess.run(["/bin/bash", SCRIPT, "install", "a", "b"], capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
        self.assertEqual((r.returncode, r.stdout.strip()), (2, "install needs root"))


if __name__ == "__main__":
    unittest.main()
