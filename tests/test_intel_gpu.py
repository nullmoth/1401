"""Intel Xe GPUs get a build notice naming their path: basic display, plus the Mac app's opt-in WhateverXe for the IDs it
covers. A Tiger Lake laptop (1135G7, Iris Xe) built with no word on what its graphics would do; an Intel GPU macOS
already drives must get nothing new. No network."""
import os
import re
import unittest

from p1401 import engine, intel_gpu

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeChecker:
    def __init__(self, gpus, monitors=None):
        self.hardware_report = {"GPU": gpus, "Monitor": monitors or {}}

    def check_gpu_compatibility(self):
        pass

    def _widest_compatibility(self, comps):
        return None

    def _restrict_native_compatibility(self, widest):
        pass


class FakeHeadless:
    def __init__(self):
        self.policy, self.notices = engine.Policy(), []


def run(gpus):
    c, h = FakeChecker(gpus), FakeHeadless()
    engine._nullmoth_gpu_pass(c, h)
    c.check_gpu_compatibility()
    return h.notices


def intel(did, device_type="Integrated GPU"):
    return {"Manufacturer": "Intel", "Device ID": "8086-" + did, "Device Type": device_type}


def graphics(notes):
    return [n for n in notes if n.startswith("Graphics:")]


class Classify(unittest.TestCase):
    def test_a_tiger_lake_iris_xe_the_mac_app_covers_is_whateverxe(self):
        self.assertEqual(intel_gpu.classify(intel("9A49")), ("Tiger Lake (Xe-LP)", intel_gpu.WHATEVERXE))

    def test_a_meteor_lake_gpu_has_no_driver_to_offer(self):
        self.assertEqual(intel_gpu.classify(intel("7D55"))[1], intel_gpu.NO_DRIVER)

    def test_rocket_lake_is_xe_but_not_one_whateverxe_covers(self):
        self.assertEqual(intel_gpu.classify(intel("4C8A")), ("Rocket Lake (Xe-LP)", intel_gpu.NO_DRIVER))

    def test_negative_an_intel_gpu_macos_drives_is_not_classified(self):
        for did in ("3E92", "9BC5", "8A52", "5917"):   # Coffee Lake UHD 630, Comet Lake, Ice Lake, Kaby Lake
            self.assertIsNone(intel_gpu.classify(intel(did)), did)

    def test_negative_an_amd_or_nvidia_gpu_is_not_classified(self):
        self.assertIsNone(intel_gpu.classify({"Device ID": "1002-9A49"}))
        self.assertIsNone(intel_gpu.classify({"Device ID": "10DE-2684"}))
        self.assertIsNone(intel_gpu.classify({}))

    def test_every_whateverxe_id_has_a_family(self):
        self.assertEqual([d for d in intel_gpu.WHATEVERXE_IDS if intel_gpu.classify(intel(d)) is None], [])


class SameListAsTheMacApp(unittest.TestCase):
    """The build notice promises what the Mac app offers, so its ID list is the Mac app's, exactly."""

    def ids_in(self, rel, pattern):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            m = re.search(pattern, fh.read(), re.S)
        self.assertIsNotNone(m, rel)
        return re.findall(r"\b[0-9A-F]{4}\b", m.group(1))

    def test_the_swift_list_is_the_same(self):
        ids = self.ids_in("mac/Sources/main.swift", r"static let xeIds: Set<String> = \[(.*?)\]")
        self.assertEqual(sorted(ids), sorted(intel_gpu.WHATEVERXE_IDS))

    def test_the_setup_script_list_is_the_same(self):
        ids = self.ids_in("mac/Resources/nullmoth-setup.sh", r'case " (9A40 [0-9A-F ]*) " in')
        self.assertEqual(sorted(ids), sorted(intel_gpu.WHATEVERXE_IDS))


class BuildNotice(unittest.TestCase):
    def test_an_iris_xe_only_laptop_is_told_about_basic_display_and_the_opt_in(self):
        notes = graphics(run({"Intel(R) Iris(R) Xe Graphics": intel("9A49")}))
        self.assertTrue(any("Iris(R) Xe" in n and "WhateverXe" in n and "opt-in" in n and "basic display" in n
                            for n in notes), notes)
        self.assertFalse(any("NullMoth NVIDIA driver" in n for n in notes), notes)

    def test_the_specific_notice_replaces_the_generic_basic_display_one(self):
        notes = run({"Intel(R) Iris(R) Xe Graphics": intel("9A49")})
        self.assertFalse(any(n.startswith("Basic display:") for n in notes), notes)

    def test_a_meteor_lake_laptop_is_not_promised_whateverxe(self):
        notes = graphics(run({"Intel(R) Arc(TM) Graphics": intel("7D55")}))
        self.assertTrue(any("Meteor Lake" in n and "no driver 1401 can offer" in n for n in notes), notes)
        self.assertFalse(any("WhateverXe" in n for n in notes), notes)

    def test_with_an_nvidia_card_the_untested_pairing_is_said(self):
        notes = graphics(run({"Intel(R) Iris(R) Xe Graphics": intel("A7A0"),
                              "NVIDIA GeForce RTX 4060 Laptop GPU": {"Manufacturer": "NVIDIA", "Device Type": "Discrete GPU",
                                                                    "Device ID": "10DE-28E0"}}))
        self.assertTrue(any("WhateverXe" in n and "not been tested together with the NullMoth NVIDIA driver" in n
                            for n in notes), notes)

    def test_negative_a_uhd_630_desktop_gets_no_new_graphics_notice(self):
        self.assertEqual(graphics(run({"Intel(R) UHD Graphics 630": intel("3E92")})), [])


if __name__ == "__main__":
    unittest.main()
