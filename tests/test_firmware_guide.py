"""Saved-report firmware advice stays available without building or changing EFI."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from p1401 import guide, engine, scan_evidence

ROOT = Path(__file__).resolve().parents[1]
TOKEN = '1' * 32


class FirmwareReview(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.report = self.root / 'Report.json'
        self.value = {'Motherboard': {'Name': 'Example Board', 'Platform': 'Laptop'},
                      'CPU': {'Processor Name': 'Example processor', 'Manufacturer': 'Intel'},
                      'BIOS': {'Firmware Type': 'UEFI'},
                      'Storage Controllers': {'Intel VMD Controller': {'Device ID': '8086-1234'}}}
        self.report.write_text(json.dumps(self.value))
        self.receipt = self.root / scan_evidence.RECEIPT
        self.bind()

    def tearDown(self):
        self.temp.cleanup()

    def bind(self, **changes):
        value = {'schema': scan_evidence.SCHEMA, 'run_id': TOKEN, 'phase': 'complete',
                 'scan_status': 'complete', 'report_sha256': hashlib.sha256(self.report.read_bytes()).hexdigest(),
                 'capture': {}}
        value.update(changes)
        self.receipt.write_text(json.dumps(value))

    def text(self, bound=True):
        return guide.render_text(guide.build_prerequisite_guide(self.value, bound))

    def test_completed_exact_run_binds_without_config_or_native_reads(self):
        with mock.patch('p1401.hwcapture.collect', side_effect=AssertionError('native call'), create=True), \
             mock.patch.object(guide, 'build_guide', side_effect=AssertionError('EFI path')):
            report, bound = guide.load_prerequisite(self.report, TOKEN)
        self.assertEqual(report, self.value)
        self.assertTrue(bound)
        self.assertFalse((self.root / 'config.plist').exists())

    def test_unbound_import_and_wrong_or_missing_token_are_not_current_pc(self):
        for token in [None, '2' * 32, 'invalid']:
            with self.subTest(token=token):
                self.assertFalse(guide.load_prerequisite(self.report, token)[1])
        self.receipt.unlink()
        self.assertFalse(guide.load_prerequisite(self.report, TOKEN)[1])
        text = self.text(False)
        self.assertIn('not verified observations of this PC', text)
        self.assertNotIn('This report matches', text)
        self.assertNotIn('A firmware change or a supported alternate', text)

    def test_changed_failed_and_incomplete_receipts_do_not_bind(self):
        for changes in [{'scan_status': 'failed'}, {'phase': 'sniffer'}, {'report_sha256': '0' * 64}]:
            with self.subTest(changes=changes):
                self.bind(**changes)
                self.assertFalse(guide.load_prerequisite(self.report, TOKEN)[1])
        self.bind()
        self.report.write_text(self.report.read_text() + ' ')
        self.assertFalse(guide.load_prerequisite(self.report, TOKEN)[1])

    def test_replaced_report_and_receipt_cannot_bind_previously_parsed_bytes(self):
        original = scan_evidence.load_for_report
        def replace(path):
            self.report.write_text(json.dumps({'Storage Controllers': {'Other controller': {}}}))
            self.bind()
            return original(path)
        with mock.patch.object(scan_evidence, 'load_for_report', side_effect=replace):
            report, bound = guide.load_prerequisite(self.report, TOKEN)
        self.assertEqual(report, self.value)
        self.assertFalse(bound)

    def test_symlink_oversized_and_non_dictionary_reports_refuse(self):
        link = self.root / 'link.json'; link.symlink_to(self.report)
        with self.assertRaises(guide.GuideError): guide.load_prerequisite(link, TOKEN)
        self.report.write_bytes(b'x' * (16 * 1024 * 1024 + 1))
        with self.assertRaises(guide.GuideError): guide.load_prerequisite(self.report, TOKEN)
        self.report.write_text('[]')
        with self.assertRaises(guide.GuideError): guide.load_prerequisite(self.report, TOKEN)

    def test_storage_observation_is_not_current_mode_or_boot_drive_claim(self):
        text = self.text()
        self.assertIn('Intel VMD Controller', text)
        self.assertIn('do not establish which drive', text)
        self.assertIn('storage prerequisite', text)
        self.assertNotIn('Your drive controller is in RAID mode', text)
        self.assertNotIn('SATA Mode to AHCI', text)
        self.assertNotIn('Storage for', text)

    def test_recovery_vendor_migration_and_no_security_commands(self):
        text = self.text()
        for required in ['Back up', 'Windows recovery media', 'recovery key', 'exact model',
                         'RAID/Optane', 'INACCESSIBLE_BOOT_DEVICE', 'generic Safe Mode', 'fresh scan']:
            self.assertIn(required, text)
        for forbidden in ['bcdedit /', 'mbr2gpt /', 'Secure Boot ->', 'TPM ->', 'VMD off', 'Set SATA Mode']:
            self.assertNotIn(forbidden, text)
        self.assertTrue(all(not step.settings for step in guide.build_prerequisite_guide(self.value, True)))

    def test_absent_or_malformed_storage_never_invents_vmd(self):
        for storage in [None, [], 'Intel VMD', {'AHCI controller': {}}]:
            self.value['Storage Controllers'] = storage
            self.assertNotIn('Review the reported storage controllers', self.text())

    def test_controller_display_is_bounded_and_html_escaped(self):
        self.value['Storage Controllers'] = {'<script>VMD' + str(i) + '</script>' + 'x' * 300: {} for i in range(90)}
        steps = guide.build_prerequisite_guide(self.value, True)
        line = steps[1].body[0]
        self.assertLess(len(line), 11000)
        page = guide.render_html({}, steps, mark=b'', prerequisites=True)
        self.assertIn('&lt;script&gt;', page)
        self.assertNotIn('<script>VMD', page)
        self.assertIn('Firmware Prerequisite Review', page)
        self.assertNotIn('settings below follow your scan and EFI', page)

    def test_real_cli_creates_only_html_and_preserves_existing_efi(self):
        efi = self.root / 'efi/EFI/OC'; efi.mkdir(parents=True)
        config = efi / 'config.plist'; config.write_bytes(b'preserve')
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        target = self.root / 'firmware.html'
        result = subprocess.run([sys.executable, '-m', 'p1401.guide', '--bios-only', str(self.report),
                                 '--run-id', TOKEN, '--html', str(target)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(target.is_file())
        for name, data in before.items(): self.assertEqual((self.root / name).read_bytes(), data)
        after = {p.relative_to(self.root) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(after - set(before), {Path('firmware.html')})
        self.assertIn('completed Check this PC', target.read_text())

    def test_cli_import_is_review_only_no_config_needed(self):
        self.receipt.unlink()
        result = subprocess.run([sys.executable, '-m', 'p1401.guide', '--bios-only', str(self.report)],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('not verified observations', result.stdout)

    def test_completed_efi_guide_still_uses_actual_config(self):
        config = {'Kernel': {'Quirks': {'AppleXcpmCfgLock': True, 'DisableIoMapper': True}}}
        text = guide.render_text(guide.build_guide(self.value, config, bitlocker='Off'))
        self.assertIn('your EFI already works around CFG Lock', text)
        self.assertNotIn('VT-d ->', text)
        self.assertIn('Make the macOS stick', text)
        self.assertIn('Start from the stick', text)
        self.assertIn('Install macOS', text)

    def test_vmd_refusal_is_self_contained_without_menu_guess(self):
        text = engine.stop_message(['Intel VMD controllers are not supported'])
        for value in ['Review firmware prerequisites', 'no EFI is required', 'back up', 'recovery key', 'migration']:
            self.assertIn(value, text)
        for value in ['look under Storage', 'Safe Mode once', 'turn off Intel VMD']:
            self.assertNotIn(value, text)

    def test_ui_has_prebuild_path_and_returns_without_usb_progress(self):
        source = (ROOT / 'windows/App/MainForm.cs').read_text()
        self.assertIn('scanned = true; LoadFacts(); await PrepareFirmwareGuide();', source)
        prepare = source[source.index('async Task PrepareFirmwareGuide()'):source.index('async void OnNext()')]
        self.assertIn('p1401.guide --bios-only ', prepare)
        self.assertIn('" --run-id " + scanRunId', prepare)
        self.assertNotIn('config.plist', prepare)
        self.assertNotIn('p1401 build', prepare)
        self.assertIn('(page == 1 || page == 2)', source)
        self.assertIn('showingPrerequisites = false; Go(prerequisiteReturnPage); return;', source)
        self.assertIn('if (page == 4 && !built) { Go(2); return; }', source)
        self.assertIn('next.Enabled = built;', source)


if __name__ == '__main__': unittest.main()
