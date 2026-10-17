"""A boot file that is not the verified release's is written back from the verified zip before the EFI check.

A fresh build (NM-YZZJY5WJ) ended "EFI/OC/OpenCore.efi differs from the verified OpenCore release; rebuild the complete
EFI" with nothing to say what was there. The restore replaces the file and records its hash, size and whether it looked
quarantined; a file that still differs after that is being rewritten on the PC, and the message now says what it is."""
import hashlib
import io
import os
import pathlib
import plistlib
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from p1401 import validate

GOOD = {
    'X64/EFI/BOOT/BOOTx64.efi': b'MZ' + b'\x00' * 6000 + b'boot',
    'X64/EFI/OC/OpenCore.efi': b'MZ' + b'\x00' * 9000 + b'opencore',
    'X64/EFI/OC/Drivers/OpenRuntime.efi': b'MZ' + b'\x00' * 5000 + b'runtime',
    'X64/EFI/OC/Drivers/OpenCanopy.efi': b'MZ' + b'\x00' * 5000 + b'canopy',
}


class Restore(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            for name, data in GOOD.items():
                archive.writestr(name, data)
        self.archive = buffer.getvalue()
        self.digest = hashlib.sha256(self.archive).hexdigest()
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        (self.cache / 'OpenCore-TEST.zip').write_bytes(self.archive)
        self.efi = self.root / 'efi'
        for name, data in GOOD.items():
            if 'Canopy' in name:
                continue  # not enabled in this config: not a file the check owns
            target = self.efi / name[len('X64/'):]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (self.efi / 'EFI/OC/config.plist').write_bytes(plistlib.dumps(
            {'UEFI': {'Drivers': [{'Enabled': True, 'Path': 'OpenRuntime.efi'}, {'Enabled': False, 'Path': 'OpenCanopy.efi'}]}}))

    def patched(self):
        return patch.multiple(validate, CACHE=str(self.cache),
                              _opencore_release=lambda: ('https://example.invalid/OpenCore-TEST.zip', self.digest))

    def test_a_matching_efi_is_left_alone(self):
        with self.patched():
            self.assertEqual(validate.restore_release_components(str(self.efi)), [])
            self.assertEqual(validate.release_components(str(self.efi)), [])

    def test_a_rewritten_opencore_efi_is_put_back_and_described(self):
        path = self.efi / 'EFI/OC/OpenCore.efi'
        path.write_bytes(b'MZ' + b'\x11' * 9000 + b'other build')
        with self.patched():
            records = validate.restore_release_components(str(self.efi))
            self.assertEqual([r['file'] for r in records], ['EFI/OC/OpenCore.efi'])
            self.assertIn('sha256 ' + hashlib.sha256(b'MZ' + b'\x11' * 9000 + b'other build').hexdigest(), records[0]['found'])
            self.assertIn('9013 bytes', records[0]['found'])
            self.assertNotIn('quarantined', records[0]['found'])
            self.assertEqual(path.read_bytes(), GOOD['X64/EFI/OC/OpenCore.efi'])
            self.assertEqual(validate.release_components(str(self.efi)), [])

    def test_a_quarantined_looking_file_is_named_as_such(self):
        path = self.efi / 'EFI/OC/OpenCore.efi'
        path.write_bytes(b'')
        with self.patched():
            records = validate.restore_release_components(str(self.efi))
        self.assertIn('empty - security software may have quarantined it', records[0]['found'])
        path.write_bytes(b'quarantine stub')
        with self.patched():
            records = validate.restore_release_components(str(self.efi))
        self.assertIn('not a PE image', records[0]['found'])

    def test_a_missing_boot_file_is_restored(self):
        (self.efi / 'EFI/BOOT/BOOTx64.efi').unlink()
        with self.patched():
            records = validate.restore_release_components(str(self.efi))
        self.assertEqual((records[0]['file'], records[0]['found']), ('EFI/BOOT/BOOTx64.efi', 'missing'))
        self.assertTrue((self.efi / 'EFI/BOOT/BOOTx64.efi').is_file())

    def test_a_read_only_file_is_still_replaced(self):
        path = self.efi / 'EFI/OC/Drivers/OpenRuntime.efi'
        path.write_bytes(b'MZ' + b'\x22' * 5000)
        os.chmod(path, 0o444)
        with self.patched():
            validate.restore_release_components(str(self.efi))
        self.assertEqual(path.read_bytes(), GOOD['X64/EFI/OC/Drivers/OpenRuntime.efi'])

    def test_the_check_after_a_failed_restore_reports_the_hash_and_size(self):
        path = self.efi / 'EFI/OC/OpenCore.efi'
        path.write_bytes(b'stub')
        with self.patched():
            failures = validate.release_components(str(self.efi))
        self.assertEqual(len(failures), 1)
        self.assertIn('EFI/OC/OpenCore.efi differs from the verified OpenCore release', failures[0])
        self.assertIn(hashlib.sha256(b'stub').hexdigest(), failures[0])
        self.assertIn('4 bytes; not a PE image', failures[0])

    def test_the_build_restores_before_validating_and_explains_a_file_that_still_differs(self):
        source = (pathlib.Path(__file__).resolve().parents[1] / 'p1401/engine.py').read_text()
        build = source[source.index('def build('):]
        self.assertLess(build.index('validate_mod.restore_release_components(out_dir)'), build.index('validate_mod.validate(out_dir)'))
        self.assertIn('written back from the verified OpenCore zip just before this check', build)
        self.assertIn('res.policy_changes += restored', build)


if __name__ == '__main__':
    unittest.main()
