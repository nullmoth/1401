"""Failed scans retain bounded evidence; imported reports never trigger current-host native queries."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from p1401 import hwcapture as hc, scan, scan_evidence as se
from tests.test_capture_completeness import Capture, REPORT


class Receipts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'scan'; self.token = se.begin(self.root, 'a' * 32)
    def capture(self):
        result = hc.empty_native('fixture unavailable')
        result['cpu_topology'] = hc.measured({'cores': 6}, 'fixture CPU API')
        return result
    def test_failed_scan_without_report_keeps_inventory_and_partial_raw_sections(self):
        se.save_inventory(self.root, self.token, self.capture()); se.save_partial(self.root, self.token, REPORT)
        value = se.finish(self.root, self.token, False, 'fixture WMI failure')
        self.assertIsNone(value['report_sha256']); self.assertEqual(value['capture']['cpu_topology']['value']['cores'], 6)
        self.assertEqual(value['hardware_summary']['Input'][0]['ACPI Path'], '\\_SB.I2CD.TPD0')
        self.assertEqual(value['scan_status'], 'failed')
        self.assertNotIn('SERIAL-PRIVATE', json.dumps(value)); self.assertNotIn('a4:bb:6d', json.dumps(value))
    def test_exact_report_binding_and_mutation_refusal(self):
        se.save_inventory(self.root, self.token, self.capture())
        report = self.root / 'Report.json'; report.write_text(json.dumps(REPORT)); value = se.finish(self.root, self.token, True)
        self.assertEqual(value['report_sha256'], hashlib.sha256(report.read_bytes()).hexdigest())
        self.assertEqual(se.load_for_report(report, REPORT)['cpu_topology']['value']['cores'], 6)
        report.write_text(json.dumps(REPORT) + ' ')
        self.assertEqual(se.load_for_report(report, REPORT)['scan_binding']['status'], 'unavailable')
    def test_incomplete_wrong_run_or_oversized_receipt_is_never_bound(self):
        report = self.root / 'Report.json'; report.write_text(json.dumps(REPORT))
        for raw in [se._read(self.root / se.RECEIPT), {'schema': se.SCHEMA, 'run_id': 'not-a-run'}, 'x' * (se.MAX_BYTES + 1)]:
            (self.root / se.RECEIPT).write_text(raw if isinstance(raw, str) else json.dumps(raw))
            self.assertEqual(se.load_for_report(report, REPORT)['scan_binding']['status'], 'unavailable')
    def test_nonregular_and_oversized_reports_are_not_bound(self):
        report = self.root / 'Report.json'; report.mkdir()
        self.assertIsNone(se.finish(self.root, self.token, False)['report_sha256'])
        self.assertEqual(se.load_for_report(report, REPORT)['scan_binding']['status'], 'unavailable')
        report.rmdir(); report.write_bytes(b' ' * (16 * 1024 * 1024 + 1))
        self.assertIsNone(se.finish(self.root, self.token, False)['report_sha256'])
        self.assertEqual(se.load_for_report(report, REPORT)['scan_binding']['status'], 'unavailable')

    def test_old_report_and_acpi_cannot_be_reused_as_a_new_scan(self):
        with self.assertRaises(ValueError): se.begin(self.root)
        other = Path(self.temp.name) / 'existing'; other.mkdir(); (other / 'Report.json').write_text('{}')
        with self.assertRaises(ValueError): se.begin(other)
        self.assertEqual((other / 'Report.json').read_text(), '{}')
    def test_unknown_or_missing_report_never_runs_native_api(self):
        with patch.object(hc, 'collect', side_effect=AssertionError('native')), patch.object(hc, '_bounded_native', side_effect=AssertionError('worker')):
            data = se.load_for_report(self.root / 'absent.json', {'GPU': []})
        self.assertEqual(data['cpu_topology']['status'], 'unavailable')
    def test_upstream_failure_retains_prescan_evidence(self):
        out = Path(self.temp.name) / 'controller'
        def failed(*args, **kwargs):
            se.save_partial(out, se._read(out / se.RECEIPT)['run_id'], REPORT)
            return subprocess.CompletedProcess(args, 1)
        with patch.object(hc, 'collect', return_value=self.capture()), patch.object(scan.subprocess, 'run', side_effect=failed):
            self.assertEqual(scan._child(str(out)), 1)
        value = se._read(out / se.RECEIPT); self.assertEqual(value['scan_status'], 'failed')
        self.assertEqual(value['capture']['cpu_topology']['value']['cores'], 6)
        self.assertEqual(value['hardware_summary']['GPU'][0]['Device ID'], '10DE-25A0')
    def test_upstream_timeout_keeps_inventory_without_report(self):
        out = Path(self.temp.name) / 'timeout'
        with patch.object(hc, 'collect', return_value=self.capture()), patch.object(scan.subprocess, 'run', side_effect=subprocess.TimeoutExpired('fixture', 1)):
            self.assertEqual(scan._child(str(out)), 1)
        value = se._read(out / se.RECEIPT); self.assertEqual(value['failure_type'], 'upstream_scan_timeout')
        self.assertEqual(value['capture']['cpu_topology']['value']['cores'], 6)


class BuilderReadsOnly(Capture):
    def test_no_native_query_for_imported_report(self):
        with patch.object(hc, 'collect', side_effect=AssertionError('native')), patch.object(hc, '_bounded_native', side_effect=AssertionError('worker')):
            result, data, _ = self.run_build(REPORT)
        self.assertEqual(data['capture']['scan_binding']['status'], 'unavailable')
        self.assertEqual(data['hardware_summary']['GPU'][0]['Device ID'], '10DE-25A0')


del Capture
