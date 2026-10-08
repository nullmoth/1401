"""Bind scan, device choices and written EFI without claiming hardware qualification."""
import copy
import json
import pathlib
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from p1401 import machine_handoff, usbwriter, guide

class MachineHandoff(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.build = self.root / 'build'
        (self.build / 'EFI/OC').mkdir(parents=True)
        (self.build / 'EFI/OC/config.plist').write_bytes(b'validated configuration')
        self.scan = self.root / 'Report.json'
        self.report = {
            'Motherboard': {'Name': 'Board revision A', 'Chipset': 'B860', 'Version': 'A', 'Serial': 'private'},
            'CPU': {'Processor Name': 'Processor', 'Core Count': 20, 'Thread Count': 20, 'CPUID': 'C0662'},
            'GPU': {'Selected': {'Device ID': '10DE-2D04', 'Subsystem ID': '1462-5102', 'PCI Path': 'PciRoot(0)/Pci(1,0)', 'Device Type': 'Discrete GPU'},
                    'Disabled': {'Device ID': '10DE-2D04', 'Subsystem ID': '1462-5102', 'PCI Path': 'PciRoot(0)/Pci(2,0)', 'Device Type': 'Discrete GPU'}},
            'Network': {'Ethernet': {'Device ID': '8086-5502', 'MAC': 'private'}}}
        self.scan.write_text(json.dumps(self.report))
        self.result = SimpleNamespace(hardware=self.report, disabled_devices={'GPU: Disabled': '10DE-2D04'},
                                      acpi_fingerprints=[{'signature': 'APIC', 'sha256': 'a' * 64, 'size': 44}],
                                      out_dir=str(self.build), macos_version='24.6.0', smbios='iMacPro1,1')
    def create(self):
        return machine_handoff.create(str(self.scan), self.result)
    def test_full_identity_and_disabled_choices_survive_handoff(self):
        value = self.create()
        self.assertEqual(machine_handoff.verified(str(self.build), str(self.scan)), value)
        destination = self.root / 'installer'
        machine_handoff.copy_to_installer(value, str(destination))
        readback = json.loads((destination / 'NullMoth/system-profile.json').read_text())
        self.assertEqual(readback['hardware']['CPU']['CPUID'], 'C0662')
        self.assertEqual(readback['hardware']['CPU']['Core Count'], 20)
        self.assertNotEqual(readback['hardware']['GPU'][0]['PCI Path'], readback['hardware']['GPU'][1]['PCI Path'])
        self.assertEqual(readback['disabled_devices'], {'GPU: Disabled': '10DE-2D04'})
        self.assertEqual(readback['acpi_fingerprints'], self.result.acpi_fingerprints)
        self.assertNotIn('private', json.dumps(readback))
        self.assertEqual(readback['identity_status'], 'build_bound_live_unverified')
        self.assertEqual(readback['qualification']['usb_ports'], 'mapping_required')
        self.assertEqual(readback['qualification']['fan_control'], 'not_assessed')
    def test_same_named_other_board_scan_is_refused_before_disk_writes(self):
        self.create()
        other = copy.deepcopy(self.report)
        other['Motherboard']['Name'] = 'Board revision B'
        self.scan.write_text(json.dumps(other))
        disk = {'Number': 3, 'BusType': 'USB', 'Size': 16 * 10**9}
        with patch.object(usbwriter, 'list_disks', return_value=[disk]), patch.object(usbwriter, 'write') as write, patch('p1401.apple.image_info') as apple:
            with self.assertRaisesRegex(RuntimeError, 'scan changed'):
                usbwriter.cli_write(['3', str(self.build), '24', '--profile', str(self.scan)])
            write.assert_not_called(); apple.assert_not_called()
    def test_changed_added_or_deleted_efi_file_is_refused(self):
        for action in ('changed', 'added', 'deleted'):
            with self.subTest(action=action):
                target = self.build / 'EFI/OC/config.plist'
                target.write_bytes(b'validated configuration')
                self.create()
                if action == 'changed': target.write_bytes(b'other configuration')
                elif action == 'added': (self.build / 'EFI/OC/extra.efi').write_bytes(b'other boot file')
                else: target.unlink()
                with self.assertRaisesRegex(RuntimeError, 'EFI changed|EFI is incomplete'):
                    machine_handoff.verified(str(self.build))
                if action == 'added': (self.build / 'EFI/OC/extra.efi').unlink()
    def test_missing_profile_cannot_report_current_machine_ready(self):
        with self.assertRaisesRegex(RuntimeError, 'no verified machine profile'):
            machine_handoff.verified(str(self.build), str(self.scan))
    def test_changed_device_choices_are_refused_before_disk_commands(self):
        value = self.create()
        value['disabled_devices'] = {}
        disk = {'Number': 3, 'BusType': 'USB', 'Size': 16 * 10**9}
        with patch('p1401.validate.validate', return_value={'ok': True}), patch.object(usbwriter, '_ps') as commands, patch('p1401.rawdisk.wipe_mbr_fat32') as wipe:
            with self.assertRaisesRegex(usbwriter.UsbError, 'profile changed before erasing'):
                usbwriter.write(disk, str(self.build), {}, machine_profile=value)
            commands.assert_not_called(); wipe.assert_not_called()
    def test_profile_readback_failure_is_not_ready(self):
        value = self.create()
        import builtins
        original = builtins.open
        def changed(path, mode='r', *args, **kwargs):
            if str(path).endswith('system-profile.json') and mode == 'rb':
                import io
                return io.BytesIO(b'corrupted profile')
            return original(path, mode, *args, **kwargs)
        with patch('builtins.open', side_effect=changed):
            with self.assertRaisesRegex(RuntimeError, 'stick is not ready'):
                machine_handoff.copy_to_installer(value, str(self.root / 'installer'))

class DisabledGpuGuide(unittest.TestCase):
    def report(self):
        return {'Motherboard': {'Name': 'Board', 'Platform': 'Laptop'}, 'CPU': {'Manufacturer': 'Intel'},
                'GPU': {'Integrated': {'Manufacturer': 'Intel', 'Device Type': 'Integrated GPU', 'Resizable BAR': 'Enabled'},
                        'Discrete': {'Manufacturer': 'AMD', 'Device Type': 'Discrete GPU', 'Resizable BAR': 'Disabled'}}}
    def test_disabled_integrated_gpu_gets_no_dvmt_instruction(self):
        settings = guide.bios_settings(self.report(), {}, {'Integrated GPU: Integrated': '8086-0000'})
        self.assertFalse(any('DVMT' in s.name for s in settings))
    def test_disabled_discrete_gpu_does_not_contradict_selected_rebar_setting(self):
        settings = guide.bios_settings(self.report(), {}, {'GPU: Discrete': '1002-0000'})
        self.assertFalse(any('Re-Size' in s.name for s in settings))
    def test_unverified_board_menu_claims_are_not_exact(self):
        steps = guide.build_guide(self.report(), {})
        text = guide.render_text(steps)
        self.assertIn('exact model and board revision', text)
        cfg = {'NVRAM': {'Add': {guide.NVRAM_APPLE: {'boot-args': 'nvfb=1'}}}}
        settings = guide.bios_settings(self.report(), cfg)
        above = next(s for s in settings if s.name == 'Above 4G Decoding')
        self.assertIn('if unavailable, stop', above.if_missing)
        self.assertNotIn('Every board', above.if_missing)

if __name__ == '__main__': unittest.main()
