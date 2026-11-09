"""What a boot-stop report carries so the next one can be diagnosed: the ACPI facts, the shape of the stick's log, the
hardware class, and where a raw write failed. Synthetic tables."""
import os
import tempfile
import unittest

from p1401 import rawdisk, stop_fingerprint as sf
from tests.test_acpi_extra_processors import dsdt, MADT20
from tests.test_acpi_alib_shim import ssdt, IN_SB


def acpi_dir(files):
    t = tempfile.mkdtemp()
    for n, b in files.items():
        with open(os.path.join(t, n), "wb") as f:
            f.write(b)
    return t


LOG = "\n".join(["00:000 00:000 OC: Starting", "00:174 00:046 OCCPU: MP services threads 24 (enabled 20) - Success",
                 "00:220 00:046 OCCPU: Found 15th Gen Intel(R) Core(TM) Ultra 9 275HX", "03:050 01:200 OCB: EXITBS:START"])


class Fingerprint(unittest.TestCase):
    def test_acpi_facts_name_the_processor_mismatch_the_vendor_method_and_the_tables(self):
        d = acpi_dir({"DSDT.aml": dsdt(29), "APIC.aml": MADT20, "SSDT-3.aml": ssdt(IN_SB), "DMAR.aml": b"DMAR" + b"\0" * 60})
        f = sf.acpi_facts(d)
        self.assertEqual((f["dsdt"]["processor_devices"], f["madt"]["enabled_uids"]), (29, 20))
        self.assertEqual(f["alib_ssdts"], [{"file": "SSDT-3.aml", "oem_table_id": "Vortex"}])
        self.assertTrue(f["dmar_present"])
        self.assertEqual(f["ssdt_count"], 1)
        self.assertTrue(all(set(t) == {"file", "sig", "oem", "table_id", "len", "sha"} for t in f["tables"]))

    def test_the_log_shape_says_how_long_the_last_line_sat(self):
        f = sf.log_facts(LOG)
        self.assertEqual((f["lines"], f["last_gap_ms"], f["exitbs_reached"]), (4, 1200, True))
        self.assertEqual(f["last"][-1], "03:050 01:200 OCB: EXITBS:START")
        self.assertIn("275HX", f["cpu_found"])

    def test_hardware_class_flags_a_processor_without_graphics(self):
        h = sf.hardware_facts({"CPU": {"Processor Name": "12th Gen Intel(R) Core(TM) i5-12400F"}, "GPU": {"a": {"Device Type": "Discrete GPU"}}})
        self.assertTrue(h["cpu_without_igpu"]); self.assertEqual(h["gpu_kinds"], ["Discrete GPU"])
        self.assertFalse(sf.hardware_facts({"CPU": {"Processor Name": "Intel Core i5-12400"}})["cpu_without_igpu"])

    def test_a_part_that_fails_says_so_and_the_rest_stays(self):
        r = sf.record("/nonexistent", [LOG], {"CPU": {}})
        self.assertIn("notes", r["acpi"]); self.assertEqual(r["stick_logs"][0]["lines"], 4)
        self.assertEqual(r["schema"], 1)

    def test_no_paths_serials_or_user_names_ride_along(self):
        d = acpi_dir({"DSDT.aml": dsdt(3), "APIC.aml": MADT20})
        import json
        text = json.dumps(sf.record(d, [LOG], {"CPU": {"Processor Name": "X"}}))
        self.assertNotIn(d, text)
        self.assertNotIn(os.path.expanduser("~"), text)


class WriteFailure(unittest.TestCase):
    def test_the_line_says_where_how_big_and_whether_it_was_aligned(self):
        l = rawdisk.failure_line(5, 0, 1 << 20, 64 << 30, 512, False, 1)
        self.assertIn("Windows error 5", l); self.assertIn("(start of the disk, 0.00%)", l); self.assertIn("sector 512", l); self.assertIn("aligned True", l)
        l = rawdisk.failure_line(5, (64 << 30) - (1 << 20), 1 << 20, 64 << 30, 4096, True, 0)
        self.assertIn("end of the disk", l); self.assertIn("offline True", l)
        self.assertIn("aligned unknown", rawdisk.failure_line(5, 7, 100, 0))
        self.assertIn("aligned False", rawdisk.failure_line(5, 7, 100, 1 << 30, 512))


if __name__ == "__main__":
    unittest.main()
