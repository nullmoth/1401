"""The built EFI leaves the boot picker able to show the driver's "Remove NVIDIA driver" entry: the picker appears
(ShowPicker), it is not Apple's tool-less picker (PickerMode), and nothing is hidden behind Space (HideAuxiliary).

The config is validated by OpenCore's own ocvalidate before and after. The negative control runs the release-2.0
policy (the code before this fix) and shows it leaves ShowPicker off and the Apple picker in place."""
import os
import pathlib
import platform
import plistlib
import subprocess
import sys
import tempfile
import unittest
import zipfile

from p1401 import engine, policy, validate

REPO = pathlib.Path(__file__).resolve().parents[1]
OLD_REV = 'a68ccdd'


def result_for(directory):
    return engine.BuildResult(ok=True, out_dir=directory, macos_version='24.6.0',
                              hardware={'CPU': {'Manufacturer': 'Intel'}, 'Motherboard': {'Chipset': ''}, 'GPU': {}})


class PickerVisible(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        archive = os.environ.get('OPENCORE_TEST_ZIP', os.path.join(validate.CACHE, 'OpenCore-1.0.8-RELEASE.zip'))
        if not os.path.isfile(archive):
            raise unittest.SkipTest('The OpenCore 1.0.8 release archive is required for these integration tests.')
        with zipfile.ZipFile(archive) as z:
            cls.sample = z.read('Docs/Sample.plist')
            name = {'Windows': 'ocvalidate.exe', 'Linux': 'ocvalidate.linux'}.get(platform.system(), 'ocvalidate')
            cls.validator = z.read('Utilities/ocvalidate/' + name)
        # the release-2.0 p1401 package, imported under its own name so it does not clash with the one under test
        cls.oldroot = tempfile.mkdtemp(prefix='p1401-old-')
        tar = subprocess.run(['git', '-C', str(REPO), 'archive', OLD_REV, 'p1401'], capture_output=True, check=True)
        subprocess.run(['tar', '-x', '-C', cls.oldroot], input=tar.stdout, check=True)
        os.rename(os.path.join(cls.oldroot, 'p1401'), os.path.join(cls.oldroot, 'p1401legacy'))
        sys.path.insert(0, cls.oldroot)
        from p1401legacy import policy as oldpolicy  # noqa: PLC0415
        cls.oldpolicy = oldpolicy

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, 'oldroot', None):
            sys.path[:] = [p for p in sys.path if p != cls.oldroot]
            subprocess.run(['rm', '-rf', cls.oldroot])

    def _staged(self, directory, **boot):
        config = pathlib.Path(directory) / 'config.plist'
        executable = pathlib.Path(directory) / 'ocvalidate'
        executable.write_bytes(self.validator); executable.chmod(0o755)
        cfg = plistlib.loads(self.sample)
        cfg['Misc']['Boot'].update(boot)
        config.write_bytes(plistlib.dumps(cfg))
        ok = subprocess.run([str(executable), str(config)], capture_output=True, text=True, timeout=30)
        self.assertEqual(ok.returncode, 0, 'the crafted config must be valid before policy runs:\n' + ok.stdout)
        return config, executable

    def test_a_hidden_picker_is_made_able_to_show_the_remove_entry(self):
        with tempfile.TemporaryDirectory() as d:
            config, executable = self._staged(d, ShowPicker=False, PickerMode='Apple', HideAuxiliary=True)
            rules = [c["rule"] for c in policy.apply(str(config), result_for(d), engine.Policy())]
            boot = plistlib.loads(config.read_bytes())['Misc']['Boot']
            self.assertIs(boot['ShowPicker'], True)
            self.assertEqual(boot['PickerMode'], 'Builtin')
            self.assertIs(boot['HideAuxiliary'], False)
            for r in ('show-picker', 'picker-lists-tools', 'show-installer-entry'):
                self.assertIn(r, rules)
            after = subprocess.run([str(executable), str(config)], capture_output=True, text=True, timeout=30)
            self.assertEqual(after.returncode, 0, after.stdout + after.stderr)
            # idempotent: a second pass changes nothing more about the picker
            again = [c["rule"] for c in policy.apply(str(config), result_for(d), engine.Policy())]
            self.assertFalse({'show-picker', 'picker-lists-tools'} & set(again))

    def test_a_good_picker_is_left_alone(self):
        # negative control (the rule fires only when needed): an already-visible External/OpenCanopy picker is untouched
        with tempfile.TemporaryDirectory() as d:
            config, _ = self._staged(d, ShowPicker=True, PickerMode='External', HideAuxiliary=False)
            rules = [c["rule"] for c in policy.apply(str(config), result_for(d), engine.Policy())]
            boot = plistlib.loads(config.read_bytes())['Misc']['Boot']
            self.assertIs(boot['ShowPicker'], True)
            self.assertEqual(boot['PickerMode'], 'External')
            self.assertFalse({'show-picker', 'picker-lists-tools'} & set(rules))

    def test_negative_control_release_2_0_policy_leaves_the_picker_hidden(self):
        # the code before this fix handled HideAuxiliary but never ShowPicker or PickerMode, so the Remove entry stayed
        # unreachable on a config with the picker off and Apple's picker selected
        with tempfile.TemporaryDirectory() as d:
            config, _ = self._staged(d, ShowPicker=False, PickerMode='Apple', HideAuxiliary=True)
            self.oldpolicy.apply(str(config), result_for(d), engine.Policy())
            boot = plistlib.loads(config.read_bytes())['Misc']['Boot']
            self.assertIs(boot['ShowPicker'], False)
            self.assertEqual(boot['PickerMode'], 'Apple')


if __name__ == '__main__':
    unittest.main(verbosity=2)
