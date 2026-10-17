"""A built config with WhateverGreen on gets gfxrst=4 next to the NullMoth boot-args (WhateverGreen's boot screen copy
can panic the Mac when the NVIDIA display opens); a gfxrst already set, or no WhateverGreen, is left alone."""
import unittest
from types import SimpleNamespace

from p1401 import nullmoth

B = "7C436110-AB2A-4BBB-A880-FE41995C9F82"


def result():
    gpu = {"Manufacturer": "NVIDIA", "Device Type": "Discrete GPU", "Device ID": "10DE-2520",
           "Compatibility": nullmoth.SEQUOIA}
    return SimpleNamespace(hardware={"Motherboard": {"Platform": "Desktop"}, "GPU": {"RTX 3060 Laptop": gpu}},
                           disabled_devices={})


def cfg(kexts, args="-v"):
    return {"Kernel": {"Add": kexts}, "NVRAM": {"Add": {B: {"boot-args": args}}}}


def weg(enabled=True):
    return {"BundlePath": "WhateverGreen.kext", "Enabled": enabled}


class WegGfxrst(unittest.TestCase):
    def run_apply(self, c):
        log = []
        nullmoth.apply(c, result(), lambda *a: log.append(a[0]))
        return c["NVRAM"]["Add"][B]["boot-args"].split(), log

    def test_whatevergreen_on_gets_gfxrst4(self):
        args, log = self.run_apply(cfg([weg()]))
        self.assertIn("gfxrst=4", args)
        self.assertIn("nullmoth-weg-gfxrst", log)

    def test_negative_control_whatevergreen_off(self):
        args, log = self.run_apply(cfg([weg(enabled=False)]))
        self.assertNotIn("gfxrst=4", args)
        self.assertNotIn("nullmoth-weg-gfxrst", log)

    def test_no_kernel_section(self):
        c = {"NVRAM": {"Add": {B: {"boot-args": ""}}}}
        args, log = self.run_apply(c)
        self.assertNotIn("gfxrst=4", args)

    def test_a_set_gfxrst_is_kept(self):
        args, log = self.run_apply(cfg([weg()], "gfxrst=1"))
        self.assertIn("gfxrst=1", args)
        self.assertNotIn("gfxrst=4", args)
        self.assertNotIn("nullmoth-weg-gfxrst", log)

    def test_second_pass_changes_nothing(self):
        c = cfg([weg()])
        self.run_apply(c)
        args, log = self.run_apply(c)
        self.assertEqual(args.count("gfxrst=4"), 1)
        self.assertEqual(log, [])


if __name__ == "__main__":
    unittest.main()
