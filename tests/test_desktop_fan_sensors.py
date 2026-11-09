"""Every desktop gets SMCSuperIO (fan speeds from the board's Super I/O chip); the engine alone gave it only to Intel CPUs,
so AMD desktops had no fan readings. Laptops keep their fans behind the embedded controller and are left as chosen."""
import copy
import types
import unittest

from p1401 import engine


class DesktopFanSensors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine._load_engine()
        from Scripts.kext_maestro import KextMaestro
        cls.maestro = KextMaestro

    def picked(self, platform):
        k = self.maestro()
        k.kexts = copy.deepcopy(k.kexts)
        for x in k.kexts:
            x.checked = x.required
        added = engine._desktop_fan_sensors(k, {"Motherboard": {"Platform": platform}}, "24.0.0")
        return added, {x.name for x in k.kexts if x.checked}

    def test_an_amd_desktop_gets_smcsuperio_and_its_virtualsmc(self):
        added, checked = self.picked("Desktop")
        self.assertTrue(added)
        self.assertLessEqual({"SMCSuperIO", "VirtualSMC"}, checked)

    def test_a_laptop_is_left_as_the_engine_chose(self):
        added, checked = self.picked("Laptop")
        self.assertFalse(added)
        self.assertNotIn("SMCSuperIO", checked)

    def test_the_wrapper_calls_it_after_the_engine_choice(self):
        src = open(engine.__file__, encoding="utf-8").read()
        i = src.index("def select_required_kexts(self, hardware_report, macos_version, needs_oclp, acpi_patches):")
        body = src[i:src.index("km.select_required_kexts = select_required_kexts", i)]
        self.assertLess(body.index("out = select("), body.index("_desktop_fan_sensors(self, hardware_report, macos_version)"))

    def test_negative_control_the_engine_alone_skips_an_amd_desktop(self):
        import pathlib
        src = (pathlib.Path(engine.__file__).resolve().parents[1] / "upstream/OpCore-Simplify/Scripts/kext_maestro.py").read_text(encoding="utf-8")
        self.assertIn('if "Intel" in hardware_report.get("CPU").get("Manufacturer"):\n            selected_kexts.extend(("SMCProcessor", "SMCSuperIO"))', src)


if __name__ == "__main__":
    unittest.main()
