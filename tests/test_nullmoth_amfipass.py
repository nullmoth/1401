"""An EFI built for the NullMoth driver carries AMFIPass and Lilu: the driver's Mac setup stops without them (10-10)."""
import copy
import types
import unittest

from p1401 import engine, nullmoth


class NullmothAmfipass(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine._load_engine()
        from Scripts.kext_maestro import KextMaestro
        from Scripts.datasets import kext_data
        cls.maestro, cls.data = KextMaestro, kext_data

    def run_pass(self, gpu):
        o = types.SimpleNamespace(k=self.maestro())
        o.k.kexts = copy.deepcopy(o.k.kexts)          # the engine's kext list is module-level; keep each run apart
        for k in o.k.kexts:
            k.checked = k.required
        h = types.SimpleNamespace(notices=[])
        picked = engine._nullmoth_amfipass(o, {"GPU": {"card": gpu}}, "24.0.0", h)
        checked = {k.name for k in o.k.kexts if k.checked}
        return picked, checked

    def test_a_supported_nvidia_card_gets_amfipass_and_lilu(self):
        picked, checked = self.run_pass({"Manufacturer": "NVIDIA", "Device ID": "10DE-2D04",
                                         "Device Type": "Discrete GPU", "Compatibility": nullmoth.SEQUOIA})
        self.assertTrue(picked)
        self.assertLessEqual({"AMFIPass", "Lilu"}, checked)

    def test_negative_control_no_nvidia_card_adds_nothing(self):
        picked, checked = self.run_pass({"Manufacturer": "AMD", "Device ID": "1002-73BF",
                                         "Device Type": "Discrete GPU", "Compatibility": ("15.99.99", "10.13.0")})
        self.assertFalse(picked)
        self.assertNotIn("AMFIPass", checked)


if __name__ == "__main__":
    unittest.main()
