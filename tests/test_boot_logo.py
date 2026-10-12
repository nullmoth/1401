"""Exercise EFI logo defaults through the complete policy pass on disposable configs."""
import copy
import pathlib
import plistlib
import tempfile
import unittest
from unittest import mock
from p1401 import engine, policy
BASE = {'NVRAM': {'Add': {}, 'Delete': {}}, 'Kernel': {'Add': [], 'Patch': [], 'Quirks': {}},
        'Booter': {'Quirks': {}}, 'Misc': {'Tools': [{'Path': 'Recovery.efi', 'Enabled': True}]},
        'ACPI': {'Add': []}, 'PlatformInfo': {'Generic': {}},
        'UEFI': {'Quirks': {}, 'Drivers': [{'Path': 'OpenRuntime.efi', 'Enabled': True, 'HideVerbose': False},
                                         {'Path': 'HfsPlus.efi', 'Enabled': True}]}}
class BootLogo(unittest.TestCase):
    def apply(self, entries=None, opt=False):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory); config = root / 'config.plist'
            before = copy.deepcopy(BASE); before['UEFI']['Drivers'] += entries or []
            config.write_bytes(plistlib.dumps(before))
            result = engine.BuildResult(ok=True, out_dir=directory, macos_version='24.6.0', hardware={})
            changes = policy.apply(str(config), result, engine.Policy(boot_logo=opt))
            after = plistlib.loads(config.read_bytes())
            self.assertEqual(after['UEFI']['Drivers'][:2], before['UEFI']['Drivers'][:2])
            self.assertEqual(after['Misc']['Tools'], before['Misc']['Tools'])
            return after['UEFI']['Drivers'], [c for c in changes if c['rule'] == 'boot-logo'], (root / 'Drivers/NullMothLogo.efi').is_file()
    def test_default_policy_omits_the_optional_driver(self):
        self.assertFalse(engine.Policy().boot_logo)
        with mock.patch('shutil.copyfile', side_effect=AssertionError('Unexpected EFI file write')):
            drivers, changes, copied = self.apply()
        self.assertEqual(drivers, BASE['UEFI']['Drivers']); self.assertFalse(changes or copied)
    def test_default_disables_only_an_existing_enabled_logo(self):
        entry = {'Path': 'NullMothLogo.efi', 'Enabled': True, 'Arguments': '', 'Comment': 'custom'}
        drivers, changes, copied = self.apply([entry])
        self.assertEqual(drivers[2], dict(entry, Enabled=False)); self.assertEqual(len(changes), 1); self.assertFalse(copied)
    def test_already_disabled_logo_stays_disabled(self):
        entry = {'Path': 'NullMothLogo.efi', 'Enabled': False, 'Arguments': ''}
        drivers, changes, copied = self.apply([entry])
        self.assertEqual(drivers[2], entry); self.assertFalse(changes or copied)
    def test_explicit_opt_in_restores_an_existing_disabled_entry(self):
        entry = {'Path': 'NullMothLogo.efi', 'Enabled': False, 'Arguments': '', 'Comment': 'custom'}
        drivers, changes, copied = self.apply([entry], opt=True)
        self.assertEqual(drivers[2], dict(entry, Enabled=True))
        self.assertEqual(len(drivers), 3)
        self.assertTrue(copied)
        self.assertEqual(len(changes), 1)
    def test_explicit_opt_in_copies_one_logo_with_existing_schema(self):
        drivers, changes, copied = self.apply(opt=True)
        logos = [d for d in drivers if d.get('Path') == 'NullMothLogo.efi']
        self.assertEqual(len(logos), 1); self.assertTrue(logos[0]['Enabled'] and copied)
        self.assertIn('HideVerbose', logos[0]); self.assertEqual(len(changes), 1)
if __name__ == '__main__': unittest.main()
