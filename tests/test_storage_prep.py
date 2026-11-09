"""The Windows preparation for turning Intel VMD off (p1401/storage_prep.py), run against a recording runner."""
import os
import subprocess
import tempfile
import unittest

from p1401 import storage_prep as sp


class Runner:
    def __init__(self, fail=None, values=None):
        self.calls, self.fail, self.values = [], fail, values or {"storahci": 3, "stornvme": 3}

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if cmd[0] == "reg" and cmd[1] == "query":
            svc = cmd[2].rsplit("\\", 1)[1]
            v = self.values.get(svc)
            return subprocess.CompletedProcess(cmd, 0 if v is not None else 1, f"    Start    REG_DWORD    0x{v:x}\n" if v is not None else "", "")
        bad = self.fail and self.fail in " ".join(cmd)
        return subprocess.CompletedProcess(cmd, 1 if bad else 0, "", "denied" if bad else "")


class Prep(unittest.TestCase):
    def state(self):
        return os.path.join(tempfile.mkdtemp(), "state.json")

    def test_prepare_makes_a_restore_point_first_and_ends_with_the_one_time_safe_mode_boot(self):
        r = Runner()
        log = sp.run("prepare", self.state(), runner=r, platform="win32")
        self.assertTrue(all(ok for _, ok, _ in log))
        flat = [" ".join(c) for c in r.calls if c[0] != "reg" or c[1] != "query"]
        self.assertIn("Checkpoint-Computer", flat[0])
        self.assertIn("safeboot minimal", flat[-1])
        self.assertTrue(any("storahci" in c and "/d 0" in c for c in flat))

    def test_a_failed_required_step_undoes_what_was_changed(self):
        r = Runner(fail="bcdedit /set")
        path = self.state()
        log = sp.run("prepare", path, runner=r, platform="win32")
        self.assertEqual(log[-1][0], "rolled back")
        restored = [" ".join(c) for c in r.calls if c[:2] == ["reg", "add"] and c[-2] == "3"]
        self.assertEqual(len(restored), 2)        # both services back to their saved start type 3

    def test_undo_puts_back_the_saved_values_and_leaves_safe_mode(self):
        path = self.state()
        sp.run("prepare", path, runner=Runner(values={"storahci": 3, "stornvme": None}), platform="win32")
        r = Runner()
        sp.run("undo", path, runner=r, platform="win32")
        flat = [" ".join(c) for c in r.calls]
        self.assertTrue(any(c.startswith("reg delete") and "stornvme" in c for c in flat))
        self.assertTrue(any("storahci" in c and "/d 3" in c for c in flat))
        self.assertTrue(any("deletevalue" in c for c in flat))

    def test_it_refuses_to_run_off_windows(self):
        with self.assertRaises(RuntimeError):
            sp.run("prepare", self.state(), runner=Runner(), platform="darwin")

    def test_the_bios_path_follows_the_boards_maker(self):
        self.assertIn("F1", sp.bios_path("LENOVO 21HH"))
        self.assertIn("VMD setup menu", sp.bios_path("ASUSTeK COMPUTER INC. PRIME Z790-P"))
        self.assertEqual(sp.bios_path("Some Unknown Board"), sp.GENERIC_PATH)


if __name__ == "__main__":
    unittest.main()
