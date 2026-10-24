"""The BIOS guide states the Resizable BAR setting only from a source that can see it: the stick's scan (it measures
the BAR) or an AMD card (Hardware Sniffer reads AMD's driver setting). On NVIDIA the Windows scan reads AMD's
registry value, which is never there, so it said "Disabled - turn it On" with the setting already on."""
import unittest

from p1401 import guide

CONFIG = {"NVRAM": {"Add": {guide.NVRAM_APPLE: {"boot-args": "-v nvfb=1 nvaccel=1"}}}, "Kernel": {"Quirks": {}}}


def rebar_line(gpu):
    report = {"CPU": {"Manufacturer": "Intel"}, "BIOS": {}, "Motherboard": {"Name": "Board"},
              "GPU": {"Card": dict({"Device Type": "Discrete GPU"}, **gpu)}}
    for st in guide.bios_settings(report, CONFIG):
        if "Resizable BAR" in st.name:
            return st
    return None


class RebarSource(unittest.TestCase):
    def test_nvidia_from_the_windows_scan_is_not_called_disabled(self):
        st = rebar_line({"Manufacturer": "NVIDIA", "Device ID": "10DE-2D05", "Resizable BAR": "Disabled"})
        self.assertIsNotNone(st)
        self.assertNotIn("Disabled", st.now)
        self.assertNotIn("turn it On", st.now)

    def test_a_measured_bar_is_still_reported(self):
        st = rebar_line({"Manufacturer": "NVIDIA", "Device ID": "10DE-2D05", "Resizable BAR": "Disabled",
                         "Resizable BAR source": "BAR size"})
        self.assertIn("Disabled", st.now)
        self.assertIn("turn it On", st.now)

    def test_an_amd_card_keeps_the_drivers_setting(self):
        st = rebar_line({"Manufacturer": "AMD", "Device ID": "1002-7480", "Resizable BAR": "Enabled"})
        self.assertIn("Enabled", st.now)


if __name__ == "__main__":
    unittest.main()
