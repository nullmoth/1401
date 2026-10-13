"""Tahoe + the IOSkywalkFamily downgrade + Lucy on a Realtek port: Apple's own Realtek driver is blocked, only then."""
import copy
import pathlib
import plistlib
import tempfile
import unittest
from p1401 import engine, policy
SKYWALK = {'Arch': 'x86_64', 'Comment': 'Allow IOSkywalk Downgrade', 'Enabled': True,
           'Identifier': 'com.apple.iokit.IOSkywalkFamily', 'MaxKernel': '', 'MinKernel': '23.0.0', 'Strategy': 'Exclude'}
BASE = {'NVRAM': {'Add': {}, 'Delete': {}}, 'Kernel': {'Add': [], 'Patch': [], 'Quirks': {}, 'Block': []},
        'Booter': {'Quirks': {}}, 'Misc': {'Tools': []}, 'ACPI': {'Add': []}, 'PlatformInfo': {'Generic': {}},
        'UEFI': {'Quirks': {}, 'Drivers': []}}
class TahoeRealtekEthernet(unittest.TestCase):
    def apply(self, macos, kexts, skywalk=True):
        with tempfile.TemporaryDirectory() as directory:
            config = pathlib.Path(directory) / 'config.plist'
            cfg = copy.deepcopy(BASE)
            cfg['Kernel']['Add'] = [{'BundlePath': k, 'Enabled': True} for k in kexts]
            if skywalk:
                cfg['Kernel']['Block'].append(dict(SKYWALK))
            config.write_bytes(plistlib.dumps(cfg))
            result = engine.BuildResult(ok=True, out_dir=directory, macos_version=macos, hardware={})
            changes = policy.apply(str(config), result, engine.Policy())
            after = plistlib.loads(config.read_bytes())
            rl = [b for b in after['Kernel']['Block'] if b.get('Identifier') == 'com.apple.driver.AppleEthernetRL']
            return rl, [c for c in changes if c['rule'] == 'tahoe-realtek-ethernet']
    def test_tahoe_downgrade_with_lucy_blocks_apple_realtek(self):
        rl, changes = self.apply('25.99.99', ['IOSkywalkFamily.kext', 'RTL812xLucy.kext'])
        self.assertEqual(len(rl), 1); self.assertEqual(rl[0]['MinKernel'], '25.0.0'); self.assertEqual(rl[0]['Strategy'], 'Exclude')
        self.assertEqual(len(changes), 1)
    def test_sequoia_is_left_alone(self):
        self.assertEqual(self.apply('24.99.99', ['IOSkywalkFamily.kext', 'RTL812xLucy.kext']), ([], []))
    def test_no_downgrade_keeps_apple_realtek(self):
        self.assertEqual(self.apply('25.99.99', ['RTL812xLucy.kext'], skywalk=False), ([], []))
    def test_no_lucy_keeps_apple_realtek(self):
        # without Lucy Apple's driver is the port's only driver: blocking it would cost the Ethernet port
        self.assertEqual(self.apply('25.99.99', ['IOSkywalkFamily.kext']), ([], []))
    def test_older_lucy_name_counts_too(self):
        rl, _ = self.apply('25.99.99', ['IOSkywalkFamily.kext', 'LucyRTL8125Ethernet.kext'])
        self.assertEqual(len(rl), 1)
if __name__ == '__main__': unittest.main()
