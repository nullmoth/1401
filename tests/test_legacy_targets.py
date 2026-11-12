"""The experimental older macOS releases: the module's own named arms, and the opt-in at the engine's door."""
import os
import subprocess
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class LegacyTargets(unittest.TestCase):
    def test_selftest(self):
        p = subprocess.run([sys.executable, "-m", "p1401.legacy", "--selftest"], cwd=REPO, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout[-2000:] + p.stderr[-2000:])
        self.assertIn("legacy selftest: 0 failed", p.stdout)

    def test_recovery_targets_cover_every_release(self):
        from p1401 import apple, legacy
        for d in legacy.RELEASE:
            self.assertIn(d, apple.TARGETS, f"no recovery image target for Darwin {d}")
            self.assertEqual(apple.MAJOR[d], legacy.RELEASE[d])
        for d in range(11, 19):   # before Catalina Apple picks the image from a board serial
            self.assertIn(d, apple.OLD_MLB)

    def test_off_by_default_and_15_26_untouched(self):
        from p1401 import engine, legacy, nullmoth
        self.assertFalse(engine.Policy().legacy)
        self.assertIsNone(legacy.target("24"))
        self.assertIsNone(legacy.target("25"))
        rep = {"GPU": {"RTX 5060": {"Manufacturer": "NVIDIA", "Device Type": "Discrete GPU", "Device ID": "10DE-2D05"}}}
        nullmoth.mark(rep)
        self.assertEqual(rep["GPU"]["RTX 5060"]["Compatibility"], nullmoth.SEQUOIA)
        nullmoth.mark(rep, legacy=True)
        self.assertEqual(rep["GPU"]["RTX 5060"]["Compatibility"], nullmoth.LEGACY)

    def test_driver_arguments_keep_the_accelerator_off(self):
        from p1401 import legacy
        cfg = {"NVRAM": {"Add": {"7C436110-AB2A-4BBB-A880-FE41995C9F82": {"boot-args": "-v nvaccel=1"}}}}
        seen = []
        legacy.driver_args(cfg, lambda *a: seen.append(a))
        args = cfg["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"].split()
        self.assertIn("nvfb=1", args)
        self.assertNotIn("nvaccel=1", args)
        self.assertTrue(seen)


if __name__ == "__main__":
    unittest.main()
