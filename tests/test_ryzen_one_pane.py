"""The Ryzen power profile has one path: the page, the app, setup's --ryzen-power on|off|status with --ryzen-limits, the
pinned RyzenAdj the package carries. nullmoth-ryzen-power.sh stays because setup calls it to install and remove the job."""
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SETUP = (ROOT / "mac/Resources/nullmoth-setup.sh").read_text()
SWIFT = {p.name: p.read_text() for p in (ROOT / "mac/Sources").glob("*.swift")}
PAGE = (ROOT / "mac/Resources/index.html").read_text()


class OnePane(unittest.TestCase):
    def test_the_old_install_route_is_gone_everywhere(self):
        for name, text in SWIFT.items():
            self.assertNotIn("ryzenAction", text, name)
            self.assertNotIn("ryzenArguments", text, name)
            self.assertNotIn('"--ryzenadj"', text, name)        # the app never names a RyzenAdj build: setup uses the pinned one
        self.assertNotIn("ryinstall", PAGE)

    def test_the_script_has_exactly_one_caller_and_it_is_setup(self):
        callers = []
        for p in list((ROOT / "mac").rglob("*")) + list((ROOT / "tests").glob("*.py")):
            if p.is_file() and p.suffix in (".sh", ".swift", ".js", ".html", ".py") and p.name != "nullmoth-ryzen-power.sh":
                if "nullmoth-ryzen-power.sh" in p.read_text(errors="replace") and not p.name.startswith("test_"):
                    callers.append(p.name)
        self.assertEqual(sorted(set(callers)), ["nullmoth-setup.sh"])

    def test_setup_accepts_on_off_and_status(self):
        self.assertIn('--ryzen-power takes on, off or status', SETUP)
        self.assertIn('[ "$RYZEN" = status ]', SETUP)

    def test_status_changes_nothing_and_names_the_four_facts(self):
        a = SETUP.index('  if [ "$RYZEN" = status ]; then')
        block = SETUP[a:SETUP.index("  fi\n", a) + 5]
        for fact in ("record:", "NMSMN kext installed", "nmsmn=1 in NVRAM", "job:"):
            self.assertIn(fact, block)
        for writer in ("plutil -replace", "nvram boot-args=", "kmutil create", "rm -rf", " ra add", "ditto"):
            self.assertNotIn(writer, block)
        script = ("note() { :; }; ok() { echo \"OK $*\"; }; cleanup() { :; }; RYZEN=status; ST=%s; RPW=/nonexistent\n" % tempfile.mkdtemp()
                  + SETUP[SETUP.index('  EXT=/Library/Extensions; RK=$EXT/NMSMN.kext; RREC=$ST/ryzen-power'):a] + block)
        p = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=30)
        self.assertIn("NOTE record:", p.stdout)
        self.assertIn("OK Ryzen power profile status shown", p.stdout)


if __name__ == "__main__":
    unittest.main()
