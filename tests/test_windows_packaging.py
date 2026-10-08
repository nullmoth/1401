"""Exercise release packaging behavior independently of a Windows runner."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('windows_release', Path(__file__).resolve().parents[1] / 'tools/windows_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class Packaging(unittest.TestCase):
    def test_archive_is_stable_across_source_order_and_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / '1401'
            root.mkdir()
            (root / 'b.txt').write_bytes(b'second')
            (root / '1401.exe').write_bytes(b'MZ executable')
            (root / 'a.txt').write_bytes(b'first')
            first, second = Path(directory) / 'first.zip', Path(directory) / 'second.zip'
            release.deterministic_zip(root, first)
            (root / 'a.txt').touch()
            (root / 'b.txt').touch()
            release.deterministic_zip(root, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(archive.namelist(), ['1401/1401.exe', '1401/a.txt', '1401/b.txt'])
                self.assertTrue(all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist()))

    def test_escape_and_drive_members_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ('../outside', '1401/../outside', 'C:/outside', '1401/C:/outside', '1401\\outside'):
                with self.subTest(name=name):
                    archive = Path(directory) / 'bad.zip'
                    with zipfile.ZipFile(archive, 'w') as output:
                        output.writestr(name, b'payload')
                    with self.assertRaisesRegex(RuntimeError, 'Unsafe'):
                        release.extract_baseline(archive, Path(directory) / 'stage')

    def test_checksum_failure_preserves_existing_input(self):
        from unittest.mock import patch
        import io
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'input.zip'
            target.write_bytes(b'existing')
            with patch.object(release, 'get', return_value=io.BytesIO(b'wrong')):
                with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
                    release.download('https://github.com/example/input.zip', '0' * 64, target)
            self.assertEqual(target.read_bytes(), b'existing')
            self.assertFalse(target.with_suffix('.zip.part').exists())

    def test_changed_candidate_cannot_be_packaged_using_old_evidence(self):
        import json
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory) / 'stage'
            (stage / '1401').mkdir(parents=True)
            (stage / '1401/1401.exe').write_bytes(b'MZ changed')
            evidence = Path(directory) / 'evidence.json'
            evidence.write_text(json.dumps({'ok': True, 'version': release.version(), 'candidate_files': {'1401.exe': '0' * 64}}))
            output = Path(directory) / 'output'
            with self.assertRaisesRegex(RuntimeError, 'changed after'):
                release.package(SimpleNamespace(stage=str(stage), evidence=str(evidence), output=str(output)))
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
