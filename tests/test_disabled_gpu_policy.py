"""Validate policy against exact labels emitted by the upstream customizer."""
import copy
import os
import pathlib
import platform
import plistlib
import subprocess
import tempfile
import unittest
import zipfile

from p1401 import engine, nullmoth, policy, validate


class DisabledGpuPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine._load_engine()
        from Scripts.hardware_customizer import HardwareCustomizer
        cls.customizer = HardwareCustomizer
        archive = pathlib.Path(os.environ.get('OPENCORE_TEST_ZIP',
                               str(pathlib.Path(validate.CACHE) / 'OpenCore-1.0.8-RELEASE.zip')))
        if not archive.is_file():
            raise unittest.SkipTest('Matching OpenCore 1.0.8 archive required')
        with zipfile.ZipFile(archive) as z:
            cls.sample = z.read('Docs/Sample.plist')
            tool = {'Windows': 'ocvalidate.exe', 'Linux': 'ocvalidate.linux'}.get(platform.system(), 'ocvalidate')
            cls.validator = z.read('Utilities/ocvalidate/' + tool)

    def gpu(self, maker='NVIDIA', device='10DE-2D04', kind='Discrete GPU'):
        return {'Manufacturer': maker, 'Device ID': device, 'Device Type': kind,
                'Compatibility': nullmoth.SEQUOIA}

    def disable(self, report, name):
        customizer = self.customizer()
        customizer.customized_hardware = copy.deepcopy(report)
        customizer.disabled_devices = {}
        customizer._disable_device('GPU', name, report['GPU'][name])
        return {n: g['Device ID'] for n, g in customizer.disabled_devices.items()}

    def apply(self, report, disabled, macos='24.6.0', whatevergreen=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            config = root / 'config.plist'
            cfg = plistlib.loads(self.sample)
            cfg['NVRAM']['Add'][policy.BOOT]['boot-args'] = '-v'
            cfg['NVRAM']['Add'][policy.BOOT]['csr-active-config'] = bytes(4)
            if whatevergreen:
                cfg['Kernel']['Add'] = [{
                    'Arch': 'Any', 'BundlePath': bundle + '.kext', 'Comment': 'GPU policy fixture',
                    'Enabled': True, 'ExecutablePath': 'Contents/MacOS/' + bundle, 'MaxKernel': '',
                    'MinKernel': '', 'PlistPath': 'Contents/Info.plist'} for bundle in ['Lilu', 'WhateverGreen']]
            config.write_bytes(plistlib.dumps(cfg))
            result = engine.BuildResult(ok=True, out_dir=str(root), macos_version=macos,
                                        hardware=report, disabled_devices=disabled)
            changes = policy.apply(str(config), result, engine.Policy())
            fixed = plistlib.loads(config.read_bytes())
            validator = root / ('ocvalidate.exe' if platform.system() == 'Windows' else 'ocvalidate')
            validator.write_bytes(self.validator)
            validator.chmod(0o755)
            checked = subprocess.run([str(validator), str(config)], capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            return fixed, changes

    def test_actual_customizer_gpu_label_does_not_activate_disabled_driver(self):
        report = {'GPU': {'Discrete card': self.gpu()}}
        disabled = self.disable(report, 'Discrete card')
        self.assertEqual(set(disabled), {'GPU: Discrete card'})
        cfg, changes = self.apply(report, disabled)
        nv = cfg['NVRAM']['Add'][policy.BOOT]
        self.assertEqual(nv['boot-args'], '-v')
        self.assertEqual(nv['csr-active-config'], bytes(4))
        self.assertFalse(any(c['rule'].startswith('nullmoth-') for c in changes))

    def test_compatibility_filter_label_is_respected(self):
        report = {'GPU': {'Discrete card': self.gpu()}}
        cfg, _ = self.apply(report, {'Discrete GPU: Discrete card': '10DE-2D04'})
        self.assertNotIn('nvaccel=1', cfg['NVRAM']['Add'][policy.BOOT]['boot-args'])

    def test_identical_device_ids_do_not_disable_another_selected_card(self):
        report = {'GPU': {'Selected card': self.gpu(), 'Disabled card': self.gpu()}}
        disabled = self.disable(report, 'Disabled card')
        cfg, _ = self.apply(report, disabled)
        self.assertIn('nvaccel=1', cfg['NVRAM']['Add'][policy.BOOT]['boot-args'])

    def test_disabled_integrated_gpu_does_not_preserve_conflicting_tahoe_driver(self):
        report = {'GPU': {'Integrated card': self.gpu('Intel', '8086-9BC5', 'Integrated GPU'),
                          'Discrete card': self.gpu('AMD', '1002-73BF')}}
        disabled = {'Integrated GPU: Integrated card': '8086-9BC5'}
        cfg, _ = self.apply(report, disabled, '25.0.0', whatevergreen=True)
        self.assertFalse(next(k for k in cfg['Kernel']['Add'] if k['BundlePath'] == 'WhateverGreen.kext')['Enabled'])

    def test_disabled_discrete_gpu_does_not_remove_required_integrated_driver(self):
        report = {'GPU': {'Integrated card': self.gpu('Intel', '8086-9BC5', 'Integrated GPU'),
                          'Discrete card': self.gpu('AMD', '1002-73BF')}}
        disabled = self.disable(report, 'Discrete card')
        cfg, _ = self.apply(report, disabled, '25.0.0', whatevergreen=True)
        self.assertTrue(next(k for k in cfg['Kernel']['Add'] if k['BundlePath'] == 'WhateverGreen.kext')['Enabled'])


if __name__ == '__main__':
    unittest.main()
