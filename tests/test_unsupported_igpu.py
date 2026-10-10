"""An Intel iGPU macOS has no driver for must not stop the build (1.10.0 build log, 10-10, Iris Xe laptop:
"KeyError: 'PciRoot(0x0)/Pci(0x2,0x0)'"). Runs the engine's real device-properties pass. No network."""
import copy
import os
import sys
import unittest

from p1401 import engine

UP = engine.UPSTREAM


def report():
    return {"GPU": {"Intel(R) Iris(R) Xe Graphics": {"Device Type": "Integrated GPU", "Manufacturer": "Intel",
                                                       "Device ID": "8086-9A49", "PCI Path": "PciRoot(0x0)/Pci(0x2,0x0)",
                                                       "Codename": "Tiger Lake"}},
            "Motherboard": {"Name": "Test Laptop", "Platform": "Laptop"}, "Monitor": {}}


class UnsupportedIgpu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if UP not in sys.path:
            sys.path.insert(0, UP)
        from Scripts import config_prodigy  # noqa: PLC0415
        from Scripts.datasets import kext_data  # noqa: PLC0415
        cls.cp, cls.kd = config_prodigy, kext_data

    def kexts(self):
        ks = copy.deepcopy(self.kd.kexts)
        for k in ks:
            k.checked = k.name in ("Lilu", "WhateverGreen")
        return ks

    def call(self, fn):
        prodigy = self.cp.ConfigProdigy.__new__(self.cp.ConfigProdigy)
        return fn(prodigy, report(), {}, "24.0.0", self.kexts())

    def test_negative_control_the_engine_alone_raises_the_users_keyerror(self):
        orig = getattr(self.cp.ConfigProdigy, "_1401_orig", None) or self.cp.ConfigProdigy.deviceproperties
        engine._unsupported_igpu_fix()
        raw = self.cp.ConfigProdigy.deviceproperties.__closure__  # the wrapper keeps the engine's function
        engine_fn = next(c.cell_contents for c in raw if callable(c.cell_contents) and c.cell_contents.__name__ == "deviceproperties")
        with self.assertRaises(KeyError):
            self.call(engine_fn)
        self.assertTrue(callable(orig))

    def test_with_the_fix_the_build_goes_on_without_igpu_properties(self):
        engine._unsupported_igpu_fix()
        out = self.call(self.cp.ConfigProdigy.deviceproperties)
        self.assertNotIn("PciRoot(0x0)/Pci(0x2,0x0)", out or {})


if __name__ == "__main__":
    unittest.main()
