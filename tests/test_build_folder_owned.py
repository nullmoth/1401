"""A build that stops inside the upstream EFI step must not lock the PC out of every later Build.

106 build logs (1401 1.0 to 1.15) ended "refusing to build into an unowned nonempty folder": the upstream step empties
the output folder, marker included, copies OpenCore in, and a failure after that left a folder without the marker."""
import inspect
import os
import tempfile
import unittest

from p1401 import engine


def leftover(root, *parts, extra=()):
    d = os.path.join(root, *parts)
    os.makedirs(os.path.join(d, "EFI", "OC", "Kexts"))
    open(os.path.join(d, "EFI", "OC", "OpenCore.efi"), "wb").write(b"x")
    for name in extra:
        open(os.path.join(d, name), "w").write("x")
    return d


class LeftoverBuild(unittest.TestCase):
    def test_the_apps_own_folder_left_by_a_stopped_build_is_adopted_and_wiped(self):
        with tempfile.TemporaryDirectory() as t:
            d = leftover(t, "NullMoth", "1401", "efi", extra=("manifest.json",))
            self.assertTrue(engine._adopt_leftover_build(d))
            engine._prepare_out(d)  # raised "not a 1401 build folder" before
            self.assertEqual(os.listdir(d), [])

    def test_negative_control_any_other_folder_is_still_refused(self):
        with tempfile.TemporaryDirectory() as t:
            d = leftover(t, "Desktop", "my-efi")
            self.assertFalse(engine._adopt_leftover_build(d))
            with self.assertRaises(RuntimeError):
                engine._prepare_out(d)
            self.assertTrue(os.path.exists(os.path.join(d, "EFI", "OC", "OpenCore.efi")))

    def test_negative_control_the_apps_folder_holding_other_files_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            d = leftover(t, "NullMoth", "1401", "efi", extra=("my-notes.txt",))
            self.assertFalse(engine._adopt_leftover_build(d))
            with self.assertRaises(RuntimeError):
                engine._prepare_out(d)

    def test_the_marker_is_written_back_even_when_the_upstream_step_raises(self):
        src = inspect.getsource(engine.build)
        body = src[src.index("o.build_opencore_efi("):]
        self.assertLess(body.index("finally:"), body.index("MARKER"))
        self.assertIn("_adopt_leftover_build(out_dir)", src[:src.index("refusing to build into an unowned")])


if __name__ == "__main__":
    unittest.main()
