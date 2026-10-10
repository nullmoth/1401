"""The Linux probe converts into a hardware report the builder accepts (10-09: a user with no working Windows scan sent
only the probe, and the builder rejected it for missing Motherboard/BIOS/CPU/GPU/Network)."""
import json
import os
import tempfile
import unittest

from p1401 import probe_report, report


def _probe(d, chassis="3", gpu_bar=32 << 30):
    rep = {
        "firmware": {"boot_mode": "UEFI", "SecureBoot": 0},
        "dmi": {"board_vendor": "ASUSTeK COMPUTER INC.", "board_name": "ROG STRIX X670E-E GAMING WIFI", "bios_version": "4003",
                "chassis_type": chassis},
        "cpu": {"vendor": "AuthenticAMD", "brand": "AMD Ryzen 9 9950X3D 16-Core Processor", "family": 26, "model": 68,
                "cores": 16, "packages": 1, "features": {"sse2": True, "sse3": True, "ssse3": True, "sse4_1": True,
                                                         "sse4_2": True, "avx": True, "avx2": True, "svm": True}},
        "pci": [
            {"bdf": "0000:01:00.0", "vendor": "0x10de", "device": "0x2b85", "subsystem_vendor": "0x1458", "subsystem_device": "0x416e",
             "class": "0x030000", "device_name": "GB202 [GeForce RTX 5090]", "boot_vga": "1",
             "oc_path": "PciRoot(0x0)/Pci(0x1,0x1)/Pci(0x0,0x0)", "acpi_path": "\\_SB_.PCI0.GPP0.VGA_",
             "bars": [{"index": 1, "size": gpu_bar, "prefetch": True}]},
            {"bdf": "0000:12:00.0", "vendor": "0x1002", "device": "0x13c0", "subsystem_vendor": "0x1043", "subsystem_device": "0x8877",
             "class": "0x030000", "device_name": "Granite Ridge [Radeon Graphics]", "boot_vga": None,
             "oc_path": "PciRoot(0x0)/Pci(0x8,0x1)/Pci(0x0,0x0)", "bars": []},
            {"bdf": "0000:02:00.0", "vendor": "0x144d", "device": "0xa80c", "class": "0x010802", "device_name": "NVMe",
             "oc_path": "PciRoot(0x0)/Pci(0x1,0x2)/Pci(0x0,0x0)"},
            {"bdf": "0000:0a:00.0", "vendor": "0x8086", "device": "0x15f3", "class": "0x020000", "device_name": "I225-V",
             "oc_path": "PciRoot(0x0)/Pci(0x2,0x1)/Pci(0x0,0x0)"},
            {"bdf": "0000:0b:00.0", "vendor": "0x8086", "device": "0x2725", "class": "0x028000", "device_name": "AX210",
             "oc_path": "PciRoot(0x0)/Pci(0x2,0x2)/Pci(0x0,0x0)"},
        ],
        "audio": [{"codec": "Nvidia GPU aa HDMI/DP", "vendor_id": "0x10de00aa"}],
    }
    os.makedirs(os.path.join(d, "acpi", "tables"))
    for t in ("DSDT.aml", "APIC.aml"):
        open(os.path.join(d, "acpi", "tables", t), "wb").write(b"\0" * 64)
    json.dump(rep, open(os.path.join(d, "report.json"), "w"))


class ProbeReport(unittest.TestCase):
    def convert(self, **kw):
        t = tempfile.mkdtemp()
        _probe(os.path.join(t, "p"), **kw)
        r, a = probe_report.convert(os.path.join(t, "p"), os.path.join(t, "out"))
        return json.load(open(r)), a

    def test_a_probe_becomes_a_report_with_every_required_section(self):
        rep, acpi = self.convert()
        for k in ("Motherboard", "BIOS", "CPU", "GPU", "Network", "USB Controllers", "Storage Controllers", "Sound", "Input"):
            self.assertIn(k, rep)
        self.assertEqual(sorted(os.listdir(acpi)), ["APIC.aml", "DSDT.aml"])
        self.assertEqual(rep["Motherboard"]["Chipset"], "X670")
        self.assertEqual(rep["CPU"]["Codename"], "Granite Ridge")
        self.assertIn("AVX2", rep["CPU"]["SIMD Features"])
        self.assertEqual(rep["BIOS"]["Secure Boot"], "Disabled")

    def test_the_card_keeps_its_opencore_path_and_the_igpu_is_integrated(self):
        rep, _ = self.convert()
        g = rep["GPU"]["GB202 [GeForce RTX 5090]"]
        self.assertEqual(g["PCI Path"], "PciRoot(0x0)/Pci(0x1,0x1)/Pci(0x0,0x0)")
        self.assertEqual(g["Device ID"], "10DE-2B85")
        self.assertEqual(g["Device Type"], "Discrete GPU")
        self.assertEqual(rep["GPU"]["Granite Ridge [Radeon Graphics]"]["Device Type"], "Integrated GPU")

    def test_resizable_bar_is_read_from_the_bar_size_both_ways(self):
        on, _ = self.convert(gpu_bar=32 << 30)
        off, _ = self.convert(gpu_bar=256 << 20)
        self.assertEqual(on["GPU"]["GB202 [GeForce RTX 5090]"]["Resizable BAR"], "Enabled")
        self.assertEqual(off["GPU"]["GB202 [GeForce RTX 5090]"]["Resizable BAR"], "Disabled")

    def test_a_laptop_chassis_reads_laptop(self):
        rep, _ = self.convert(chassis="10")
        self.assertEqual(rep["Motherboard"]["Platform"], "Laptop")

    def test_the_converted_report_passes_the_builders_own_validation(self):
        t = tempfile.mkdtemp()
        _probe(os.path.join(t, "p"))
        r, _ = probe_report.convert(os.path.join(t, "p"), os.path.join(t, "out"))
        raw = open(r, "rb").read()
        path, _notes = report.normalized_copy(os.path.abspath(r), tempfile.mkdtemp(), raw_hardware=None)
        self.assertTrue(os.path.isfile(path))


if __name__ == "__main__":
    unittest.main()
