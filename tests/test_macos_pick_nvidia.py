"""A PC whose NVIDIA card runs on the NullMoth driver is built for macOS 15, whatever the engine suggests.

On AMD Ryzen laptops the engine suggests "macOS Ventura 13 or older" and makes Ventura the default. It is on the menu,
so it was taken as is: 15 NVIDIA builds installed Ventura or Sonoma, where the driver does not load."""
import unittest

from p1401 import engine, nullmoth

Q_VENTURA = "Please enter the macOS version you want to use (default: macOS Ventura 13):"
MENU_ALL = ("Available macOS versions:\n   19. macOS Catalina 10.15\n   20. macOS Big Sur 11\n   21. macOS Monterey 12\n"
            "   22. macOS Ventura 13\n   23. macOS Sonoma 14\n   24. macOS Sequoia 15\n   25. macOS Tahoe 26\nNote:\nQ. Quit")
MENU_NO_15 = "Available macOS versions:\n   22. macOS Ventura 13\n   23. macOS Sonoma 14\nQ. Quit"


def policy(**prefer):
    p = engine.Policy()
    p.prefer.update(prefer)
    return p


class FakeChecker:
    def __init__(self, gpus):
        self.hardware_report = {"GPU": gpus, "Monitor": {}}

    def check_gpu_compatibility(self):
        pass

    def _widest_compatibility(self, comps):
        return None

    def _restrict_native_compatibility(self, widest):
        pass


class FakeHeadless:
    def __init__(self):
        self.policy, self.notices = engine.Policy(), []


RTX = {"Manufacturer": "NVIDIA", "Device Type": "Discrete GPU", "Device ID": "10DE-2D05", "Codename": "Unknown"}
AMD_IGPU = {"Manufacturer": "AMD", "Device Type": "Integrated GPU", "Device ID": "1002-1638",
            "Compatibility": ("24.99.99", "19.0.0")}


class MacosPick(unittest.TestCase):
    def test_a_ventura_default_on_the_menu_answers_sequoia_for_a_driver_card(self):
        self.assertEqual(engine._macos_answer(Q_VENTURA, MENU_ALL, policy(macOS="24")), "24")

    def test_negative_control_without_a_driver_card_the_engines_default_stays(self):
        self.assertEqual(engine._macos_answer(Q_VENTURA, MENU_ALL, policy()), "")

    def test_the_users_choice_wins(self):
        p = policy(macOS="24")
        p.macos = "25"
        self.assertEqual(engine._macos_answer(Q_VENTURA, MENU_ALL, p), "25")

    def test_negative_control_sequoia_not_on_the_menu_falls_back_to_the_old_rule(self):
        self.assertEqual(engine._macos_answer(Q_VENTURA, MENU_NO_15, policy(macOS="24")), "")

    def test_the_gpu_pass_asks_for_sequoia_when_it_marks_a_card(self):
        c, h = FakeChecker({"RTX 5060": dict(RTX), "AMD Radeon(TM) Graphics": dict(AMD_IGPU)}), FakeHeadless()
        engine._nullmoth_gpu_pass(c, h)
        c.check_gpu_compatibility()
        self.assertEqual(h.policy.prefer.get("macOS"), "24")

    def test_a_marked_card_keeps_tahoe_on_the_menu(self):
        # NM-RRSB2644: an RTX 4060 PC that picked macOS 26 got a menu of "24. macOS Sequoia 15" only and failed
        lo, hi = (int(x.split(".")[0]) for x in (nullmoth.SEQUOIA[1], nullmoth.SEQUOIA[0]))
        self.assertEqual((lo, hi), (24, 25))

    def test_the_gpu_pass_asks_for_tahoe_when_the_user_picked_it(self):
        c, h = FakeChecker({"RTX 5060": dict(RTX)}), FakeHeadless()
        h.policy.macos = "25"
        engine._nullmoth_gpu_pass(c, h)
        c.check_gpu_compatibility()
        self.assertEqual(h.policy.prefer.get("macOS"), "25")
        self.assertTrue(any("macOS 26 Tahoe" in n for n in h.notices), h.notices)

    def test_negative_control_no_driver_card_sets_no_version(self):
        c, h = FakeChecker({"AMD Radeon(TM) Graphics": dict(AMD_IGPU)}), FakeHeadless()
        engine._nullmoth_gpu_pass(c, h)
        c.check_gpu_compatibility()
        self.assertNotIn("macOS", h.policy.prefer)


if __name__ == "__main__":
    unittest.main()
