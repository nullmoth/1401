"""The Huawei MateBook X Pro 2023 profile: the real scan's devices get their own, honest notes.

Fixture data is the structure of the scan this project made on the machine (MRGFG-XX, i7-1360P, A7A0, AX211,
GXTP786 touchpad, GXTP738X touchscreen, TBU405Pro). The profile must never call the touchscreen a touchpad and must
not claim a boot that was not observed.
"""
import unittest

from p1401 import huawei

REPORT = {
    "Motherboard": {"Name": "HUAWEI MRGFG-XX-PCB", "Chipset": "Raptor Lake-P", "Platform": "Laptop"},
    "CPU": {"Manufacturer": "Intel", "Processor Name": "13th Gen Intel(R) Core(TM) i7-1360P", "Codename": "Raptor Lake-P"},
    "GPU": {"Intel(R) Iris(R) Xe Graphics": {"Manufacturer": "Intel", "Device ID": "8086-A7A0",
                                             "Device Type": "Integrated GPU"}},
    "Network": {"Intel(R) Wi-Fi 6E AX211 160MHz": {"Bus Type": "PCI", "Device ID": "8086-51F1"},
                "Realtek USB GbE Family Controller": {"Bus Type": "USB", "Device ID": "0BDA-8153"}},
    "Input": {"符合 HID 标准的触摸板": {"Bus Type": "ACPI", "Device": "GXTP786", "Device Type": "I2C HID 设备"},
              "符合 HID 标准的触摸屏": {"Bus Type": "ACPI", "Device": "GXTP738X", "Device Type": "I2C HID 设备"},
              "PS/2 标准键盘": {"Bus Type": "ACPI", "Device": "MSFT0001", "Device Type": "PS/2"}},
    "Storage Drives": {"Disk 2": {"Model": "TBU405Pro", "Bus Type": "USB", "Size": 1024209543168},
                       "Disk 0": {"Model": "WD PC SN740 SDDPNQE-2T00-1027", "Bus Type": "NVMe", "Size": 2048408248320,
                                  "System": True}},
}
KEXTS = ["WhateverXe", "itlwm", "VoodooI2C", "VoodooI2CHID", "VoodooPS2Controller", "UTBDefault"]


class Profile(unittest.TestCase):
    def test_board_and_cpu_must_both_match(self):
        self.assertTrue(huawei.matches(REPORT))
        other = dict(REPORT, Motherboard={"Name": "LENOVO 21HQ"})
        self.assertFalse(huawei.matches(other))
        other = dict(REPORT, CPU={"Processor Name": "13th Gen Intel(R) Core(TM) i5-1340P"})
        self.assertFalse(huawei.matches(other))
        self.assertEqual(huawei.notes(other, KEXTS), [])

    def test_a7a0_and_whateverxe_are_named(self):
        notes = huawei.notes(REPORT, KEXTS, {"offline_recommended": True})
        self.assertTrue(any("A7A0" in n and "WhateverXe" in n for n in notes), notes)
        self.assertTrue(any("unverified" in n or "opt-in" in n for n in notes), notes)

    def test_ax211_is_named_as_itlwm_and_not_installer_wifi(self):
        notes = huawei.notes(REPORT, KEXTS, {"offline_recommended": True})
        ax = [n for n in notes if "AX211" in n]
        self.assertTrue(ax, notes)
        self.assertIn("itlwm", ax[0])
        self.assertIn("HeliPort", ax[0])
        self.assertIn("offline", ax[0])

    def test_the_touchpad_and_touchscreen_are_never_confused(self):
        notes = huawei.notes(REPORT, KEXTS, {"offline_recommended": False})
        pad = [n for n in notes if "GXTP786" in n]
        screen = [n for n in notes if "GXTP738X" in n]
        self.assertTrue(pad and screen, notes)
        self.assertIn("is the i2c touchpad", pad[0].lower())
        self.assertIn("not the touchscreen", pad[0].lower())
        self.assertIn("is the i2c touchscreen", screen[0].lower())
        self.assertIn("not the touchpad", screen[0].lower())
        self.assertTrue(any("VoodooI2C" in n for n in pad), notes)

    def test_the_external_enclosure_is_not_treated_as_the_target(self):
        notes = huawei.notes(REPORT, KEXTS, {"offline_recommended": False})
        ext = [n for n in notes if "TBU405Pro" in n]
        self.assertTrue(ext, notes)
        self.assertIn("external", ext[0].lower())
        self.assertIn("APFS", ext[0])

    def test_nothing_claims_a_verified_boot(self):
        notes = huawei.notes(REPORT, KEXTS, {"offline_recommended": True})
        joined = " ".join(notes).lower()
        self.assertNotIn("has booted", joined)
        self.assertNotIn("works on this machine", joined)


if __name__ == "__main__":
    unittest.main()
