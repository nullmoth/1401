"""A Linux scan names a monitor after its DRM port ("HDMI-A", "eDP") and can list ACPI paths from the root scope
("\\HPET"). The builder's report schema knows only the Windows connector names and _SB paths, and refuses the whole
report over one unknown value, so normalize translates the port and leaves out the unusable path."""
import unittest

from p1401 import report


def scan(**sections):
    base = {"GPU": {"Card": {"Manufacturer": "NVIDIA", "Device ID": "10DE-1234"}},
            "Motherboard": {"Platform": "Desktop"}, "Input": {}, "Network": {},
            "USB Controllers": {}, "Storage Controllers": {}}
    base.update(sections)
    return base


class ConnectorNames(unittest.TestCase):
    def test_drm_port_names_become_windows_ones(self):
        for was, name in (("HDMI-A", "HDMI"), ("DP", "DP"), ("DVI-I", "DVI"), ("VGA", "VGA"),
                          ("eDP", "Internal"), ("LVDS", "Internal")):
            out, notes = report.normalize(scan(Monitor={"Display": {"Connector Type": was, "Resolution": "1920x1080"}}))
            self.assertEqual(out["Monitor"]["Display"]["Connector Type"], name, was)
            if was == name:
                self.assertEqual(notes, [], was)
            else:
                self.assertEqual(len(notes), 1, was)
                self.assertIn("Linux names the port", notes[0])

    def test_a_port_the_builder_does_not_know_is_uninitialized(self):
        out, notes = report.normalize(scan(Monitor={"Display": {"Connector Type": "Virtual", "Resolution": "1024x768"}}))
        self.assertEqual(out["Monitor"]["Display"]["Connector Type"], "Uninitialized")
        self.assertEqual(len(notes), 1)

    def test_a_missing_connector_type_is_uninitialized(self):
        out, notes = report.normalize(scan(Monitor={"Display": {"Resolution": "1024x768"}}))
        self.assertEqual(out["Monitor"]["Display"]["Connector Type"], "Uninitialized")
        self.assertIn("None", notes[0])

    def test_windows_names_are_left_alone(self):
        out, notes = report.normalize(scan(Monitor={"Display": {"Connector Type": "HDMI", "Resolution": "1920x1080"}}))
        self.assertEqual(out["Monitor"]["Display"]["Connector Type"], "HDMI")
        self.assertEqual(notes, [])


class AcpiPaths(unittest.TestCase):
    def test_a_root_scope_path_is_left_out_and_sb_paths_are_kept(self):
        out, notes = report.normalize(scan(**{"System Devices": {
            "PNP0103": {"Bus Type": "ACPI", "Device": "PNP0103", "ACPI Path": "\\HPET"},
            "RTC": {"Bus Type": "ACPI", "Device": "PNP0B00", "ACPI Path": "\\_SB.PCI0.SBRG.RTC0"}}}))
        self.assertNotIn("ACPI Path", out["System Devices"]["PNP0103"])
        self.assertEqual(out["System Devices"]["PNP0103"]["Device"], "PNP0103")
        self.assertEqual(out["System Devices"]["RTC"]["ACPI Path"], "\\_SB.PCI0.SBRG.RTC0")
        self.assertEqual(len(notes), 1)
        self.assertIn("outside _SB", notes[0])

    def test_the_path_is_left_out_in_any_device_section(self):
        out, notes = report.normalize(scan(Sound={"Codec": {"Bus Type": "HDAUDIO", "Device ID": "10EC-0897",
                                                            "ACPI Path": "\\AOD_"}}))
        self.assertNotIn("ACPI Path", out["Sound"]["Codec"])
        self.assertEqual(out["Sound"]["Codec"]["Device ID"], "10EC-0897")
        self.assertEqual(len(notes), 1)
        self.assertIn("outside _SB", notes[0])


if __name__ == "__main__":
    unittest.main()
