"""A cached executable must still match its verified OpenCore archive before launch."""
import hashlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile
from p1401 import validate


class ValidatorProvenance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)
        self.payload = b'MZverified-validator-fixture'
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('Utilities/ocvalidate/ocvalidate.exe', self.payload)
        self.archive = self.cache / 'OpenCore-fixture.zip'
        self.archive.write_bytes(stream.getvalue())
        self.digest = hashlib.sha256(stream.getvalue()).hexdigest()
        self.exe = self.cache / (self.digest[:12] + '-ocvalidate.exe')
        for patch in [mock.patch.object(validate, 'CACHE', str(self.cache)),
                      mock.patch.object(validate, '_opencore_release', return_value=('https://github.com/example/OpenCore-fixture.zip', self.digest)),
                      mock.patch.object(validate.platform, 'system', return_value='Windows'),
                      mock.patch.object(validate.urllib.request, 'urlopen', side_effect=AssertionError('unexpected network'))]:
            patch.start(); self.addCleanup(patch.stop)

    def launch(self):
        calls = []
        def recorded(command, **kwargs):
            calls.append(command)
            self.assertEqual(Path(command[0]).read_bytes(), self.payload)
            self.assertEqual(command[1], 'config.plist')
            return subprocess.CompletedProcess(command, 0, 'No issues found.', '')
        with mock.patch.object(validate.subprocess, 'run', side_effect=recorded):
            result = validate.run_ocvalidate('config.plist')
        self.assertEqual(result, (True, 0, 'No issues found.'))
        self.assertEqual(len(calls), 1)

    def test_replaced_cached_executable_is_repaired_before_launch(self):
        self.exe.write_bytes(b'MZunverified-replacement')
        self.launch()
        self.assertFalse(any(p.name.startswith('1401-validator-') for p in self.cache.iterdir()))

    def test_missing_executable_is_verified_and_extracted(self):
        self.launch()

    def test_exact_cached_executable_is_not_rewritten(self):
        self.exe.write_bytes(self.payload)
        with mock.patch('tempfile.mkstemp', side_effect=AssertionError('unnecessary rewrite')):
            self.launch()

    def test_symlink_cannot_replace_external_target_or_launch(self):
        external = self.cache / 'external.bin'; external.write_bytes(b'preserve')
        try: self.exe.symlink_to(external)
        except OSError as error:
            # Standard Windows accounts may not create links; the link-detection branch still executes.
            if os.name != 'nt': raise
            with mock.patch.object(validate.os.path, 'islink', return_value=True), \
                 mock.patch.object(validate.subprocess, 'run', side_effect=AssertionError('launch')):
                with self.assertRaises(validate.ValidatorUnavailable): validate.run_ocvalidate('config.plist')
        else:
            with mock.patch.object(validate.subprocess, 'run', side_effect=AssertionError('launch')):
                with self.assertRaises(validate.ValidatorUnavailable): validate.run_ocvalidate('config.plist')
            self.assertTrue(self.exe.is_symlink())
        self.assertEqual(external.read_bytes(), b'preserve')

    def test_failed_repair_stops_before_launch_and_cleans_temporary(self):
        self.exe.write_bytes(b'MZreplacement')
        with mock.patch.object(validate.os, 'replace', side_effect=PermissionError('fixture')), \
             mock.patch.object(validate.subprocess, 'run', side_effect=AssertionError('launch')):
            with self.assertRaises(PermissionError): validate.run_ocvalidate('config.plist')
        self.assertEqual(self.exe.read_bytes(), b'MZreplacement')
        self.assertFalse(any(p.name.startswith('1401-validator-') for p in self.cache.iterdir()))

    def test_post_write_mismatch_stops_before_launch(self):
        original = validate.os.replace
        def replaced(source, target):
            original(source, target); Path(target).write_bytes(b'changed')
        with mock.patch.object(validate.os, 'replace', side_effect=replaced), \
             mock.patch.object(validate.subprocess, 'run', side_effect=AssertionError('launch')):
            with self.assertRaises(validate.ValidatorUnavailable): validate.run_ocvalidate('config.plist')

    def test_application_control_refusal_remains_failure_without_paths(self):
        denied = OSError('private exception detail'); denied.winerror = 4551
        with mock.patch.object(validate.subprocess, 'run', side_effect=denied) as launch:
            result = validate.validate('fixture-efi')
        self.assertFalse(result['ok']); self.assertIsNone(result['ocvalidate'])
        self.assertIn('application control', result['error']); self.assertIn('4551', result['error'])
        self.assertIn('CodeIntegrity', result['error']); self.assertNotIn('private exception detail', result['error'])
        self.assertEqual(launch.call_count, 1)

    def test_archive_replacement_between_initial_hash_and_extraction_never_launches(self):
        original = validate._sha256
        alternate = io.BytesIO()
        with zipfile.ZipFile(alternate, 'w') as archive:
            archive.writestr('Utilities/ocvalidate/ocvalidate.exe', b'MZunverified-archive')
        def replaced(path):
            digest = original(path)
            if Path(path) == self.archive: self.archive.write_bytes(alternate.getvalue())
            return digest
        with mock.patch.object(validate, '_sha256', side_effect=replaced), \
             mock.patch.object(validate.subprocess, 'run', side_effect=AssertionError('launch')):
            with self.assertRaisesRegex(validate.ValidatorUnavailable, 'archive changed'):
                validate.run_ocvalidate('config.plist')
        self.assertFalse(self.exe.exists())

    def test_other_launch_error_is_not_misclassified_as_application_control(self):
        denied = PermissionError('fixture-access'); denied.winerror = 5
        with mock.patch.object(validate.subprocess, 'run', side_effect=denied):
            result = validate.validate('fixture-efi')
        self.assertFalse(result['ok']); self.assertNotIn('application control', result['error'])
