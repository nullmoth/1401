#!/usr/bin/env python3
"""Every script setup runs with [ -x ] reaches the app bundle executable.

nullmoth-setup.sh refuses the installer unless it is executable. A source file committed without its execute bit made
every install through the app stop ("the audited installer is missing from the app"). This checks both layers: the mode
git records for the scripts, and that app/build.sh sets 755 on each of them after copying the resources.
"""
import pathlib
import subprocess
import unittest
import os as _os, pathlib as _pl
# the NVIDIA driver checkout these app/driver contract tests read (NULLMOTH_DRIVER, else the sibling driver/)
DRV = _pl.Path(_os.environ.get("NULLMOTH_DRIVER") or _pl.Path(__file__).resolve().parents[3] / "driver")

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ["nullmoth-setup.sh", "nullmoth-uninstall.sh", "nullmoth-runtime-check.sh"]


class ScriptsExecutable(unittest.TestCase):
    def test_build_sets_755_on_every_script_setup_runs(self):
        build = (ROOT / "build.sh").read_text()
        for name in SCRIPTS:
            self.assertRegex(build, r'chmod 755 [^\n]*"\$APP/Contents/Resources/' + name.replace(".", r"\.") + '"',
                             f"build.sh does not chmod 755 {name}")

    def test_the_installers_are_recorded_executable(self):
        for repo, rel in [(ROOT, "Resources/nullmoth-uninstall.sh"), (DRV, "package/install.sh"), (DRV, "package/uninstall.sh")]:
            mode = subprocess.run(["git", "-C", str(repo), "ls-files", "-s", rel], capture_output=True, text=True).stdout.split()
            self.assertTrue(mode, f"{rel} is not tracked")
            self.assertEqual(mode[0], "100755", f"{rel} is tracked as {mode[0]}, not 100755")


if __name__ == "__main__":
    unittest.main()
