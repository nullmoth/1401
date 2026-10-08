"""Failed-build evidence arms (private, report probe-completeness-004). Run from a p1401 tree: python3 -m unittest
tests.test_capture_completeness. Every engine part is a stand-in; nothing is downloaded and no real path is written."""
import hashlib, json, sys, tempfile, types, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from p1401 import engine
from p1401.__main__ import _result_json

DGPU = {"Manufacturer": "NVIDIA", "Device ID": "10DE-25A0", "Subsystem ID": "380217AA", "Device Type": "Discrete GPU",
        "PCI Path": "PciRoot(0x0)/Pci(0x1,0x0)/Pci(0x0,0x0)", "ACPI Path": "\\_SB.PCI0.GPP0.PEGP", "Bus Type": "PCI"}
IGPU = {"Manufacturer": "AMD", "Device ID": "1002-1638", "Subsystem ID": "380217AA", "Device Type": "Integrated GPU",
        "PCI Path": "PciRoot(0x0)/Pci(0x8,0x1)/Pci(0x0,0x0)", "ACPI Path": "\\_SB.PCI0.GP17.VGA", "Bus Type": "PCI"}
REPORT = {
    "CPU": {"Manufacturer": "AMD", "Processor Name": "Fixture 6800H", "Core Count": "8", "Thread Count": "16", "Serial": "CPU-SERIAL-PRIVATE"},
    "Motherboard": {"Name": "Fixture Laptop", "Platform": "Laptop", "Serial Number": "BOARD-SERIAL-PRIVATE"},
    "BIOS": {"Firmware Type": "UEFI", "Version": "J2CN41WW"},
    "GPU": {"NVIDIA GeForce RTX 3050 Laptop GPU": DGPU, "AMD Radeon(TM) Graphics": IGPU},
    "Monitor": {"Built-in": {"Connected GPU": "AMD Radeon(TM) Graphics", "Connector Type": "Internal"}},
    "Network": {"Realtek Gaming 2.5GbE": {"Device ID": "10EC-8125", "Subsystem ID": "380217AA", "Bus Type": "PCI",
                                         "PCI Path": "PciRoot(0x0)/Pci(0x2,0x2)/Pci(0x0,0x0)", "MAC Address": "a4:bb:6d:01:02:03"}},
    "Storage Controllers": {"Intel VMD": {"Device ID": "8086-9A0B", "Subsystem ID": "380217AA", "Bus Type": "PCI",
                                          "PCI Path": "PciRoot(0x0)/Pci(0xE,0x0)", "Serial Number": "DISK-SERIAL-PRIVATE"}},
    "Input": {"ELAN Touchpad": {"Device ID": "ELAN0001", "Bus Type": "I2C", "ACPI Path": "\\_SB.I2CD.TPD0"}},
    "Sound": {"Realtek ALC287": {"Device ID": "10EC-0287", "Codec ID": "10EC0287", "Bus Type": "HDAUDIO",
                                 "Audio Endpoints": ["Fixture Headphones"]}},
}


class FakeEngine:
    """Stands in for the upstream engine: validation passes, the compatibility pass drops the discrete GPU (as it does
    for an unsupported card), and the step after it fails."""
    def __init__(self):
        acpi = SimpleNamespace(acpi_tables=None, r=SimpleNamespace(run=lambda *a, **k: ("", "", 0)), iasl="iasl")
        self.o = SimpleNamespace(); self.k = SimpleNamespace()
        self.v = SimpleNamespace(validate_report=lambda p: (True, [], [], json.loads(Path(p).read_text())))
        self.ac = SimpleNamespace(acpi=acpi, dsdt=None, read_acpi_tables=lambda p: None, ensure_dsdt=lambda: True)
        def compat(report):
            hw = json.loads(json.dumps(report)); hw["GPU"].pop("NVIDIA GeForce RTX 3050 Laptop GPU")
            return hw, {}, {}
        self.c = SimpleNamespace(check_gpu_compatibility=lambda: None, hardware_report=REPORT, check_compatibility=compat)
    def select_macos_version(self, *a):
        raise RuntimeError("version selection stopped after the compatibility pass")


class Capture(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.root = Path(self.t.name)
        self.acpi = self.root / "ACPI"; self.acpi.mkdir(); (self.acpi / "dsdt.aml").write_bytes(b"DSDT" + bytes(60))
        ds = types.ModuleType("Scripts.datasets"); pci = types.ModuleType("Scripts.datasets.pci_data"); pci.WirelessCardIDs = []
        self.modules = patch.dict(sys.modules, {"Scripts": types.ModuleType("Scripts"),
                                               "Scripts.datasets": ds, "Scripts.datasets.pci_data": pci})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def tearDown(self):
        self.t.cleanup()

    def run_build(self, report, factory=FakeEngine, acpi=True):
        rp = self.root / "Report.json"; rp.write_text(json.dumps(report))
        if not acpi:
            for f in self.acpi.iterdir(): f.unlink()
        utils = SimpleNamespace(Utils=type("Utils", (), {}))
        with patch.object(engine, "_load_engine", return_value=(SimpleNamespace(OCPE=factory), utils)), \
             patch.object(engine, "OCK_CACHE", str(self.root / "cache")), \
             patch("p1401.hwcapture.sys.platform", "linux"):
            r = engine.build(str(rp), str(self.acpi), str(self.root / "out"), download=False)
        return r, _result_json(r), rp.read_bytes()

    def gpu_ids(self, data):
        return {(g.get("Device ID"), g.get("Subsystem ID"), g.get("PCI Path")) for g in data["hardware_summary"].get("GPU", [])}

    def test_failure_after_compatibility_keeps_the_dropped_gpu(self):
        r, data, _ = self.run_build(REPORT)
        self.assertFalse(r.ok); self.assertIn("after the compatibility pass", r.error)
        self.assertIn(("10DE-25A0", "380217AA", DGPU["PCI Path"]), self.gpu_ids(data))

    def test_hybrid_laptop_keeps_both_gpus_with_routing(self):
        _, data, _ = self.run_build(REPORT)
        g = {x.get("Device ID"): x for x in data["hardware_summary"]["GPU"]}
        self.assertEqual(g["1002-1638"].get("ACPI Path"), IGPU["ACPI Path"])
        self.assertEqual(g["10DE-25A0"].get("ACPI Path"), DGPU["ACPI Path"])
        self.assertEqual(data["hardware_summary"]["Monitor"][0]["Connected GPU"], "AMD Radeon(TM) Graphics")

    def test_unknown_gpu_without_driver_keeps_raw_pci_identity(self):
        rep = json.loads(json.dumps(REPORT))
        rep["GPU"] = {"Microsoft Basic Display Adapter": {"Manufacturer": "Unknown", "Device ID": "", "Subsystem ID": "",
                                                          "PCI Path": "PciRoot(0x0)/Pci(0x1,0x0)/Pci(0x0,0x0)", "ACPI Path": "\\_SB.PCI0.PEG0.PEGP"}}
        r, data, _ = self.run_build(rep)
        self.assertFalse(r.ok)
        g = data["hardware_summary"]["GPU"][0]
        self.assertEqual((g.get("PCI Path"), g.get("ACPI Path")), ("PciRoot(0x0)/Pci(0x1,0x0)/Pci(0x0,0x0)", "\\_SB.PCI0.PEG0.PEGP"))

    def test_missing_privileges_acpi_still_logs_hardware(self):
        r, data, _ = self.run_build(REPORT, acpi=False)
        self.assertIn("administrator", r.error)
        self.assertTrue(data["hardware_summary"]["GPU"]); self.assertEqual(data["acpi_fingerprints"], [])

    def test_two_identical_cards_stay_two_entries(self):
        rep = json.loads(json.dumps(REPORT))
        rep["GPU"] = {"NVIDIA GeForce RTX 3090": dict(DGPU, **{"Device ID": "10DE-2204"}),
                      "NVIDIA GeForce RTX 3090 #2": dict(DGPU, **{"Device ID": "10DE-2204", "PCI Path": "PciRoot(0x0)/Pci(0x3,0x1)/Pci(0x0,0x0)"})}
        _, data, _ = self.run_build(rep)
        self.assertEqual(len([g for g in data["hardware_summary"]["GPU"] if g.get("Device ID") == "10DE-2204"]), 2)

    def test_vmd_i2c_and_codec_evidence_is_logged(self):
        _, data, _ = self.run_build(REPORT)
        hs = data["hardware_summary"]
        self.assertEqual(hs.get("Storage Controllers", [{}])[0].get("Device ID"), "8086-9A0B")
        self.assertEqual(hs.get("Input", [{}])[0].get("ACPI Path"), "\\_SB.I2CD.TPD0")
        self.assertEqual(hs.get("Sound", [{}])[0].get("Codec ID"), "10EC0287")

    def test_exact_scan_hash_and_unobservable_fields(self):
        _, data, raw = self.run_build(REPORT)
        self.assertEqual(data.get("report_sha256"), hashlib.sha256(raw).hexdigest())
        self.assertIn("BIOS setup options", data["hardware_summary"].get("not_observed", []))

    def test_no_serial_mac_or_endpoint_name_is_logged(self):
        _, data, _ = self.run_build(REPORT)
        s = json.dumps(data)
        for private in ("SERIAL-PRIVATE", "a4:bb:6d", "Fixture Headphones"):
            self.assertNotIn(private, s)


if __name__ == "__main__":
    unittest.main()


class CaptureInLog(Capture):
    def test_failed_build_log_carries_capture_with_statuses(self):
        r, data, _ = self.run_build(REPORT)
        cap = data.get("capture") or {}
        self.assertEqual(cap.get("cpu_topology", {}).get("status"), "unavailable")
        kinds = {g["device_id"]: g["kind"] for g in cap.get("gpus", [])}
        self.assertEqual(kinds.get("10DE-25A0"), "PCI adapter; physical backing and driver qualification unverified")
        self.assertIn("devices", cap.get("nvidia", {}))
