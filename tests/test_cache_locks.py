import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
from p1401 import dependency_cache, engine

sys.path.insert(0, engine.UPSTREAM)
from Scripts.utils import Utils


def locked(code=32):
    error = PermissionError('file is in use')
    error.winerror = code
    return error


class CacheLocks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        self.product = self.cache / 'BrightnessKeys'
        self.product.mkdir()
        (self.product / 'stale').write_text('old dependency')
        self.utils = Utils()
        dependency_cache.tolerate_cache_locks(self.utils, str(self.cache))

    def test_transient_windows_sharing_lock_retries_actual_cache_clear(self):
        import shutil
        original = shutil.rmtree
        failures = iter((locked(), locked(33), None))

        def clear(path):
            error = next(failures)
            if error is not None:
                raise error
            return original(path)

        with patch('Scripts.utils.shutil.rmtree', side_effect=clear) as remove, patch('p1401.dependency_cache.time.sleep') as pause:
            self.utils.create_folder(str(self.product), remove_content=True)
        self.assertEqual(remove.call_count, 3)
        self.assertEqual(pause.call_count, 2)
        self.assertTrue(self.product.is_dir())
        self.assertEqual(list(self.product.iterdir()), [])

    def test_persistent_lock_is_bounded_and_actionable(self):
        with patch('Scripts.utils.shutil.rmtree', side_effect=locked(33)) as remove, patch('p1401.dependency_cache.time.sleep') as pause:
            with self.assertRaisesRegex(RuntimeError, 'cache is still locked'):
                self.utils.create_folder(str(self.product), remove_content=True)
        self.assertEqual(remove.call_count, 4)
        self.assertEqual(pause.call_count, 3)
        self.assertTrue((self.product / 'stale').is_file())

    def test_permissions_and_paths_outside_cache_are_not_retried(self):
        other = self.root / 'other'
        other.mkdir()
        for target, code in ((self.product, 5), (other, 32)):
            with self.subTest(code=code), patch('Scripts.utils.shutil.rmtree', side_effect=locked(code)) as remove, patch('p1401.dependency_cache.time.sleep') as pause:
                with self.assertRaises(PermissionError):
                    self.utils.create_folder(str(target), remove_content=True)
                self.assertEqual(remove.call_count, 1)
                pause.assert_not_called()

    def test_other_utils_instances_are_unchanged(self):
        separate = Utils()
        with patch('Scripts.utils.shutil.rmtree', side_effect=locked()) as remove, patch('p1401.dependency_cache.time.sleep') as pause:
            with self.assertRaises(PermissionError):
                separate.create_folder(str(self.product), remove_content=True)
            self.assertEqual(remove.call_count, 1)
            pause.assert_not_called()


if __name__ == '__main__':
    unittest.main()
