"""A GPU Windows reports with neither a maker nor a PCI ID: its name names the maker (1.10 builds 10-10: 'NVIDIA GeForce
GT 730' stopped the build five times). The build goes on with a placeholder ID that matches no supported card (basic
display); a name that names no maker still stops with the old advice."""
import unittest

from p1401 import report


class GpuName(unittest.TestCase):
    def test_a_named_card_gets_its_maker_and_a_placeholder_id(self):
        out, notes = report.normalize({"GPU": {"NVIDIA GeForce GT 730": {"Manufacturer": "Unknown"}}})
        g = out["GPU"]["NVIDIA GeForce GT 730"]
        self.assertEqual((g["Manufacturer"], g["Device ID"]), ("NVIDIA", "10DE-0000"))
        self.assertIn("basic display", notes[-1])

    def test_radeon_and_iris_names_too(self):
        for name, want in (("AMD Radeon RX 580 Series", "1002-0000"), ("Intel(R) Iris(R) Xe Graphics", "8086-0000")):
            out, _ = report.normalize({"GPU": {name: {"Manufacturer": "Unknown"}}})
            self.assertEqual(out["GPU"][name]["Device ID"], want)

    def test_a_name_with_no_maker_still_stops(self):
        with self.assertRaisesRegex(RuntimeError, "Install your graphics card's driver"):
            report.normalize({"GPU": {"Microsoft Basic Display Adapter": {"Manufacturer": "Unknown"}}})

    def test_a_real_pci_id_is_never_replaced(self):
        out, _ = report.normalize({"GPU": {"NVIDIA GeForce GT 730": {"Manufacturer": "Unknown", "Device ID": "10DE-1287"}}})
        self.assertEqual(out["GPU"]["NVIDIA GeForce GT 730"]["Device ID"], "10DE-1287")


if __name__ == "__main__":
    unittest.main()
