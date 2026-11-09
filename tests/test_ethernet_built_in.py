"""Apple ID sign-in counts a Mac's accounts by en0; macOS makes only a built-in PCI Ethernet controller en0, so every PCI
Ethernet controller in the scan is marked built-in (1401 #338, #90)."""
import os
import plistlib
import tempfile
import unittest

from p1401 import engine, policy

I225 = "8086-15F3"          # Intel I225-V, in the engine's Ethernet table
WIFI = "8086-2725"          # Intel AX210, a Wi-Fi card
PATH_A = "PciRoot(0x0)/Pci(0x1C,0x2)/Pci(0x0,0x0)"
PATH_B = "PciRoot(0x0)/Pci(0x1C,0x3)/Pci(0x0,0x0)"


def build(network, add=None):
    t = tempfile.mkdtemp()
    path = os.path.join(t, "config.plist")
    cfg = {"NVRAM": {"Add": {}, "Delete": {}}, "Kernel": {"Add": [], "Patch": [], "Quirks": {}},
           "Booter": {"Quirks": {}, "MmioWhitelist": []}, "Misc": {}, "ACPI": {"Add": []},
           "UEFI": {"Drivers": [], "Quirks": {}}, "PlatformInfo": {"Generic": {}}, "DeviceProperties": {"Add": add or {}}}
    with open(path, "wb") as f:
        plistlib.dump(cfg, f)
    res = engine.BuildResult(ok=True, out_dir=t, macos_version="24.6.0", hardware={
        "Motherboard": {"Name": "B", "Chipset": ""}, "CPU": {"Manufacturer": "Intel", "Processor Name": "i5", "Codename": ""},
        "GPU": {}, "Network": network})
    changes = policy.apply(path, res, engine.Policy())
    with open(path, "rb") as f:
        return plistlib.load(f)["DeviceProperties"]["Add"], [c["rule"] for c in changes]


class EthernetBuiltIn(unittest.TestCase):
    def test_a_pci_ethernet_controller_with_an_acpi_path_is_marked_built_in(self):
        add, rules = build({"Intel I225-V": {"Device ID": I225, "PCI Path": PATH_A, "ACPI Path": "\\_SB.PC00.RP05", "Bus Type": "PCI"}})
        self.assertEqual(add, {PATH_A: {"built-in": b"\x01"}})
        self.assertIn("ethernet-built-in", rules)

    def test_wifi_cards_and_usb_adapters_are_not_marked(self):
        add, rules = build({"AX210": {"Device ID": WIFI, "PCI Path": PATH_B, "Bus Type": "PCI"},
                            "USB Ethernet": {"Device ID": I225, "PCI Path": PATH_A, "Bus Type": "USB"}})
        self.assertEqual(add, {})
        self.assertNotIn("ethernet-built-in", rules)

    def test_other_properties_on_the_same_path_are_kept_and_a_marked_one_is_not_reported_again(self):
        add, rules = build({"Intel I225-V": {"Device ID": I225, "PCI Path": PATH_A, "Bus Type": "PCI"}},
                           add={PATH_A: {"built-in": b"\x01", "device-id": b"\x01\x02"}})
        self.assertEqual(add[PATH_A], {"built-in": b"\x01", "device-id": b"\x01\x02"})
        self.assertNotIn("ethernet-built-in", rules)
        add, _ = build({"Intel I225-V": {"Device ID": I225, "PCI Path": PATH_A, "Bus Type": "PCI"}},
                       add={PATH_A: {"device-id": b"\x01\x02"}})
        self.assertEqual(add[PATH_A], {"device-id": b"\x01\x02", "built-in": b"\x01"})

    def test_a_machine_with_no_network_scan_is_untouched(self):
        add, rules = build({})
        self.assertEqual((add, "ethernet-built-in" in rules), ({}, False))


if __name__ == "__main__":
    unittest.main()
