"""The bundled Python must see only its own packages.

A check run from %USERPROFILE%\\Desktop\\1401 failed inside the engine's own site-packages with "module 'certifi' has no
attribute 'where'" and "module 'win32com' has no attribute '__gen_path__'": that PC's own Python had a PYTHONPATH and a
user site-packages, and the portable interpreter imported those first. The app starts the engine isolated (-E -s, no
PYTHON* path variables), and the engine starts its own workers with the same options."""
import unittest
from pathlib import Path
from types import SimpleNamespace

from p1401 import scan

ROOT = Path(__file__).resolve().parents[1]


class AppLaunch(unittest.TestCase):
    def test_the_app_starts_python_isolated_from_the_pcs_own_python(self):
        source = (ROOT / 'windows/App/Engine.cs').read_text()
        self.assertIn('PythonFlags = "-E -s -B -X utf8 -u"', source)
        self.assertIn('new ProcessStartInfo(Python, PythonFlags + " -m " + args)', source)
        removed = source[source.index('foreach (var name in new[] { "PYTHONPATH"'):source.index('psi.EnvironmentVariables.Remove(name)')]
        for name in ('"PYTHONPATH"', '"PYTHONHOME"', '"PYTHONSTARTUP"', '"PYTHONUSERBASE"'):
            self.assertIn(name, removed)
        self.assertIn('psi.EnvironmentVariables["PYTHONNOUSERSITE"] = "1"', source)
        # -I would also drop the working directory from the import path, and -m p1401 needs it there.
        self.assertNotIn('"-I', source)


class WorkerFlags(unittest.TestCase):
    def flags(self, **values):
        base = dict(isolated=0, ignore_environment=0, no_user_site=0, dont_write_bytecode=0, utf8_mode=0)
        base.update(values)
        return SimpleNamespace(**base)

    def test_the_apps_options_reach_the_scan_worker(self):
        got = scan.interpreter_flags(self.flags(ignore_environment=1, no_user_site=1, dont_write_bytecode=1, utf8_mode=1))
        self.assertEqual(got, ['-E', '-s', '-B', '-X', 'utf8'])

    def test_a_plain_interpreter_adds_nothing(self):
        self.assertEqual(scan.interpreter_flags(self.flags()), [])

    def test_isolated_mode_is_one_option_not_three(self):
        self.assertEqual(scan.interpreter_flags(self.flags(isolated=1, ignore_environment=1, no_user_site=1)), ['-I'])

    def test_the_real_interpreters_flags_are_a_list_of_options(self):
        got = scan.interpreter_flags()
        self.assertIsInstance(got, list)
        self.assertTrue(all(x.startswith('-') or x == 'utf8' for x in got), got)


if __name__ == '__main__':
    unittest.main()
