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
    # 10-25: DevirtualiseMmio is forced off on laptops only (1401 #6, public laptop EFIs). Desktops did as well or better
    # with it on in the stick reports, and the Arrow Lake desktop that runs macOS boots with it on.
    def test_hybrid_laptops_turn_off_devirtualise_mmio(self):
        for name, code in (("12th Gen Intel(R) Core(TM) i7-12700H", "Alder Lake"), ("Intel(R) Core(TM) Ultra 9 275HX", "Arrow Lake"),
                           ("13th Gen Intel(R) Core(TM) i5-13650HX", "")):
            cfg, changes = build("Intel", name, code, platform="Laptop", devirt=True)
            self.assertFalse(devmmio(cfg), name)
            self.assertIn("hybrid-intel-devmmio", rules(changes), name)

    def test_hybrid_desktops_keep_the_engine_choice(self):
        for name, code in (("12th Gen Intel(R) Core(TM) i7-12700K", "Alder Lake"), ("14th Gen Intel(R) Core(TM) i9-14900K", "Raptor Lake")):
            for devirt in (True, False):
                cfg, changes = build("Intel", name, code, platform="Desktop", devirt=devirt)
                self.assertEqual(devmmio(cfg), devirt, name)
                self.assertNotIn("hybrid-intel-devmmio", rules(changes), name)

    def test_arrow_lake_desktop_gets_the_225f_setting(self):
        cfg, changes = build("Intel", "Intel(R) Core(TM) Ultra 5 225F", "Arrow Lake", platform="Desktop", devirt=False)
        self.assertTrue(devmmio(cfg))
        self.assertIn("arrow-lake-desktop-devmmio", rules(changes))
        cfg, changes = build("Intel", "Intel(R) Core(TM) Ultra 5 225F", "Arrow Lake", platform="Desktop", devirt=True)
        self.assertTrue(devmmio(cfg))
        self.assertNotIn("arrow-lake-desktop-devmmio", rules(changes))

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



class HybridIntelGuide(unittest.TestCase):
    """policy.py turns DisableIoMapper on for every hybrid Intel build, and the guide used to list VT-d only when it was
    off, so these PCs were never told the BIOS step that got them past EXITBS:START (1401 #10, #11, #53, #58)."""
    def settings(self, name, code, iomapper):
        from p1401 import guide  # noqa: PLC0415
        report = {"CPU": {"Manufacturer": "Intel", "Processor Name": name, "Codename": code}, "Motherboard": {"Name": "Board"}, "GPU": {}}
        return {st.name: st for st in guide.bios_settings(report, {"Kernel": {"Quirks": {"DisableIoMapper": iomapper}}})}

    def test_hybrid_intel_is_told_to_turn_vt_d_off_even_with_disableiomapper(self):
        st = self.settings("Intel(R) Core(TM) Ultra 7 265K", "Arrow Lake", True)
        self.assertIn("VT-d", st)
        self.assertTrue(st["VT-d"].required)
        self.assertIn("X2APIC", st["VT-d"].if_missing)

    def test_older_intel_with_disableiomapper_still_skips_vt_d(self):
        self.assertNotIn("VT-d", self.settings("Intel(R) Core(TM) i7-9700K", "Coffee Lake", True))
        self.assertIn("VT-d", self.settings("Intel(R) Core(TM) i7-9700K", "Coffee Lake", False))


if __name__ == "__main__":
    unittest.main()
