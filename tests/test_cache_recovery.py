"""A dependency cache that exists but refuses writes must not end the build.

The first MateBook build in this project left OCK_Files/Lilu with an ACL that denied its own user; the second build
died with "PermissionError: ...\\OCK_Files\\Lilu\\manifest.json". The folder may belong to another user or a sandbox,
so it is never deleted: a fresh cache is used beside it.
"""
import os
import tempfile
import unittest
from unittest import mock

from p1401 import engine


class PickCache(unittest.TestCase):
    def test_a_writable_base_is_used(self):
        calls = []
        got = engine.pick_cache(r"C:\cache", writable=lambda p: calls.append(p) or True)
        self.assertEqual(got, r"C:\cache")
        self.assertEqual(calls, [r"C:\cache"])

    def test_an_unwritable_base_falls_over_to_a_fresh_folder(self):
        got = engine.pick_cache(r"C:\cache", writable=lambda p: p == r"C:\cache-2")
        self.assertEqual(got, r"C:\cache-2")

    def test_none_writable_is_none_not_a_crash_inside_the_engine(self):
        self.assertIsNone(engine.pick_cache(r"C:\cache", writable=lambda p: False))

    def test_a_real_folder_is_writable_and_a_file_in_its_place_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(engine.cache_writable(os.path.join(tmp, "cache")))
            marker = os.path.join(tmp, "file")
            open(marker, "wb").close()
            self.assertFalse(engine.cache_writable(marker))

    def test_a_cache_with_an_inaccessible_child_is_not_used(self):
        # The real failure: OCK_Files itself was writable, OCK_Files/Lilu was not, and the build died there.
        with tempfile.TemporaryDirectory() as tmp:
            os.mkdir(os.path.join(tmp, "Lilu"))
            real_open = open

            def fake_open(path, *a, **k):
                parent = os.path.basename(os.path.dirname(str(path)))
                if parent == "Lilu":
                    raise PermissionError(13, "Permission denied", str(path))
                return real_open(path, *a, **k)

            with mock.patch("builtins.open", fake_open):
                self.assertFalse(engine.cache_writable(tmp))

    def test_the_build_uses_the_fallback_and_says_so(self):
        seen = {}
        fake = mock.Mock()
        fake.o = mock.Mock()
        fake.k = mock.Mock()
        with mock.patch.object(engine, "pick_cache", return_value=r"C:\cache-2"), \
             mock.patch("builtins.print") as out:
            engine._use_ock_cache(fake)
        self.assertEqual(fake.o.ock_files_dir, r"C:\cache-2")
        self.assertEqual(fake.k.ock_files_dir, r"C:\cache-2")
        self.assertIn("not writable", " ".join(str(c.args[0]) for c in out.call_args_list if c.args))


if __name__ == "__main__":
    unittest.main()
