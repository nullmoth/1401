#!/usr/bin/env python3
"""nullmoth-gamemode-policy.py: what counts as a game, what is raised and demoted, and that everything is undone. The system
tools are replaced by a recording runner, so nothing real is touched."""
import importlib.util
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("gm", os.path.join(HERE, "..", "Resources", "nullmoth-gamemode-policy.py"))
gm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gm)


class Runner:
    """Answers ps for nice values and records every other command; commands for pids in `fail` fail."""

    def __init__(self, nice=0, fail=()):
        self.calls, self.nice, self.fail = [], nice, set(fail)

    def __call__(self, cmd):
        self.calls.append(cmd)
        if cmd[0].endswith("/ps") and "nice=" in cmd:
            return subprocess.CompletedProcess(cmd, 0, f"  {self.nice}\n", "")
        pid = cmd[-1]
        return subprocess.CompletedProcess(cmd, 1 if pid in self.fail else 0, "", "")


class Policy(unittest.TestCase):
    def test_the_games_category_or_an_opt_in_makes_a_bundle_a_game(self):
        self.assertTrue(gm.is_game({"LSApplicationCategoryType": "public.app-category.games"}))
        self.assertTrue(gm.is_game({"LSSupportsGameMode": True}))
        self.assertFalse(gm.is_game({"LSApplicationCategoryType": "public.app-category.productivity"}))
        self.assertFalse(gm.is_game({"LSSupportsGameMode": False}))
        self.assertFalse(gm.is_game(None))

    def test_only_listed_background_jobs_are_demoted_never_the_game_or_other_apps(self):
        procs = [(10, "mds_stores"), (11, "Safari"), (12, "photoanalysisd"), (13, "TheGame"), (14, "mds_stores")]
        acts = gm.plan(13, procs)
        self.assertEqual(acts[0], ("raise", 13))
        self.assertEqual(sorted(p for a, p in acts if a == "background"), [10, 12, 14])
        self.assertNotIn(("background", 13), acts)
        self.assertNotIn(("background", 11), acts)

    def test_a_game_that_is_itself_on_the_list_is_not_demoted(self):
        self.assertEqual(gm.plan(5, [(5, "mds_stores")]), [("raise", 5)])


class Apply(unittest.TestCase):
    def test_apply_raises_the_game_and_demotes_the_jobs_and_records_both(self):
        state = os.path.join(tempfile.mkdtemp(), "s.json")
        r = Runner(nice=0)
        published = []
        rec = gm.apply(13, [(10, "mds_stores"), (13, "TheGame")], runner=r, state=state, publish=published.append)
        self.assertEqual(published, [True])
        self.assertEqual(rec, {"game": 13, "raised": [{"pid": 13, "nice": 0}], "backgrounded": [10]})
        self.assertIn(["/usr/bin/renice", "-5", "-p", "13"], r.calls)
        self.assertIn(["/usr/sbin/taskpolicy", "-b", "-p", "10"], r.calls)
        self.assertTrue(os.path.exists(state))

    def test_restore_undoes_exactly_what_apply_did_and_removes_the_record(self):
        state = os.path.join(tempfile.mkdtemp(), "s.json")
        gm.apply(13, [(10, "mds_stores"), (13, "TheGame")], runner=Runner(nice=3), state=state, publish=lambda a: None)
        r = Runner()
        published = []
        n = gm.restore(runner=r, state=state, publish=published.append)
        self.assertEqual(published, [False])
        self.assertEqual(n, 2)
        self.assertIn(["/usr/bin/renice", "3", "-p", "13"], r.calls)   # the game's own previous nice, not zero
        self.assertIn(["/usr/sbin/taskpolicy", "-B", "-p", "10"], r.calls)
        self.assertFalse(os.path.exists(state))

    def test_a_change_that_failed_is_not_recorded_so_it_is_not_undone(self):
        state = os.path.join(tempfile.mkdtemp(), "s.json")
        rec = gm.apply(13, [(10, "mds_stores"), (13, "TheGame")], runner=Runner(fail={"10"}), state=state, publish=lambda a: None)
        self.assertEqual(rec["backgrounded"], [])

    def test_restore_with_no_record_does_nothing(self):
        self.assertEqual(gm.restore(runner=Runner(), state="/nonexistent/none.json", publish=lambda a: None), 0)

    def test_apply_and_restore_need_root(self):
        if os.getuid() == 0:
            self.skipTest("running as root")
        for args in (["x", "apply", "1"], ["x", "restore"], ["x", "watch"]):
            self.assertEqual(gm.main(args), 2)


class Publish(unittest.TestCase):
    def test_active_sets_the_notify_state_to_1_and_writes_the_file(self):
        f = os.path.join(tempfile.mkdtemp(), "gamemode-active")
        calls = []
        gm.publish_active(True, notifier=lambda n, v: calls.append((n, v)), active_file=f)
        self.assertEqual(calls, [("com.nullmoth.gamemode.active", 1)])
        self.assertTrue(os.path.exists(f))

    def test_inactive_sets_the_state_to_0_and_removes_the_file(self):
        f = os.path.join(tempfile.mkdtemp(), "gamemode-active")
        gm.publish_active(True, notifier=lambda n, v: None, active_file=f)
        calls = []
        gm.publish_active(False, notifier=lambda n, v: calls.append((n, v)), active_file=f)
        self.assertEqual(calls, [("com.nullmoth.gamemode.active", 0)])
        self.assertFalse(os.path.exists(f))

    def test_a_file_that_cannot_be_written_does_not_stop_the_notification(self):
        calls = []
        gm.publish_active(True, notifier=lambda n, v: calls.append(v), active_file="/proc/none/x/gamemode-active")
        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
