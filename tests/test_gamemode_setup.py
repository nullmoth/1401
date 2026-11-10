"""setup --game-mode: runs the bundled service script with the two bundled files, off unless asked; removing the driver removes
Game Mode too. The service script is stubbed (its own tests belong to the macparity branch)."""
import pathlib
import subprocess
import tempfile
import sys
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


@unittest.skipUnless(sys.platform == "darwin", "runs macOS tools (bash, plutil); the Mac side is tested on a Mac")
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


@unittest.skipUnless(sys.platform == "darwin", "runs macOS tools (bash, plutil); the Mac side is tested on a Mac")
class CardAndFlagAgree(unittest.TestCase):
    """The Tools-tab card (GameMode.swift) and setup's --game-mode run the same bundled script with the same arguments."""
    SWIFT = (ROOT / "mac/Sources/GameMode.swift").read_text()

    def test_same_script_same_install_arguments_same_remove(self):
        self.assertIn('static let script = "nullmoth-gamemode-service.sh"', self.SWIFT)
        self.assertIn('static let policy = "nullmoth-gamemode-policy.py"', self.SWIFT)
        self.assertIn('static let indicator = "nullmoth-gamemode-indicator"', self.SWIFT)
        # card: [install, policy, indicator] / [remove]; flag: install <policy> <indicator> / remove
        self.assertIn('[op, resources.appendingPathComponent(policy).path, resources.appendingPathComponent(indicator).path]', self.SWIFT)
        self.assertIn('"$GS" install "$GD/nullmoth-gamemode-policy.py" "$GD/nullmoth-gamemode-indicator"', T)
        self.assertIn('/bin/bash "$GS" remove', T)
        self.assertIn("nullmoth-gamemode-service.sh", T)

    def test_the_flag_shows_the_scripts_own_status_line_which_the_card_parses_the_same_way(self):
        self.assertIn("parse(_ text: String)", self.SWIFT)
        self.assertIn('/bin/bash "$GS" status', T)

    def test_the_card_is_the_only_game_mode_control_in_the_window(self):
        page = (ROOT / "mac/Resources/index.html").read_text()
        self.assertEqual(page.count('id="gmcard"'), 1)
        app = (ROOT / "mac/Resources/app.js").read_text()
        self.assertNotIn('"--game-mode"', app)
        main = (ROOT / "mac/Sources/main.swift").read_text()
        self.assertNotIn('"--game-mode"', main)
