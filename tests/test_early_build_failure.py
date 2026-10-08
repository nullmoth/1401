import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from p1401 import engine
from p1401.__main__ import _result_json

class EarlyFailure(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.report = self.root / 'Report.json'; self.acpi = self.root / 'ACPI'; self.acpi.mkdir()
        (self.acpi / 'dsdt.aml').write_bytes(b'DSDT')
        self.report.write_text(json.dumps({'CPU': {'Manufacturer': 'AMD', 'Processor Name': 'Fixture CPU', 'Serial': 'private'}, 'GPU': {'Basic Display Adapter': {'Manufacturer': 'Unknown', 'Device ID': '10DE-2B85'}}, 'Motherboard': {'Name': 'Fixture Board'}}))
    def tearDown(self): self.temp.cleanup()
    def build(self, factory):
        utils = SimpleNamespace(Utils=type('Utils', (), {}))
        with patch.object(engine, '_load_engine', return_value=(SimpleNamespace(OCPE=factory), utils)):
            return engine.build(str(self.report), str(self.acpi), str(self.root / 'out'))
    def test_download_bootstrap_failure_retains_machine_identity(self):
        factory = Mock(side_effect=RuntimeError('iasl download failed'))
        result = self.build(factory); data = _result_json(result)
        self.assertFalse(result.ok); self.assertIn('iasl download failed', result.error)
        self.assertEqual(data['hardware_summary']['GPU'][0]['Device ID'], '10DE-2B85')
        self.assertEqual(data['hardware_summary']['CPU']['Processor Name'], 'Fixture CPU')
        self.assertNotIn('private', json.dumps(data))
    def test_missing_inputs_do_not_start_downloads(self):
        for missing in ('report', 'acpi'):
            with self.subTest(missing=missing):
                if missing == 'report':
                    saved = self.report.read_bytes(); self.report.unlink()
                else: (self.acpi / 'dsdt.aml').unlink()
                factory = Mock(); result = self.build(factory)
                self.assertFalse(result.ok); factory.assert_not_called()
                if missing == 'report': self.report.write_bytes(saved)
                else: self.assertTrue(_result_json(result)['hardware_summary']['GPU'])
    def test_import_failure_returns_structured_error(self):
        with patch.object(engine, '_load_engine', side_effect=ImportError('missing engine file')):
            result = engine.build(str(self.report), str(self.acpi), str(self.root / 'out'))
        self.assertFalse(result.ok); self.assertIn('missing engine file', result.error)
        self.assertEqual(result.transcript, '')

if __name__ == '__main__': unittest.main()
