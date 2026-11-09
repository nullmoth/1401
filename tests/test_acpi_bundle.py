"""The ACPI bundle sent with Send logs (p1401/acpi_bundle.py): the tables replay needs, never the personal ones, capped."""
import os
import tempfile
import unittest
import zipfile

from p1401 import acpi_bundle as ab


def table(sig, size):
    return sig.encode() + (size - 4) * b"\0"


class Bundle(unittest.TestCase):
    def make(self, tables):
        d = tempfile.mkdtemp()
        for name, data in tables.items():
            open(os.path.join(d, name), "wb").write(data)
        out = os.path.join(tempfile.mkdtemp(), "acpi.zip")
        return ab.build(d, out), out

    def test_the_dsdt_and_ssdts_are_sent(self):
        r, out = self.make({"DSDT.aml": table("DSDT", 5000), "SSDT1.aml": table("SSDT", 900), "APIC.aml": table("APIC", 400)})
        self.assertEqual(sorted(r["sent"]), ["APIC.aml", "DSDT.aml", "SSDT1.aml"])
        self.assertIn("ACPI/DSDT.aml", zipfile.ZipFile(out).namelist())

    def test_the_windows_licence_the_logo_and_unknown_tables_are_never_sent(self):
        r, out = self.make({"DSDT.aml": table("DSDT", 5000), "MSDM.aml": table("MSDM", 100), "SLIC.aml": table("SLIC", 100),
                            "BGRT.aml": table("BGRT", 100), "XYZW.aml": table("XYZW", 100)})
        self.assertEqual(r["sent"], ["DSDT.aml"])
        self.assertEqual(sorted(x["file"] for x in r["left_out"]), ["BGRT.aml", "MSDM.aml", "SLIC.aml", "XYZW.aml"])
        self.assertFalse(any("MSDM" in n for n in zipfile.ZipFile(out).namelist() if n != "manifest.json"))

    def test_a_dump_over_the_cap_keeps_the_dsdt_and_says_what_it_left_out(self):
        tables = {"DSDT.aml": table("DSDT", 3 << 20)}
        for i in range(6):
            tables[f"SSDT{i}.aml"] = table("SSDT", 1 << 20)
        r, _ = self.make(tables)
        self.assertIn("DSDT.aml", r["sent"])
        self.assertLessEqual(r["bytes"], ab.MAX_TOTAL)
        self.assertTrue(any(x["why"] == "size cap" for x in r["left_out"]))

    def test_a_file_that_is_not_a_table_is_ignored(self):
        r, _ = self.make({"DSDT.aml": table("DSDT", 100), "notes.txt": b"hello"})
        self.assertEqual(r["sent"], ["DSDT.aml"])


if __name__ == "__main__":
    unittest.main()
