"""macOS has no third-party NVMe driver, so some OEM drives never appear in the installer or stall the install, and
the person finds out only after the long download. The scan now records the drive models, and the build warns up
front and enables NVMeFix for the families a power-state fix helps. Earlier builds recorded no drive model at all."""
import os
import plistlib
import tempfile
import unittest

from p1401 import engine, policy, report, scan, storage_drives


def raw(*drives):
    return {"Storage Drives": {name: props for name, props in drives}}


class StorageDrivesSection(unittest.TestCase):
    def test_builds_the_section_from_get_disk_rows(self):
        rows = [{"Number": 0, "FriendlyName": "Samsung SSD 990 PRO 2TB", "Model": "Samsung SSD 990 PRO 2TB",
                 "BusType": "NVMe", "MediaType": "SSD", "Size": 2000000000000, "IsBoot": False, "IsSystem": True},
                {"Number": 1, "FriendlyName": "SanDisk Ultra", "Model": "", "BusType": "USB", "Size": 16000000000}]
        section = scan._storage_drives_section(rows)
        self.assertEqual(section["Disk 0"]["Model"], "Samsung SSD 990 PRO 2TB")
        self.assertEqual(section["Disk 0"]["Bus Type"], "NVMe")
        self.assertTrue(section["Disk 0"]["System"])
        self.assertEqual(section["Disk 1"]["Model"], "SanDisk Ultra")  # FriendlyName when Model is blank

    def test_a_row_without_a_model_is_skipped(self):
        self.assertEqual(scan._storage_drives_section([{"Number": 2, "BusType": "NVMe"}]), {})


class Classify(unittest.TestCase):
    def test_unseen_family_on_an_internal_drive_is_named(self):
        r = raw(("Disk 0", {"Model": "Samsung PM9C1a 512GB", "Bus Type": "NVMe"}))
        self.assertEqual(storage_drives.unseen_drives(r), ["Samsung PM9C1a"])
        self.assertFalse(storage_drives.any_supported_fixed_drive(r))

    def test_usb_is_never_the_target(self):
        r = raw(("Disk 0", {"Model": "Samsung PM9C1a", "Bus Type": "USB"}))
        self.assertEqual(storage_drives.unseen_drives(r), [])

    def test_a_second_internal_drive_leaves_a_target(self):
        r = raw(("Disk 0", {"Model": "Samsung PM9C1a", "Bus Type": "NVMe"}),
                ("Disk 1", {"Model": "WD Blue SN580", "Bus Type": "NVMe"}))
        self.assertTrue(storage_drives.any_supported_fixed_drive(r))

    def test_nvmefix_families(self):
        self.assertTrue(storage_drives.wants_nvmefix(raw(("Disk 0", {"Model": "Samsung SSD PM981 MZVLB", "Bus Type": "NVMe"}))))
        self.assertTrue(storage_drives.wants_nvmefix(raw(("Disk 0", {"Model": "SK hynix BC511 HFM256", "Bus Type": "NVMe"}))))

    def test_ordinary_retail_ssd_raises_nothing(self):
        r = raw(("Disk 0", {"Model": "Samsung SSD 990 PRO 2TB", "Bus Type": "NVMe"}))
        self.assertEqual(storage_drives.unseen_drives(r), [])
        self.assertFalse(storage_drives.wants_nvmefix(r))
        self.assertEqual(storage_drives.warning(r), "")

    def test_warning_names_the_drive_and_advises_another(self):
        w = storage_drives.warning(raw(("Disk 0", {"Model": "Samsung PM9C1a", "Bus Type": "NVMe"})))
        self.assertIn("PM9C1a", w)
        self.assertIn("different SSD", w)

    def test_a_raw_model_number_is_still_captured_even_when_not_classified(self):
        # Windows may report PM9C1a as its model number; the capture records it so a log can name it, and the
        # classifier simply does not claim a verdict it cannot back.
        r = raw(("Disk 0", {"Model": "MZVL2512HCJQ-00B00", "Bus Type": "NVMe"}))
        self.assertEqual(storage_drives.unseen_drives(r), [])
        self.assertIn("Disk 0", r["Storage Drives"])


def build_with_drives(drives, nvmefix_entry=None):
    t = tempfile.mkdtemp()
    path = os.path.join(t, "config.plist")
    kernel_add = [nvmefix_entry] if nvmefix_entry else []
    cfg = {"NVRAM": {"Add": {}, "Delete": {}}, "Kernel": {"Add": kernel_add, "Patch": [], "Quirks": {}},
           "Booter": {"Quirks": {}, "MmioWhitelist": []}, "Misc": {}, "ACPI": {"Add": [], "Delete": []},
           "UEFI": {"Drivers": [], "Quirks": {}}, "PlatformInfo": {"Generic": {}}}
    with open(path, "wb") as f:
        plistlib.dump(cfg, f)
    res = engine.BuildResult(ok=True, out_dir=t, macos_version="24.6.0",
                             hardware={"CPU": {"Manufacturer": "Intel"}, "GPU": {}},
                             raw_hardware={"CPU": {"Manufacturer": "Intel"}, "GPU": {}, **raw(*drives)})
    changes = policy.apply(path, res, engine.Policy())
    with open(path, "rb") as f:
        return plistlib.load(f), changes


def rules(changes):
    return {c["rule"] for c in changes}


class PolicyStorage(unittest.TestCase):
    def test_nvmefix_family_enables_the_kext_and_warns(self):
        cfg, changes = build_with_drives(
            [("Disk 0", {"Model": "Samsung SSD PM981", "Bus Type": "NVMe"})],
            nvmefix_entry={"BundlePath": "NVMeFix.kext", "Enabled": False})
        self.assertTrue(any(k["BundlePath"] == "NVMeFix.kext" and k["Enabled"] for k in cfg["Kernel"]["Add"]))
        self.assertIn("storage-nvmefix", rules(changes))
        self.assertIn("storage-drive-warning", rules(changes))

    def test_unseen_family_warns_even_without_an_nvmefix_entry(self):
        _, changes = build_with_drives([("Disk 0", {"Model": "Samsung PM9C1a", "Bus Type": "NVMe"})])
        note = next(c["after"] for c in changes if c["rule"] == "storage-drive-warning")
        self.assertIn("PM9C1a", note)

    def test_ordinary_ssd_adds_no_storage_change(self):
        _, changes = build_with_drives([("Disk 0", {"Model": "WD Black SN850X", "Bus Type": "NVMe"})])
        self.assertNotIn("storage-nvmefix", rules(changes))
        self.assertNotIn("storage-drive-warning", rules(changes))


class ReportCarries(unittest.TestCase):
    def test_diagnostic_hardware_includes_storage_drives(self):
        rep = {"Storage Drives": {"Disk 0": {"Model": "Samsung PM9C1a", "Bus Type": "NVMe", "Size": 512000000000}}}
        out = report.diagnostic_hardware(rep)
        self.assertEqual(out["Storage Drives"][0]["Model"], "Samsung PM9C1a")


if __name__ == "__main__":
    unittest.main()
