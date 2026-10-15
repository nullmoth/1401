"""The engine's GPU pass emits a per-AMD-GPU build notice so the user sees, before building, what each AMD card gets.
Users brought RX 7900 XTX and RX 9070 cards and got only the generic "no supported GPU" path with no word on what to
expect; a native RX 6800 got no confirmation it was fully supported. The notice names the card and its macOS path."""
import unittest

from p1401 import engine


class FakeChecker:
    def __init__(self, gpus):
        self.hardware_report = {"GPU": gpus, "Monitor": {}}

    def check_gpu_compatibility(self):
        pass  # the upstream check; a no-op here, so nothing exits

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


def amd(did, device_type="Discrete GPU"):
    return {"Manufacturer": "AMD", "Device ID": "1002-" + did, "Device Type": device_type}


class GpuPassNotice(unittest.TestCase):
    def test_rdna3_card_gets_its_notice(self):
        notes = run({"AMD Radeon RX 7900 XTX": amd("744C")})
        self.assertTrue(any(n.startswith("Graphics:") and "RX 7900 XTX" in n and "opt-in NullMoth test driver" in n
                            for n in notes), notes)

    def test_rdna4_card_names_the_community_projects(self):
        notes = run({"AMD Radeon RX 9070 XT": amd("7550")})
        self.assertTrue(any("RX 9070 XT" in n and "community" in n and "Cobalt64" in n for n in notes), notes)

    def test_native_card_is_confirmed_supported(self):
        notes = run({"AMD Radeon RX 6800": amd("73BF")})
        self.assertTrue(any("RX 6800" in n and "full acceleration after" in n for n in notes), notes)

    def test_negative_control_an_nvidia_only_pc_gets_no_graphics_notice(self):
        notes = run({"NVIDIA GeForce RTX 4090": {"Manufacturer": "NVIDIA", "Device Type": "Discrete GPU",
                                                 "Device ID": "10DE-2684"}})
        self.assertFalse(any(n.startswith("Graphics:") for n in notes), notes)


if __name__ == "__main__":
    unittest.main()
