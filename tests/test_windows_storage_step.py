"""The Windows window's storage step: the plan joins the summary, Prepare / Finish / Undo call `p1401 storage-prep`, and the
buttons follow whether Prepare has run (its state file). The C# is built on the mini; these arms pin it to the engine."""
import json
import pathlib
import re
import unittest

from p1401 import storage_prep

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = (ROOT / "windows/App/MainForm.cs").read_text(encoding="utf-8")
MAIN = (ROOT / "p1401/__main__.py").read_text()


class StorageStep(unittest.TestCase):
    def test_the_three_buttons_call_the_engines_three_actions(self):
        choices = re.search(r'sp.add_argument\("action", choices=\(([^)]*)\)', MAIN).group(1)
        self.assertEqual(re.findall(r'"(\w+)"', choices), ["prepare", "finish", "undo"])
        for a in ("prepare", "finish", "undo"):
            self.assertIn(f'RunStorage("{a}"', SRC)
        self.assertIn('"p1401 storage-prep " + action', SRC)

    def test_prepare_and_undo_ask_first_and_finish_does_not(self):
        self.assertRegex(SRC, r'RunStorage\("prepare", Loc\.T\(')
        self.assertRegex(SRC, r'RunStorage\("undo", Loc\.T\(')
        self.assertIn('RunStorage("finish", null)', SRC)

    def test_button_states_follow_the_state_file(self):
        self.assertIn("storPrepare.Enabled = !StoragePrepared() && !busy;", SRC)
        self.assertIn("storFinish.Enabled = StoragePrepared() && !busy;", SRC)
        self.assertIn("storUndo.Enabled = StoragePrepared() && !busy;", SRC)
        # the file the window reads is the file the engine writes
        self.assertIn('"NullMoth", "1401", "storage-prep.json"', SRC)
        self.assertIn('"NullMoth", "1401", "storage-prep.json"', MAIN)

    def test_undo_is_on_the_page_whenever_prepare_has_run_even_when_the_plan_is_gone(self):
        self.assertIn("if (StoragePrepared()) { if (!onPage.Contains(storPrepare))", SRC)
        self.assertIn("onPage.Add(storUndo)", SRC)
        # Prepare and Finish show only for a build whose plan is "turn VMD off"
        self.assertIn('if (built && StorageVmdPlan()) { onPage.Add(storPrepare); onPage.Add(storFinish); }', SRC)

    def test_the_plan_the_engine_returns_is_what_the_window_reads(self):
        plan = storage_prep.plan({"Motherboard": {"Name": "ASUS PRIME"}}, "vmd-off", ["VMD (8086-467F)"])
        for key in ("kind", "steps", "bios_path"):
            self.assertIn(key, plan)
            self.assertIn(f'plan["{key}"]' if key != "steps" else 'plan.ContainsKey("steps")', SRC)
        self.assertIn("undoable", plan)   # the window does not read it: Undo follows the state file, not the plan
        self.assertEqual(plan["kind"], "vmd-off")
        self.assertTrue(plan["undoable"] and plan["steps"] and plan["bios_path"])
        ext = storage_prep.plan({}, "external-drive")
        self.assertEqual((ext["kind"], ext["undoable"], ext["bios_path"]), ("external-drive", False, ""))
        json.dumps(plan)

    def test_the_external_drive_checkbox_passes_the_flag_and_is_worded_as_an_install_target(self):
        self.assertIn('(externalTarget.Checked ? " --external-target" : "")', SRC)
        self.assertIn("Install macOS on an external drive", SRC)


if __name__ == "__main__":
    unittest.main()
