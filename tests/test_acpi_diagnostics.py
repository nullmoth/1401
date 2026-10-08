import unittest
from types import SimpleNamespace
from p1401 import acpi_diagnostics

class Diagnostics(unittest.TestCase):
    def make_dsdt(self, result):
        runner = SimpleNamespace(run=lambda command: result)
        return SimpleNamespace(r=runner, iasl='/tools/iasl')

    def test_actual_failure_is_retained_and_returned(self):
        result = ('output', 'AE_ALREADY_EXISTS at C:\\Users\\private-account\\ACPI\\dsdt.aml', 1)
        dsdt = self.make_dsdt(result); original = dsdt.r.run; records = []
        with acpi_diagnostics.capture(dsdt, records):
            self.assertIs(dsdt.r.run({'args': ['/tools/iasl', '-dl', 'dsdt.aml']}), result)
        self.assertEqual(records[0]['tables'], ['dsdt.aml'])
        self.assertNotIn('private-account', records[0]['stderr'])
        self.assertIn('AE_ALREADY_EXISTS', records[0]['stderr'])
        self.assertIs(dsdt.r.run, original)

    def test_success_and_other_tools_are_not_collected(self):
        for executable, status in [('/tools/iasl', 0), ('/tools/other', 1)]:
            dsdt = self.make_dsdt(('', 'message', status)); records = []
            with acpi_diagnostics.capture(dsdt, records): dsdt.r.run({'args': [executable, 'dsdt.aml']})
            self.assertEqual(records, [])

    def test_bounds_and_restoration_on_exception(self):
        dsdt = self.make_dsdt(('', 'x' * 9000, 1)); original = dsdt.r.run; records = []
        with self.assertRaises(ValueError):
            with acpi_diagnostics.capture(dsdt, records):
                for i in range(20): dsdt.r.run({'args': ['/tools/iasl', 'dsdt.aml']})
                raise ValueError('loader stopped')
        self.assertEqual(len(records), 8)
        self.assertEqual(len(records[0]['stderr']), 4096)
        self.assertIs(dsdt.r.run, original)

if __name__ == '__main__': unittest.main()
