"""The user's macOS pick is answered once; a menu that does not offer it stops the build with the cap, not a loop.

A Haswell PC with a GTX 1070 (two uploads from one user): OpenCore-Simplify offered versions 17-24, 1401 answered 25
(macOS 26 Tahoe, the user's pick) and the engine re-asked until "EngineLoop: ... our answer was rejected". The app hands
the picked version to the guide and the stick writer too, so the build does not quietly switch to another one; it names
the highest version this PC gets and the version to pick."""
import unittest

from p1401 import engine

PROMPT = "Please enter the macOS version you want to use (default: macOS High Sierra 10.13):"
MENU_TO_15 = ("== Select macOS Version\nAvailable macOS versions:\n   17. macOS High Sierra 10.13\n   18. macOS Mojave 10.14\n"
              "   19. macOS Catalina 10.15\n   20. macOS Big Sur 11 (Requires OpenCore Legacy Patcher)\n"
              "   24. macOS Sequoia 15 (Requires OpenCore Legacy Patcher)\nNote:\nQ. Quit")
MENU_15_26 = "Available macOS versions:\n   24. macOS Sequoia 15\n   25. macOS Tahoe 26\nNote:\nQ. Quit"
MENU_26_ONLY = "Available macOS versions:\n   25. macOS Tahoe 26\nNote:\nQ. Quit"


def policy(macos):
    return engine.Policy(macos=macos)


class PickNotOnTheMenu(unittest.TestCase):
    def test_a_pick_above_the_menus_cap_stops_and_names_the_cap(self):
        with self.assertRaises(engine.MacosNotOffered) as caught:
            engine._macos_answer(PROMPT, MENU_TO_15, policy("25"))
        text = str(caught.exception)
        self.assertIn("capped at macOS Sequoia 15", text)
        self.assertIn("macOS 26 Tahoe is not among them", text)
        self.assertIn("Pick macOS 15 Sequoia in 1401", text)

    def test_the_stop_is_a_runtime_error_the_build_reports_not_an_engine_loop(self):
        self.assertTrue(issubclass(engine.MacosNotOffered, RuntimeError))
        self.assertFalse(issubclass(engine.MacosNotOffered, engine.EngineLoop))

    def test_a_pick_on_the_menu_is_answered_as_before(self):
        self.assertEqual(engine._macos_answer(PROMPT, MENU_15_26, policy("25")), "25")
        self.assertEqual(engine._macos_answer(PROMPT, MENU_15_26, policy("24")), "24")
        self.assertEqual(engine._macos_answer(PROMPT, MENU_TO_15, policy("24")), "24")

    def test_a_pick_below_the_menus_floor_names_the_floor(self):
        with self.assertRaises(engine.MacosNotOffered) as caught:
            engine._macos_answer(PROMPT, MENU_26_ONLY, policy("24"))
        text = str(caught.exception)
        self.assertIn("needs at least macOS Tahoe 26", text)
        self.assertIn("Pick macOS 26 Tahoe or newer", text)

    def test_a_full_darwin_version_pick_is_passed_through_untouched(self):
        # "--macos 24.4.0" is the CLI's form; the engine takes Darwin versions itself and the menu lists majors only.
        self.assertEqual(engine._macos_answer(PROMPT, MENU_TO_15, policy("24.4.0")), "24.4.0")

    def test_a_prompt_with_no_menu_in_context_answers_the_pick(self):
        self.assertEqual(engine._macos_answer(PROMPT, "Press Enter to continue...", policy("25")), "25")

    def test_no_pick_keeps_the_engines_default_logic(self):
        self.assertEqual(engine._macos_answer(PROMPT, MENU_TO_15, engine.Policy()), "")


if __name__ == "__main__":
    unittest.main()
