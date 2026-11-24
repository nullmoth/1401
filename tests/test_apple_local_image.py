"""A BaseSystem.dmg in the Recovery folder is size-checked against its chunklist before anything is erased; a cut-short
copy is named and the writer asks Apple instead."""
import os
import tempfile
import unittest
from unittest.mock import patch

from p1401 import apple


class LocalImage(unittest.TestCase):
    def folder(self, image_bytes):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "BaseSystem.dmg"), "wb") as fh:
            fh.write(b"x" * image_bytes)
        with open(os.path.join(d, "BaseSystem.chunklist"), "wb") as fh:
            fh.write(b"CNKL")
        return d

    def test_a_cut_short_image_is_named_with_both_sizes(self):
        d = self.folder(1_048_576)
        with patch.object(apple, "parse_chunklist", lambda data: [(884_317_790, b"h")]):
            info = apple.local_image(d)
        self.assertIn("incomplete", info["problem"])
        self.assertIn("1.0 MB of the 884.3 MB", info["problem"])

    def test_an_unreadable_chunklist_is_a_problem_not_a_crash(self):
        d = self.folder(10)
        def bad(data):
            raise apple.AppleError("not an Apple chunklist")
        with patch.object(apple, "parse_chunklist", bad):
            self.assertIn("cannot be read", apple.local_image(d)["problem"])

    def test_negative_control_a_whole_image_has_no_problem(self):
        d = self.folder(100)
        with patch.object(apple, "parse_chunklist", lambda data: [(60, b"a"), (40, b"b")]):
            info = apple.local_image(d)
        self.assertNotIn("problem", info)
        self.assertTrue(info["local"])

    def test_the_writer_falls_back_to_apple_when_the_local_copy_has_a_problem(self):
        src = open(os.path.join(os.path.dirname(apple.__file__), "usbwriter.py"), encoding="utf-8").read()
        i = src.index("info = apple.local_image(rec)")
        self.assertIn('if info and info.get("problem"):', src[i:i + 300])
        self.assertIn("info = None", src[i:i + 400])


if __name__ == "__main__":
    unittest.main()
