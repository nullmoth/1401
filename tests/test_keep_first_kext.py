"""A download holding two kexts with the same name builds with the first, instead of stopping (WinError 183)."""
import os, tempfile, types, unittest

from p1401 import engine


class KeepFirst(unittest.TestCase):
    def test_second_same_name_kext_is_skipped_and_the_first_kept(self):
        mod = types.SimpleNamespace(shutil=__import__("shutil"))
        engine._keep_first_kext(mod)
        with tempfile.TemporaryDirectory() as t:
            a, b, dst = (os.path.join(t, x) for x in ("a/x.kext", "b/x.kext", "out/x.kext"))
            for d, tag in ((a, "first"), (b, "second")):
                os.makedirs(d); open(os.path.join(d, "tag"), "w").write(tag)
            os.makedirs(os.path.dirname(dst))
            mod.shutil.move(a, dst)
            mod.shutil.move(b, dst)
            self.assertEqual(open(os.path.join(dst, "tag")).read(), "first")
            self.assertFalse(os.path.exists(os.path.join(dst, "x.kext")))

    def test_control_other_moves_are_untouched(self):
        mod = types.SimpleNamespace(shutil=__import__("shutil"))
        engine._keep_first_kext(mod)
        with tempfile.TemporaryDirectory() as t:
            src, dst = os.path.join(t, "f.txt"), os.path.join(t, "g.txt")
            open(src, "w").write("x"); mod.shutil.move(src, dst)
            self.assertTrue(os.path.exists(dst) and not os.path.exists(src))
            self.assertIs(mod.shutil.rmtree, __import__("shutil").rmtree)


if __name__ == "__main__":
    unittest.main()
