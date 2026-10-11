"""A laptop whose built-in panel runs on an Intel GPU macOS has no driver for keeps that GPU on (10-10: 86 of 184 scans)."""
import unittest

from p1401 import panel_guard


def capture(vendor="8086", dev="A7A0", internal=True, active=True):
    return {"device_map": {"graphics": {"status": "measured", "value": [
        {"adapter": "a0", "vendor_id": "10DE", "device_id": "28A0", "displays": []},
        {"adapter": "a1", "vendor_id": vendor, "device_id": dev, "displays": [
            {"internal_panel": internal, "active": active, "routing_source": "QueryDisplayConfig targetInfo.adapterId"}]}]}}}


def disabled(compat=(None, None), dev="8086-A7A0"):
    return {"GPU: Intel Iris Xe": {"Device Type": "Integrated GPU", "Device ID": dev, "Compatibility": compat}}


class IntelPanel(unittest.TestCase):
    def test_panel_on_an_unsupported_intel_gpu_keeps_it_on(self):
        self.assertEqual(panel_guard.intel_panel_keys(disabled(), capture()), ["GPU: Intel Iris Xe"])

    def test_negative_control_panel_on_nvidia_keeps_nothing(self):
        self.assertEqual(panel_guard.intel_panel_keys(disabled(), capture(vendor="10DE", dev="28A0")), [])

    def test_negative_control_an_intel_gpu_macos_drives_is_not_kept(self):
        self.assertEqual(panel_guard.intel_panel_keys(disabled(compat=("23.99.99", "17.0.0")), capture()), [])

    def test_negative_control_inactive_panel_keeps_nothing(self):
        self.assertEqual(panel_guard.intel_panel_keys(disabled(), capture(active=False)), [])


if __name__ == "__main__":
    unittest.main()
