"""The stick-log diagnoser: each finding is a failure class measured in the stick logs and chats, and each one tells the
person what to change, in steps. A normal log with nothing typed must not invent a failure it cannot see."""
import unittest

from p1401 import diagnose

HANDOFF = "OCB: Matching <>/0[0] args on type 4\nAAPL: #[EB|LOG:EXITBS:START] 2026-10-26T03:00:00\n"


def cpu(name):
    return f"OCCPU: Found {name}\n"


def ids(result):
    return [f["id"] for f in result["findings"]]


class Diagnose(unittest.TestCase):
    def test_akm_in_the_log_says_bios_and_rebuild(self):
        r = diagnose.diagnose([cpu("AMD Ryzen 7 7700 8-Core Processor") + "AAPL: #[EB.MM.AKM|!] Err(0x9)\n"])
        self.assertEqual(ids(r)[0], "no-room-for-kernel")
        self.assertTrue(r["findings"][0]["rebuild"])
        self.assertIn("Above 4G", r["findings"][0]["steps"][0])

    def test_typed_exitbs_on_arrow_lake_says_vtd_off_first(self):
        r = diagnose.diagnose([cpu("Intel(R) Core(TM) Ultra 7 265K") + HANDOFF], "stuck at EXITBS:START")
        self.assertEqual(ids(r), ["froze-at-handoff"])
        self.assertIn("VT-d Off", r["findings"][0]["steps"][0])

    def test_typed_exitbs_on_amd_says_iommu_not_vtd(self):
        r = diagnose.diagnose([cpu("AMD Ryzen 9 9950X3D 16-Core Processor") + HANDOFF], "EXITBS:START")
        steps = " ".join(r["findings"][0]["steps"])
        self.assertIn("IOMMU", steps)
        self.assertNotIn("VT-d", steps)

    def test_the_scan_report_wins_over_the_log_cpu(self):
        report = {"CPU": {"Manufacturer": "Intel", "Processor Name": "Intel(R) Core(TM) i5-12400F", "Codename": "Alder Lake-S"}}
        r = diagnose.diagnose([cpu("AMD Ryzen 7 7700") + HANDOFF], "exitbs", report)
        self.assertIn("VT-d Off", r["findings"][0]["steps"][0])

    def test_windows_entry_chosen_says_pick_1401(self):
        r = diagnose.diagnose(["OCB: Matching <>/0[0] args on type 32\nOCB: StartImage success\n"])
        self.assertEqual(ids(r), ["started-windows"])

    def test_access_denied_drivers_say_secure_boot_off(self):
        r = diagnose.diagnose(["OC: Driver HfsPlus.efi at 0 cannot be loaded - Access Denied!\n"])
        self.assertEqual(ids(r), ["secure-boot-on"])

    def test_missing_hfsplus_says_rebuild_online(self):
        r = diagnose.diagnose(["OC: Driver HfsPlus.efi at 0 cannot be found!\n"])
        self.assertEqual(ids(r), ["hfsplus-missing"])
        self.assertTrue(r["findings"][0]["rebuild"])

    def test_only_the_last_start_counts_for_windows(self):
        mac_then_windows = HANDOFF + "OCB: Matching <>/0[0] args on type 32\n"
        windows_then_mac = "OCB: Matching <>/0[0] args on type 32\n" + HANDOFF
        self.assertEqual(ids(diagnose.diagnose([mac_then_windows])), ["started-windows"])
        self.assertEqual(ids(diagnose.diagnose([windows_then_mac])), ["after-handoff"])

    def test_pci_configuration_says_above4g_and_rebar(self):
        r = diagnose.diagnose([HANDOFF], "PCI configuration begin")
        self.assertEqual(ids(r), ["pci-configuration"])
        self.assertIn("Resizable BAR", " ".join(r["findings"][0]["steps"]))

    def test_black_screen_with_cursor_is_named(self):
        self.assertEqual(ids(diagnose.diagnose([], "black screen with cursor after install")), ["black-screen-cursor"])

    def test_typed_classes_each_find_their_own(self):
        for said, want in (("kernel panic", "kernel-panic"), ("prohibited sign", "boot-refused"),
                           ("not has mac os boot option", "no-macos-entry"), ("Still waiting for root device", "waiting-for-root")):
            with self.subTest(said=said):
                self.assertEqual(ids(diagnose.diagnose([], said)), [want])

    def test_lines_people_typed_find_the_right_class(self):
        for said, want in (("A kernel panic didn't occur, but there was only a mouse cursor on a black screen.", ["black-screen-cursor"]),
                           ("OpenCore did not show booting into macOS as an option, just made me boot into Windows.", ["no-macos-entry"]),
                           ("my sata disk and hdd sata, im dont see in the hakintosh", ["no-disk-in-installer"]),
                           ("pci", ["pci-configuration"]), ("pci wifi adapter not working", [])):
            with self.subTest(said=said):
                self.assertEqual(ids(diagnose.diagnose([], said)), want)

    def test_a_normal_handoff_with_nothing_typed_says_what_the_log_cannot_show(self):
        r = diagnose.diagnose([cpu("AMD Ryzen 7 7735H with Radeon Graphics") + HANDOFF])
        self.assertEqual(ids(r), ["after-handoff"])
        self.assertIn("type the last line", r["findings"][0]["cause"])

    def test_no_logs_and_nothing_typed_finds_nothing(self):
        self.assertEqual(ids(diagnose.diagnose([], "")), [])

    def test_every_line_a_person_can_see_has_its_chinese_translation(self):
        from p1401 import loc
        cases = [(["AAPL: EB.MM.AKM"], ""), (["OC: Driver X.efi at 0 cannot be loaded - Access Denied"], ""),
                 (["OC: Driver HfsPlus.efi at 0 cannot be found"], ""), (["OCB: Matching <>/0[0] args on type 32"], ""),
                 ([HANDOFF], "")]
        for name in ("Intel(R) Core(TM) Ultra 7 265K", "Intel(R) Core(TM) i7-9700K", "AMD Ryzen 7 7700", "unknown"):
            cases.append(([cpu(name) + HANDOFF], "exitbs"))
        for said in ("pci configuration", "black cursor", "panic", "prohibited", "only windows", "root device", "sata disk not seen"):
            cases.append(([], said))
        missing = set()
        for logs, said in cases:
            for f in diagnose.diagnose(logs, said)["findings"]:
                missing |= {x for x in [f["title"], f["cause"]] + f["steps"] if x not in loc.ZH}
        self.assertEqual(sorted(missing), [])

    def test_the_cli_prints_steps_and_a_json_last_line(self):
        import io, json, os, tempfile, contextlib  # noqa: E401
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "opencore-1.txt")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(cpu("Intel(R) Core(TM) Ultra 9 285K") + HANDOFF)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                diagnose.main(["--log", p, "--stopped", "EXITBS:START"])
        lines = buf.getvalue().splitlines()
        self.assertTrue(any(l.startswith("    1. ") for l in lines))
        self.assertEqual(json.loads(lines[-1])["findings"][0]["id"], "froze-at-handoff")


if __name__ == "__main__":
    unittest.main()
