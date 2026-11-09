"""setup --game-mode: runs the bundled service script with the two bundled files, off unless asked; removing the driver removes
Game Mode too. The service script is stubbed (its own tests belong to the macparity branch)."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
T = (ROOT / "mac/Resources/nullmoth-setup.sh").read_text()
a = T.index('if [ -n "${GAMEMODE:-}" ]; then')
BLOCK = T[a:T.index('if [ -n "${EXPER:-}" ]; then')]


def run(op, parts=("nullmoth-gamemode-service.sh", "nullmoth-gamemode-policy.py", "nullmoth-gamemode-indicator")):
    d = pathlib.Path(tempfile.mkdtemp())
    for p in parts:
        (d / p).write_text('#!/bin/bash\necho "$@" >> "$CALLS"\n' if p.endswith(".sh") else "x")
    calls = d / "calls"
    script = f'''stop() {{ echo "STOP $*"; exit 1; }}; ok() {{ echo "OK $*"; }}; cleanup() {{ :; }}; export CALLS={calls}; GAMEMODE={op}
set -- ; function dirname() {{ echo {d}; }}
{BLOCK}'''
    p = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=30)
    return p.stdout, (calls.read_text().splitlines() if calls.exists() else []), d


class GameMode(unittest.TestCase):
    def test_on_installs_with_the_two_bundled_files(self):
        out, calls, d = run("on")
        self.assertEqual(calls, [f"install {d.resolve()}/nullmoth-gamemode-policy.py {d.resolve()}/nullmoth-gamemode-indicator"], out)
        self.assertIn("OK Game Mode on", out)

    def test_off_removes_and_status_asks(self):
        self.assertEqual(run("off")[1], ["remove"])
        self.assertEqual(run("status")[1], ["status"])

    def test_missing_parts_or_an_unknown_word_install_nothing(self):
        out, calls, _ = run("on", parts=("nullmoth-gamemode-service.sh", "nullmoth-gamemode-policy.py"))
        self.assertIn("lacks the Game Mode parts", out); self.assertEqual(calls, [])
        self.assertIn("has no Game Mode service", run("on", parts=())[0])
        out, calls, _ = run("maybe")
        self.assertIn("takes on, off or status", out); self.assertEqual(calls, [])

    def test_removing_the_driver_removes_game_mode_and_nothing_is_on_by_default(self):
        self.assertIn('nullmoth-gamemode-service.sh" remove', T)
        self.assertNotIn('GAMEMODE=on', T.split("while [ $# -gt 0 ]")[0])


if __name__ == "__main__":
    unittest.main()
