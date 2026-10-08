import hashlib
import pathlib
import tempfile
import unittest
from p1401 import report


class AcpiFingerprints(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)

    def test_probe_table_hash_is_exact_and_contains_no_path_or_contents(self):
        data = b'DSDT' + b'private table contents'
        (self.root / 'dsdt.aml').write_bytes(data)
        (self.root / 'apic.dat').write_bytes(b'APIC' + b'interrupt table')
        (self.root / 'ssdt.aml').write_bytes(b'SSDT' + b'ignored table')
        fingerprints = report.acpi_fingerprints(str(self.root))
        dsdt = next(x for x in fingerprints if x['signature'] == 'DSDT')
        self.assertEqual(dsdt['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(dsdt['size'], len(data))
        self.assertEqual(len(fingerprints), 2)
        self.assertNotIn('private', str(fingerprints))
        self.assertNotIn(str(self.root), str(fingerprints))

    def test_unrecognized_or_oversized_inputs_are_not_exported(self):
        (self.root / 'dsdt.aml').write_bytes(b'not an ACPI table')
        (self.root / 'apic.aml').write_bytes(b'APIC' + bytes(8 * 1024 * 1024))
        self.assertEqual(report.acpi_fingerprints(str(self.root)), [])

    def test_missing_directory_or_symlink_does_not_read_unrelated_data(self):
        outside = self.root / 'outside.txt'
        outside.write_bytes(b'DSDT' + b'private')
        try:
            (self.root / 'linked.aml').symlink_to(outside)
        except (OSError, NotImplementedError):
            pass
        self.assertEqual(report.acpi_fingerprints(str(self.root)), [])
        self.assertEqual(report.acpi_fingerprints(str(self.root / 'missing')), [])
