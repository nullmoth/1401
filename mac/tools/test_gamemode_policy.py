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


class Trigger(unittest.TestCase):
    DISPLAY = (0.0, 0.0, 1920.0, 1080.0)
    GAME = {"LSApplicationCategoryType": "public.app-category.games"}

    def test_a_window_covering_the_whole_display_is_full_screen_and_a_smaller_one_is_not(self):
        self.assertTrue(gm.covers((0, 0, 1920, 1080), self.DISPLAY))
        self.assertTrue(gm.covers((-1, -1, 1922, 1082), self.DISPLAY))
        self.assertFalse(gm.covers((0, 25, 1920, 1055), self.DISPLAY))      # below the menu bar: a maximised window
        self.assertFalse(gm.covers((100, 100, 800, 600), self.DISPLAY))

    def test_only_normal_layer_windows_count_so_overlays_do_not(self):
        wins = [{"pid": 5, "layer": 0, "bounds": (0, 0, 1920, 1080)}, {"pid": 6, "layer": 25, "bounds": (0, 0, 1920, 1080)},
                {"pid": 7, "layer": 0, "bounds": (10, 10, 300, 300)}]
        self.assertEqual(gm.fullscreen_pids(wins, [self.DISPLAY]), {5})

    def test_a_window_covering_either_of_two_displays_counts(self):
        wins = [{"pid": 5, "layer": 0, "bounds": (1920, 0, 2560, 1440)}]
        self.assertEqual(gm.fullscreen_pids(wins, [self.DISPLAY, (1920.0, 0.0, 2560.0, 1440.0)]), {5})

    def test_a_game_in_front_and_full_screen_gets_game_mode(self):
        self.assertEqual(gm.desired_game((5, "/Applications/G.app"), self.GAME, {5}), 5)

    def test_a_game_that_is_not_full_screen_does_not(self):
        self.assertIsNone(gm.desired_game((5, "/Applications/G.app"), self.GAME, set()))

    def test_a_full_screen_app_that_is_not_a_game_does_not(self):
        self.assertIsNone(gm.desired_game((5, "/Applications/Safari.app"), {"LSApplicationCategoryType": "public.app-category.productivity"}, {5}))

    def test_a_full_screen_game_that_is_not_in_front_does_not(self):
        self.assertIsNone(gm.desired_game((9, "/Applications/Other.app"), {}, {5}))
        self.assertIsNone(gm.desired_game(None, None, {5}))


class WatcherSteps(unittest.TestCase):
    def make(self, alive=None):
        log = []
        return gm.Watcher(lambda pid: log.append(("apply", pid)), lambda: log.append(("restore",)), alive), log

    def test_entering_full_screen_applies_and_leaving_restores(self):
        w, log = self.make()
        for g in (None, 5, 5, None, None):
            w.step(g)
        self.assertEqual(log, [("apply", 5), ("restore",)])

    def test_switching_from_one_game_to_another_restores_the_first_before_applying_the_second(self):
        w, log = self.make()
        for g in (5, 6):
            w.step(g)
        self.assertEqual(log, [("apply", 5), ("restore",), ("apply", 6)])

    def test_a_game_that_quits_is_restored_even_if_nothing_else_changed(self):
        up = {"yes": True}
        w, log = self.make(alive=lambda pid: up["yes"])
        w.step(5)
        up["yes"] = False
        w.step(5)
        self.assertEqual(log, [("apply", 5), ("restore",), ("apply", 5)])   # the same pid is a new game only if it is back

    def test_stopping_restores_what_is_active_and_does_nothing_otherwise(self):
        w, log = self.make()
        w.stop()
        self.assertEqual(log, [])
        w.step(5)
        w.stop()
        w.stop()
        self.assertEqual(log, [("apply", 5), ("restore",)])

    def test_the_root_loop_restores_when_it_ends(self):
        log = []
        seq = iter([{"front": [5, "/Applications/G.app"], "fullscreen": [5]}] * 2)
        orig = (gm.bundle_info, gm.apply, gm.restore, gm.processes, gm.alive)
        gm.bundle_info = lambda path: {"LSSupportsGameMode": True}
        gm.apply = lambda pid, procs, **k: log.append(("apply", pid))
        gm.restore = lambda **k: log.append(("restore",)) or 1
        gm.processes = lambda: []
        gm.alive = lambda pid: True
        try:
            gm.watch(0, observer=lambda: next(seq), sleep=lambda s: None, rounds=2)
        finally:
            gm.bundle_info, gm.apply, gm.restore, gm.processes, gm.alive = orig
        self.assertEqual(log, [("apply", 5), ("restore",)])

    def test_a_missing_user_session_means_no_game(self):
        self.assertIsNone(gm.observe_as_user(runner=lambda cmd: subprocess.CompletedProcess(cmd, 0, "not json", ""), uid=501))
        self.assertIsNone(gm.observe_as_user(runner=lambda cmd: None, uid=0))


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
