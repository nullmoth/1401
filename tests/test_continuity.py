"""Continuity (AirDrop, Handoff, Universal Control, Sidecar, AirPlay to Mac, Continuity Camera, iPhone Mirroring,
Instant Hotspot) rides on AWDL, which only an Apple-compatible Wi-Fi driver raises. The build says what the chosen Wi-Fi
driver gives, and every Mac model 1401 picks passes Apple's model checks without an unlock kext."""
import unittest

from p1401 import continuity as c


def status(rows):
    return {n: s for n, s, _ in rows}


class Expectations(unittest.TestCase):
    def test_apples_own_wifi_driver_gives_every_feature_and_needs_no_notice(self):
        rows = c.expectations(["Lilu", "AirportBrcmFixup"], "MacPro7,1")
        self.assertEqual({s for _n, s, _w in rows}, {"yes"})
        self.assertIsNone(c.notice(["AirportBrcmFixup"], "MacPro7,1"))

    def test_a_third_party_wifi_driver_loses_the_wifi_features_but_keeps_the_cable_ones(self):
        st = status(c.expectations(["AirportItlwm"], "iMac20,1"))
        self.assertEqual(st["AirDrop"], "no")
        self.assertEqual(st["Handoff and Universal Clipboard"], "no")
        for wired in ("Universal Control", "Sidecar", "Continuity Camera"):
            self.assertEqual(st[wired], "wired-only")

    def test_the_notice_names_what_is_lost_and_what_still_works_with_a_cable(self):
        text = c.notice(["itlwm"], "MacBookPro16,2")
        self.assertIn("AirDrop", text)
        self.assertIn("work only with a cable", text)
        self.assertIn("Sidecar", text.split("work only with a cable")[0])

    def test_the_rtw89_driver_is_experimental_not_promised(self):
        st = status(c.expectations(["AirportRTW89"], "MacPro7,1"))
        self.assertEqual(set(st.values()), {"experimental"})
        self.assertIn("experimental", c.notice(["AirportRTW89"], "MacPro7,1"))

    def test_no_known_wifi_driver_says_nothing(self):
        self.assertEqual(c.expectations(["Lilu", "VirtualSMC"], "MacPro7,1"), [])
        self.assertIsNone(c.notice([], "MacPro7,1"))


class ModelGate(unittest.TestCase):
    def test_every_model_1401_picks_is_newer_than_the_ones_apple_excludes(self):
        for model in ("MacPro7,1", "iMac20,1", "iMac20,2", "iMacPro1,1", "MacBookPro16,2", "MacBookPro16,1", "Macmini8,1"):
            self.assertFalse(c.model_needs_unlock(model), model)

    def test_an_old_model_in_a_hand_made_efi_is_flagged(self):
        for model in ("MacPro6,1", "iMac14,2", "MacBookPro11,4", "Macmini7,1"):
            self.assertTrue(c.model_needs_unlock(model), model)
        st = status(c.expectations(["AirportBrcmFixup"], "iMac14,2"))
        self.assertEqual(st["Sidecar"], "no")
        self.assertEqual(st["AirDrop"], "yes")

    def test_text_that_is_not_a_model_is_not_flagged(self):
        self.assertFalse(c.model_needs_unlock(""))
        self.assertFalse(c.model_needs_unlock("Something"))


if __name__ == "__main__":
    unittest.main()
