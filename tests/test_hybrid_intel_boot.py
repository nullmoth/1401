"""Hybrid-core Intel (Core Ultra and 12th/13th/14th-gen Core) stops at the kernel hand-off (EXITBS:START) with a
type-14 page fault. The build turns DevirtualiseMmio off (boot.efi faults on devirtualised MMIO), keeps the
CpuTopologyRebuild core re-map on laptops whose firmware hides the Hyper-Threading / E-core switch, and tells the
user which BIOS setting to change. Earlier Intel and AMD are left alone."""
import os
import plistlib
import tempfile
import unittest

from p1401 import engine, policy


def build(manufacturer, name, codename="", platform="", devirt=None, with_ctr=False):
    t = tempfile.mkdtemp()
    path = os.path.join(t, "config.plist")
    kernel_add = []
    if with_ctr:
        kernel_add.append({"BundlePath": "CpuTopologyRebuild.kext", "Enabled": True})
    booter_quirks = {}
    if devirt is not None:
        booter_quirks["DevirtualiseMmio"] = devirt
    cfg = {"NVRAM": {"Add": {}, "Delete": {}}, "Kernel": {"Add": kernel_add, "Patch": [], "Quirks": {}},
           "Booter": {"Quirks": booter_quirks, "MmioWhitelist": []}, "Misc": {}, "ACPI": {"Add": [], "Delete": []},
           "UEFI": {"Drivers": [], "Quirks": {}}, "PlatformInfo": {"Generic": {}}}
    with open(path, "wb") as f:
        plistlib.dump(cfg, f)
    res = engine.BuildResult(ok=True, out_dir=t, macos_version="24.6.0", hardware={
        "Motherboard": {"Name": "Board", "Chipset": "", "Platform": platform},
        "CPU": {"Manufacturer": manufacturer, "Processor Name": name, "Codename": codename}, "GPU": {}})
    changes = policy.apply(path, res, engine.Policy())
    with open(path, "rb") as f:
        return plistlib.load(f), changes


def devmmio(cfg):
    return cfg["Booter"]["Quirks"].get("DevirtualiseMmio")


def ctr_enabled(cfg):
    return any(k.get("BundlePath") == "CpuTopologyRebuild.kext" and k.get("Enabled") for k in cfg["Kernel"]["Add"])


def rules(changes):
    return {c["rule"] for c in changes}


class HybridIntelBoot(unittest.TestCase):
    def test_alder_lake_turns_off_devirtualise_mmio(self):
        cfg, changes = build("Intel", "12th Gen Intel(R) Core(TM) i7-12700H", "Alder Lake", devirt=True)
        self.assertFalse(devmmio(cfg))
        self.assertIn("hybrid-intel-devmmio", rules(changes))

    def test_raptor_lake_turns_off_devirtualise_mmio(self):
        cfg, _ = build("Intel", "14th Gen Intel(R) Core(TM) i9-14900K", "Raptor Lake", devirt=True)
        self.assertFalse(devmmio(cfg))

    def test_core_ultra_turns_off_devirtualise_mmio(self):
        cfg, _ = build("Intel", "Intel(R) Core(TM) Ultra 9 275HX", "Arrow Lake", devirt=True)
        self.assertFalse(devmmio(cfg))

    def test_hybrid_detected_by_generation_when_codename_is_missing(self):
        cfg, _ = build("Intel", "13th Gen Intel(R) Core(TM) i5-13650HX", devirt=True)
        self.assertFalse(devmmio(cfg))

    def test_every_hybrid_build_names_the_bios_switch(self):
        for name, code in (("12th Gen Intel(R) Core(TM) i5-12400F", "Alder Lake"),
                           ("Intel(R) Core(TM) Ultra 5 245KF", "Arrow Lake")):
            _, changes = build("Intel", name, code)
            note = next((c["after"] for c in changes if c["rule"] == "hybrid-intel-bios"), "")
            self.assertIn("Hyper-Threading", note)

    def test_laptop_bios_note_points_to_the_software_remap(self):
        _, changes = build("Intel", "Intel(R) Core(TM) Ultra 9 275HX", "Arrow Lake", platform="Laptop", with_ctr=True)
        note = next(c["after"] for c in changes if c["rule"] == "hybrid-intel-bios")
        self.assertIn("CpuTopologyRebuild", note)

    def test_arrow_lake_laptop_keeps_cpu_topology_rebuild(self):
        cfg, _ = build("Intel", "Intel(R) Core(TM) Ultra 9 275HX", "Arrow Lake", platform="Laptop", with_ctr=True)
        self.assertTrue(ctr_enabled(cfg))

    def test_arrow_lake_desktop_still_removes_cpu_topology_rebuild(self):
        cfg, changes = build("Intel", "Intel(R) Core(TM) Ultra 7 265KF", "Arrow Lake", platform="Desktop", with_ctr=True)
        self.assertFalse(ctr_enabled(cfg))
        self.assertIn("arrow-lake-ctr", rules(changes))

    def test_older_intel_is_left_alone(self):
        cfg, changes = build("Intel", "Intel(R) Core(TM) i7-9700K", "Coffee Lake", devirt=True, with_ctr=True)
        self.assertTrue(devmmio(cfg))
        self.assertTrue(ctr_enabled(cfg))
        self.assertNotIn("hybrid-intel-devmmio", rules(changes))
        self.assertNotIn("hybrid-intel-bios", rules(changes))

    def test_amd_is_left_alone(self):
        cfg, changes = build("AMD", "AMD Ryzen 7 7800X3D 8-Core Processor", "Raphael")
        self.assertNotIn("hybrid-intel-bios", rules(changes))


if __name__ == "__main__":
    unittest.main()
