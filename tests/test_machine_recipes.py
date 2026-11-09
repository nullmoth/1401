"""Machine recipes (p1401/machine_recipes.json): the Dell XPS 13 Plus class gets the CPU topology fix that lets its
efficiency cores run, an existing CPU spoof survives it, and no other machine is touched."""
import os
import plistlib
import tempfile
import unittest

from p1401 import engine, policy


def build(board, cpu, emulate=None, quirks=None):
    t = tempfile.mkdtemp()
    path = os.path.join(t, "config.plist")
    cfg = {"NVRAM": {"Add": {}, "Delete": {}}, "Kernel": {"Add": [], "Patch": [], "Quirks": dict(quirks or {}), "Emulate": dict(emulate or {})},
           "Booter": {"Quirks": {"DevirtualiseMmio": False, "SetupVirtualMap": False}}, "Misc": {}, "ACPI": {"Add": []},
           "UEFI": {"Drivers": [], "Quirks": {}}, "PlatformInfo": {"Generic": {}}}
    with open(path, "wb") as f:
        plistlib.dump(cfg, f)
    res = engine.BuildResult(ok=True, out_dir=t, macos_version="25.0.0", hardware={
        "Motherboard": {"Name": board, "Chipset": "Raptor Lake-P", "Platform": "Laptop"},
        "CPU": {"Manufacturer": "Intel", "Processor Name": cpu, "Codename": "Raptor Lake"}, "GPU": {}})
    changes = policy.apply(path, res, engine.Policy())
    with open(path, "rb") as f:
        out = plistlib.load(f)
    return out["Kernel"], [c for c in changes if c["rule"] == "machine-recipe"]


XPS = "Dell Inc. XPS 13 9320"
CPU = "13th Gen Intel(R) Core(TM) i7-1360P"


class Recipes(unittest.TestCase):
    def test_the_xps_13_plus_gets_the_topology_fix_and_the_quirk_it_needs(self):
        k, ch = build(XPS, CPU)
        self.assertEqual(k["Emulate"]["Cpuid1Data"][4:8], bytes([0, 0, 128, 0]))
        self.assertEqual(k["Emulate"]["Cpuid1Mask"][4:8], bytes([0, 0, 255, 0]))
        self.assertTrue(k["Quirks"]["ProvideCurrentCpuInfo"])
        self.assertEqual(len(ch), 2)

    def test_an_existing_cpu_spoof_keeps_its_other_bits(self):
        spoof = bytes.fromhex("55060A00" + "00000000" * 3)
        mask = bytes.fromhex("FFFFFFFF" + "00000000" * 3)
        k, _ = build(XPS, CPU, {"Cpuid1Data": spoof, "Cpuid1Mask": mask})
        self.assertEqual(k["Emulate"]["Cpuid1Data"][:4], spoof[:4])
        self.assertEqual(k["Emulate"]["Cpuid1Mask"][:4], mask[:4])
        self.assertEqual(k["Emulate"]["Cpuid1Data"][6], 128)

    def test_a_second_pass_changes_nothing(self):
        cfg = {"Kernel": {"Emulate": {}}}
        self.assertTrue(policy.set_cpuid1_logical_per_package(cfg, 128))
        before = dict(cfg["Kernel"]["Emulate"])
        self.assertFalse(policy.set_cpuid1_logical_per_package(cfg, 128))
        self.assertEqual(cfg["Kernel"]["Emulate"], before)

    def test_another_laptop_or_another_cpu_is_untouched(self):
        for board, cpu in (("LENOVO 21HQ", CPU), (XPS, "11th Gen Intel(R) Core(TM) i7-1185G7")):
            k, ch = build(board, cpu)
            self.assertEqual(ch, [])
            self.assertNotIn("Cpuid1Data", k["Emulate"])

    def test_a_malformed_value_is_left_alone(self):
        cfg = {"Kernel": {"Emulate": {"Cpuid1Data": b"\0" * 20, "Cpuid1Mask": b"\0" * 16}}}
        self.assertFalse(policy.set_cpuid1_logical_per_package(cfg, 128))
        self.assertEqual(cfg["Kernel"]["Emulate"]["Cpuid1Data"], b"\0" * 20)

    def test_every_recipe_names_its_source_status_and_reason(self):
        for r in policy._machine_recipes():
            self.assertTrue(r["boards"] and r["cpus"] and r["source"] and r["why"])
            self.assertIn(r["status"], ("works", "opt-in"))


if __name__ == "__main__":
    unittest.main()
