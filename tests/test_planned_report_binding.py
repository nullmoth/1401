"""Parsed input and its exact scan evidence remain bound across planning and diagnostics."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from p1401 import report as report_mod, scan_evidence
from tests.test_panel_routing_guard import BeforeMutation, evidence, REPORT


def replace_input(path):
    path = Path(path)
    updated = copy.deepcopy(REPORT)
    updated['Motherboard']['Name'] = 'Different fixture board'
    payload = json.dumps(updated).encode()
    path.write_bytes(payload)
    receipt_path = path.parent / scan_evidence.RECEIPT
    receipt = json.loads(receipt_path.read_text())
    receipt['report_sha256'] = hashlib.sha256(payload).hexdigest()
    receipt['capture'] = evidence([])
    receipt_path.write_text(json.dumps(receipt))


class PlannedBinding(BeforeMutation):
    def test_replaced_report_and_receipt_do_not_release_active_panel_guard(self):
        original = scan_evidence.load_for_report
        changed = [False]
        def replace(path, raw=None, **kwargs):
            if not changed[0]:
                changed[0] = True
                replace_input(path)
            return original(path, raw, **kwargs)
        with patch.object(scan_evidence, 'load_for_report', side_effect=replace):
            result, calls, retained = self.run_engine()
        self.assertFalse(result.ok)
        self.assertIn('changed', result.error)
        self.assertEqual(calls, 0)
        self.assertTrue(retained)
        self.assertEqual(result.capture['scan_binding']['status'], 'unavailable')
        self.assertNotEqual(result.raw_hardware['Motherboard']['Name'], 'Different fixture board')

    def test_removed_report_stops_before_prior_efi_cleanup(self):
        original = scan_evidence.load_for_report
        def remove(path, raw=None, **kwargs):
            Path(path).unlink(missing_ok=True)
            return original(path, raw, **kwargs)
        with patch.object(scan_evidence, 'load_for_report', side_effect=remove):
            result, calls, retained = self.run_engine()
        self.assertFalse(result.ok)
        self.assertIn('changed', result.error)
        self.assertEqual(calls, 0)
        self.assertTrue(retained)
        self.assertEqual(result.capture['scan_binding']['status'], 'unavailable')

    def test_final_diagnostics_cannot_borrow_a_replacement_inventory(self):
        original = scan_evidence.load_for_report
        calls = [0]
        def replace_on_final_read(path, raw=None, **kwargs):
            calls[0] += 1
            if calls[0] == 2:
                replace_input(path)
            return original(path, raw, **kwargs)
        with patch.object(scan_evidence, 'load_for_report', side_effect=replace_on_final_read):
            result, later_calls, retained = self.run_engine()
        self.assertEqual(later_calls, 1)
        self.assertIn('later planning reached', result.error)
        self.assertEqual(result.capture['scan_binding']['status'], 'unavailable')
        self.assertEqual(result.capture['device_map']['graphics']['status'], 'unavailable')
        self.assertEqual(result.raw_hardware['Motherboard']['Name'], 'Fixture board')


class FrozenNormalization(unittest.TestCase):
    def test_parsed_snapshot_is_normalized_without_rereading_or_mutating_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'original.json'
            path.write_text(json.dumps({'GPU': {'bad': {'Manufacturer': 'Unknown'}}}))
            held = copy.deepcopy(REPORT)
            held['BIOS'] = {'Firmware Type': 'fixture banner\nUEFI'}
            before = copy.deepcopy(held)
            result, notes = report_mod.normalized_copy(path, root, raw_hardware=held)
            normalized = json.loads(Path(result).read_text())
            self.assertEqual(held, before)
            self.assertEqual(normalized['Motherboard']['Name'], 'Fixture board')
            self.assertEqual(normalized['BIOS']['Firmware Type'], 'UEFI')
            self.assertEqual(normalized['Input'], {})
            self.assertEqual(len(notes), 2)

    def test_standalone_import_normalization_preserves_existing_behavior(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'imported.json'
            path.write_text(json.dumps(REPORT))
            out, notes = report_mod.normalized_copy(path, root)
            self.assertEqual(json.loads(Path(out).read_text())['Input'], {})
            self.assertEqual(len(notes), 1)

    def test_import_without_receipt_remains_offline_unbound(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'imported.json'
            data = json.dumps(REPORT).encode()
            path.write_bytes(data)
            capture = scan_evidence.load_for_report(path, REPORT,
                expected_report_sha256=hashlib.sha256(data).hexdigest())
            self.assertEqual(capture['scan_binding']['status'], 'unavailable')
            self.assertTrue(capture['gpus'])


if __name__ == '__main__':
    unittest.main()
