"""Exercise policy output with OpenCore's real sample and matching validator."""
import os
import pathlib
import platform
import plistlib
import subprocess
import tempfile
import unittest
import zipfile

from p1401 import engine, policy, validate


class MmioPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = os.environ.get('OPENCORE_TEST_ZIP', os.path.join(validate.CACHE, 'OpenCore-1.0.9-RELEASE.zip'))
        if not os.path.isfile(cls.archive):
            raise unittest.SkipTest('The OpenCore 1.0.9 release archive is required for these integration tests.')
        with zipfile.ZipFile(cls.archive) as archive:
            cls.sample = archive.read('Docs/Sample.plist')
            name = {'Windows': 'ocvalidate.exe', 'Linux': 'ocvalidate.linux'}.get(platform.system(), 'ocvalidate')
            cls.validator = archive.read('Utilities/ocvalidate/' + name)

    def exercise(self, manufacturer, chipset, enabled):
        with tempfile.TemporaryDirectory() as directory:
            config = pathlib.Path(directory) / 'config.plist'
            executable = pathlib.Path(directory) / 'ocvalidate'
            executable.write_bytes(self.validator)
            executable.chmod(0o755)
            cfg = plistlib.loads(self.sample)
            cfg['Booter']['Quirks']['DevirtualiseMmio'] = enabled
            cfg['Booter']['MmioWhitelist'] = [{'Address': 4275159040, 'Comment': 'MMIO regression', 'Enabled': True}]
            config.write_bytes(plistlib.dumps(cfg))
            before = subprocess.run([str(executable), str(config)], capture_output=True, text=True, timeout=30)
            if not enabled:
                self.assertNotEqual(before.returncode, 0)
                self.assertIn('MmioWhitelist', before.stdout)
            result = engine.BuildResult(ok=True, out_dir=directory, macos_version='24.6.0', hardware={
                'CPU': {'Manufacturer': manufacturer}, 'Motherboard': {'Chipset': chipset}, 'GPU': {}})
            changes = policy.apply(str(config), result, engine.Policy())
            after = subprocess.run([str(executable), str(config)], capture_output=True, text=True, timeout=30)
            self.assertEqual(after.returncode, 0, after.stdout + after.stderr)
            fixed = plistlib.loads(config.read_bytes())
            self.assertEqual(fixed['Booter']['MmioWhitelist'][0]['Enabled'], enabled and chipset == 'TRX40')
            unchanged = config.read_bytes()
            self.assertEqual(policy.apply(str(config), result, engine.Policy()), [])
            self.assertEqual(config.read_bytes(), unchanged)
            return changes

    def test_amd_quirk_already_disabled(self):
        self.exercise('AMD', 'B650', False)

    def test_amd_quirk_disabled_by_policy(self):
        self.exercise('AMD', 'B650', True)

    def test_intel_inert_whitelist(self):
        self.exercise('Intel', 'Z790', False)

    def test_threadripper_active_whitelist_preserved(self):
        self.exercise('AMD', 'TRX40', True)


if __name__ == '__main__':
    unittest.main()
