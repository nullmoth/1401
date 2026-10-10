"""A machine whose own boots showed what it needs gets those settings on every build (Jake 10-09: keep each machine
that works and build it in). The table is known_machines.json; a non-matching machine is untouched."""
import os
import plistlib
import tempfile
import unittest

from p1401 import engine, policy


def build(board, cpu):
    t = tempfile.mkdtemp()
    path = os.path.join(t, "config.plist")
    cfg = {"NVRAM": {"Add": {}, "Delete": {}}, "Kernel": {"Add": [], "Patch": [], "Quirks": {}},
           "Booter": {"Quirks": {"DevirtualiseMmio": False, "SetupVirtualMap": False}}, "Misc": {}, "ACPI": {"Add": []},
           "UEFI": {"Drivers": [], "Quirks": {}}, "PlatformInfo": {"Generic": {}}}
    with open(path, "wb") as f:
        plistlib.dump(cfg, f)
    res = engine.BuildResult(ok=True, out_dir=t, macos_version="24.6.0", hardware={
        "Motherboard": {"Name": board, "Chipset": "X670"}, "CPU": {"Manufacturer": "AMD", "Processor Name": cpu}, "GPU": {}})
    changes = policy.apply(path, res, engine.Policy())
    return plistlib.load(open(path, "rb"))["Booter"]["Quirks"], [c for c in changes if c["rule"] == "known-machine"]


class KnownMachines(unittest.TestCase):
    def test_a_known_board_and_cpu_gets_its_recorded_settings(self):
        q, ch = build("ASUSTeK COMPUTER INC. ROG STRIX X670E-E GAMING WIFI", "AMD Ryzen 9 9950X3D 16-Core Processor")
        self.assertEqual((q["DevirtualiseMmio"], q["SetupVirtualMap"]), (True, True))
        self.assertTrue(ch)

    def test_the_same_board_with_another_cpu_is_not_matched(self):
        q, ch = build("ASUSTeK COMPUTER INC. ROG STRIX X670E-E GAMING WIFI", "AMD Ryzen 7 7800X3D 8-Core Processor")
        self.assertEqual(ch, [])

    def test_every_table_row_names_its_source_and_status(self):
        for m in policy._known_machines():
            self.assertTrue(m["board"] and m["cpu"] and m["source"])
            self.assertIn(m["status"], ("works", "fix-sent"))


if __name__ == "__main__":
    unittest.main()
