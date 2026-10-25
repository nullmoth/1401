"""A check run under Wine (paths like Z:\\home\\...) stops before the hardware scan with one clear sentence.

Wine's WMI has no device database: Win32_PnPEntity raised DISP_E_EXCEPTION three times and the scan gave up with
"Windows could not read its device database (WMI) 3 times", blaming a Windows that was never there."""
import unittest
from pathlib import Path
from types import SimpleNamespace

from p1401 import wine

ROOT = Path(__file__).resolve().parents[1]


def ntdll(**exports):
    return SimpleNamespace(**exports)


def no_key(root, path):
    raise OSError(2, 'The system cannot find the file specified')


class WineDetection(unittest.TestCase):
    def test_wines_ntdll_export_names_it(self):
        fn = lambda: b'9.0'  # noqa: E731
        got = wine.version(load_ntdll=lambda: ntdll(wine_get_version=fn), open_key=no_key)
        self.assertEqual(got, '9.0')

    def test_wines_registry_key_names_it_when_ntdll_does_not(self):
        opened = []

        def open_key(root, path):
            opened.append((root, path))
            if root == 'HKEY_LOCAL_MACHINE':
                return object()
            raise OSError(2, 'missing')
        got = wine.version(load_ntdll=lambda: ntdll(), open_key=open_key, unix_root=lambda: True)
        self.assertEqual(got, 'registry')
        self.assertEqual(opened, [('HKEY_CURRENT_USER', r'Software\Wine'), ('HKEY_LOCAL_MACHINE', r'Software\Wine')])

    def test_a_leftover_wine_key_on_real_windows_is_not_wine(self):
        # 1401 #99: a real PC refused because some other software had left a Software\Wine key
        got = wine.version(load_ntdll=lambda: ntdll(), open_key=lambda root, path: object(), unix_root=lambda: False)
        self.assertIsNone(got)

    def test_wines_export_alone_still_names_it_without_a_unix_root(self):
        got = wine.version(load_ntdll=lambda: ntdll(wine_get_version=lambda: b'9.0'), open_key=no_key, unix_root=lambda: False)
        self.assertEqual(got, '9.0')

    def test_real_windows_is_not_wine(self):
        self.assertIsNone(wine.version(load_ntdll=lambda: ntdll(), open_key=no_key))

    def test_an_ntdll_that_cannot_load_does_not_count_as_wine(self):
        def broken():
            raise OSError('no ntdll')
        self.assertIsNone(wine.version(load_ntdll=broken, open_key=no_key))

    def test_the_message_says_what_wine_cannot_do_and_what_to_do(self):
        self.assertIn('needs real Windows', wine.MESSAGE)
        self.assertIn('Wine cannot read the hardware', wine.MESSAGE)
        self.assertIn('run 1401 there', wine.MESSAGE)

    def test_the_scan_controller_stops_on_wine_before_the_sniffer(self):
        source = (ROOT / 'p1401/scan.py').read_text()
        controller = source[source.index('def _child('):source.index('def selftest(')]
        self.assertLess(controller.index('wine.version()'), controller.index('hwcapture.collect'))
        self.assertIn('return 1', controller[controller.index('wine.version()'):controller.index('hwcapture.collect')])

    def test_the_app_checks_for_wine_before_starting_the_scan(self):
        checks = (ROOT / 'windows/App/SystemChecks.cs').read_text()
        self.assertIn('public static bool UnderWine()', checks)
        self.assertIn('"wine_get_version"', checks)
        self.assertIn(r'@"Software\Wine"', checks)
        self.assertIn('needs real Windows; Wine cannot read the hardware', checks)
        form = (ROOT / 'windows/App/MainForm.cs').read_text()
        scan_step = form[form.index('if (page == 1 && !scanned)'):form.index('"p1401.scan "')]
        self.assertIn('SystemChecks.UnderWine()', scan_step)
        self.assertIn('SystemChecks.WineMessage', scan_step)


if __name__ == '__main__':
    unittest.main()
