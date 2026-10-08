import hashlib
import os
import pathlib
import plistlib
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from p1401 import validate


class OpenCoreComponents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        archive = os.environ.get('OPENCORE_TEST_ZIP', os.path.join(validate.CACHE, 'OpenCore-1.0.8-RELEASE.zip'))
        if not os.path.isfile(archive):
            raise unittest.SkipTest('The official OpenCore release archive is required.')
        cls.archive = pathlib.Path(archive).read_bytes()
        cls.digest = hashlib.sha256(cls.archive).hexdigest()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        self.archive_path = self.cache / 'OpenCore-RELEASE.zip'
        self.archive_path.write_bytes(self.archive)
        with zipfile.ZipFile(self.archive_path) as release:
            for relative in ('EFI/BOOT/BOOTx64.efi', 'EFI/OC/OpenCore.efi', 'EFI/OC/Drivers/OpenRuntime.efi'):
                target = self.root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(release.read('X64/' + relative))
        self.config_path = self.root / 'EFI/OC/config.plist'
        self.config_path.write_bytes(plistlib.dumps({'UEFI': {'Drivers': [{'Enabled': True, 'Path': 'OpenRuntime.efi'}]}}))

    def check(self):
        with patch.object(validate, 'CACHE', str(self.cache)), patch.object(validate, '_opencore_release', return_value=('https://github.com/example/OpenCore-RELEASE.zip', self.digest)):
            return validate.release_components(str(self.root))

    def test_matching_release_files_pass(self):
        self.assertEqual(self.check(), [])

    def test_binary_mismatch_is_detected_even_when_config_is_unchanged(self):
        before = self.config_path.read_bytes()
        for relative in ('EFI/BOOT/BOOTx64.efi', 'EFI/OC/OpenCore.efi', 'EFI/OC/Drivers/OpenRuntime.efi'):
            with self.subTest(relative=relative):
                target = self.root / relative
                original = target.read_bytes()
                target.write_bytes(b'older or replaced executable')
                self.assertIn(relative + ' differs', self.check()[0])
                self.assertEqual(self.config_path.read_bytes(), before)
                target.write_bytes(original)

    def test_missing_opencore_executable_stops_validation(self):
        (self.root / 'EFI/OC/OpenCore.efi').unlink()
        self.assertEqual(self.check(), ['EFI/OC/OpenCore.efi is missing from the built EFI'])

    def test_changed_release_archive_is_rejected(self):
        self.archive_path.write_bytes(b'changed archive')
        with self.assertRaisesRegex(validate.ValidatorUnavailable, 'archive changed'):
            self.check()

    def test_external_driver_is_not_mistaken_for_a_stock_release_driver(self):
        self.config_path.write_bytes(plistlib.dumps({'UEFI': {'Drivers': [{'Enabled': True, 'Path': 'HfsPlus.efi'}]}}))
        self.assertEqual(self.check(), [])


if __name__ == '__main__':
    unittest.main()
