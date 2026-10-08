"""Exercise real upstream manifests that previously hid an incomplete EFI base."""
import os
import pathlib
import plistlib
import sys
import tempfile
import unittest
import zipfile

from p1401 import dependency_cache, engine, validate

sys.path.insert(0, engine.UPSTREAM)
from Scripts.integrity_checker import IntegrityChecker


class DependencyCache(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        archive = os.environ.get('OPENCORE_TEST_ZIP', os.path.join(validate.CACHE, 'OpenCore-1.0.8-RELEASE.zip'))
        if not os.path.isfile(archive):
            raise unittest.SkipTest('The official OpenCore release archive is required.')
        with zipfile.ZipFile(archive) as release:
            cls.payloads = {'EFI/BOOT/BOOTx64.efi': release.read('X64/EFI/BOOT/BOOTx64.efi'),
                            'EFI/OC/OpenCore.efi': release.read('X64/EFI/OC/OpenCore.efi'),
                            'EFI/OC/config.plist': release.read('Docs/Sample.plist')}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.cache = self.root / 'OpenCorePkg'
        self.cache.mkdir()
        self.checker = IntegrityChecker()

    def put(self, payloads):
        for relative, data in payloads.items():
            path = self.cache / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.checker.generate_folder_manifest(str(self.cache))

    def test_empty_manifest_is_not_a_valid_dependency(self):
        self.put({})
        self.assertTrue(self.checker.verify_folder_integrity(str(self.cache))[0])
        dependency_cache.harden(self.checker)
        self.assertFalse(self.checker.verify_folder_integrity(str(self.cache))[0])

    def test_missing_config_with_consistent_manifest_is_refetched(self):
        self.put({key: data for key, data in self.payloads.items() if not key.endswith('config.plist')})
        self.assertTrue(self.checker.verify_folder_integrity(str(self.cache))[0])
        dependency_cache.harden(self.checker)
        valid, issues = self.checker.verify_folder_integrity(str(self.cache))
        self.assertFalse(valid)
        self.assertIn('EFI/OC/config.plist', issues['incomplete'])

    def test_real_complete_dependency_passes_but_modified_binary_does_not(self):
        self.put(self.payloads)
        dependency_cache.harden(self.checker)
        dependency_cache.harden(self.checker)
        self.assertTrue(self.checker.verify_folder_integrity(str(self.cache))[0])
        (self.cache / 'EFI/OC/OpenCore.efi').write_bytes(b'changed')
        valid, issues = self.checker.verify_folder_integrity(str(self.cache))
        self.assertFalse(valid)
        self.assertIn('EFI/OC/OpenCore.efi', issues['modified'])

    def test_wrong_template_with_matching_hash_is_not_reused(self):
        self.put({**self.payloads, 'EFI/OC/config.plist': plistlib.dumps({'wrong': 'template'})})
        dependency_cache.harden(self.checker)
        self.assertFalse(self.checker.verify_folder_integrity(str(self.cache))[0])

    def test_truncated_xml_with_matching_hash_is_refetched(self):
        self.put({**self.payloads, 'EFI/OC/config.plist': b'<?xml version="1.0"?><plist><dict>'})
        dependency_cache.harden(self.checker)
        valid, issues = self.checker.verify_folder_integrity(str(self.cache))
        self.assertFalse(valid)
        self.assertIn('could not be read', issues['incomplete'][0])


if __name__ == '__main__':
    unittest.main()
