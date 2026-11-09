"""The replay gate (tools/machine_gate.py) over every PC fingerprint the field has sent (tests/corpus/machines.json.gz).

The corpus holds device IDs only. Each machine is replayed through the builder's hardware decisions for macOS 15 and 26;
see tools/machine_replay.py for what that covers and what it cannot (ACPI-dependent steps). The arms below are the rules
the builder must satisfy for all of them, and the arms that prove each rule can fire.
"""
import copy
import os
import sys
import unittest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
sys.path.insert(0, TOOLS)
import machine_census as census  # noqa: E402
import machine_corpus  # noqa: E402
import machine_gate as gate  # noqa: E402
import machine_knowngood  # noqa: E402
import machine_replay as replay  # noqa: E402

MACOS = ("24", "25")
_CACHE = {}


def corpus():
    if not _CACHE:
        machines = machine_corpus.load()["machines"]
        results = replay.run(machines, MACOS)
        stops = [m for m in machines if (results[m["key"]]["24"].get("storage_plan") or {}).get("kind") == "vmd-off"]
        _CACHE.update(machines=machines, known=machine_knowngood.load(), results=results,
                      external=replay.run(stops, ("24",), external_target=True))
    return _CACHE


class ReplayGate(unittest.TestCase):
    def test_every_machine_in_the_field_corpus_satisfies_the_gate_or_has_a_named_reason(self):
        c = corpus()
        tally, offenders = gate.summarize(c["machines"], c["results"], c["known"], MACOS)
        self.assertEqual(offenders[:10], [])
        total = sum(m["machines"] for m in c["machines"])
        for mv in MACOS:
            self.assertEqual(tally[mv]["satisfied"] + sum(tally[mv]["named"].values()), total)

    def test_the_corpus_is_the_size_the_gate_claims(self):
        c = corpus()
        self.assertGreaterEqual(len(c["machines"]), 4000)
        self.assertGreaterEqual(sum(m["machines"] for m in c["machines"]), 8000)

    def test_a_named_reason_is_the_only_way_to_stop_and_every_one_is_in_the_table(self):
        c = corpus()
        seen = set()
        for m in c["machines"]:
            r = c["results"][m["key"]]["24"]
            if not r["ok"]:
                seen.add(gate.refusal_code(r["refused"] or r["crash"]))
        self.assertNotIn(None, seen)
        self.assertLessEqual(seen, set(gate.NAMED))

    def test_a_pc_behind_intel_vmd_is_planned_with_the_bios_path_and_the_windows_preparation(self):
        c = corpus()
        vmd = [m for m in c["machines"] if (c["results"][m["key"]]["24"].get("storage_plan") or {}).get("kind") == "vmd-off"]
        self.assertGreater(len(vmd), 400)
        for m in vmd:
            r = c["results"][m["key"]]["24"]
            self.assertTrue(r["ok"])
            self.assertTrue(r["storage_plan"]["bios_path"])
            self.assertTrue(any(b.startswith("Turn off Intel VMD") for b in r["bios"]))

    def test_with_the_external_drive_switch_every_vmd_pc_is_planned_for_an_external_drive(self):
        c = corpus()
        self.assertGreater(len(c["external"]), 400)
        for key, per in c["external"].items():
            self.assertTrue(per["24"]["ok"], (key, per["24"]["refused"][:120]))
            self.assertEqual(per["24"]["storage_plan"]["kind"], "external-drive")

    def test_the_only_stops_left_are_virtual_machines_a_graphics_chip_macos_has_no_driver_for_and_a_zhaoxin_cpu(self):
        c = corpus()
        codes = {gate.refusal_code(c["results"][m["key"]]["24"]["refused"] or c["results"][m["key"]]["24"]["crash"])
                 for m in c["machines"] if not c["results"][m["key"]]["24"]["ok"]}
        self.assertEqual(codes, {"virtual-machine", "gpu-not-usable", "cpu-maker"})


class GateCanFire(unittest.TestCase):
    """A guard that never fires proves nothing: each rule must catch a result built to break it."""

    machine = {"hardware": {"CPU": {"Processor Name": "12th Gen Intel(R) Core(TM) i5-12400F"}, "GPU": [
        {"Device ID": "10DE-2503", "Manufacturer": "NVIDIA"}]}, "key": "x", "machines": 1}
    known = {"cpus": {"12th Gen Intel(R) Core(TM) i5-12400F": {"n": 100, "models": {"MacPro7,1": 98, "iMac20,1": 2}}},
             "gpus": {"10DE-2503": {"n": 50, "driver": 49, "metal": 49}}}

    def result(self, **kw):
        base = {"ok": True, "refused": "", "crash": "", "smbios": "MacPro7,1", "disabled_detail": [],
                "notices": ["NullMoth driver: NVIDIA GeForce RTX 3060 selected for macOS 15 Sequoia."]}
        base.update(kw)
        return base

    def test_a_storage_note_without_the_bios_path_in_the_requirements_is_a_violation(self):
        r = self.result(notices=self.result()["notices"] + ["Storage: x (8086-467F) is behind Intel VMD"], bios=[],
                        storage_plan={"kind": "vmd-off", "steps": ["a"], "bios_path": "F2", "controllers": ["x"]})
        self.assertEqual(gate.evaluate(self.machine, r, self.known)[0], "violation")
        r["bios"] = ["Turn off Intel VMD: F2"]
        self.assertEqual(gate.evaluate(self.machine, r, self.known)[0], "satisfied")

    def test_a_good_result_is_satisfied(self):
        self.assertEqual(gate.evaluate(self.machine, self.result(), self.known), ("satisfied", None))

    def test_a_switched_off_wifi_card_with_no_note_is_a_violation(self):
        r = self.result(disabled_detail=[["Network", "8086-272B", "Intel Wi-Fi 7 BE200"]])
        self.assertEqual(gate.evaluate(self.machine, r, self.known)[0], "violation")
        r["notices"].append("Wi-Fi: Intel Wi-Fi 7 BE200 (8086-272B) has no macOS driver, so this PC will have no Wi-Fi in macOS.")
        self.assertEqual(gate.evaluate(self.machine, r, self.known)[0], "satisfied")

    def test_the_engines_multi_line_transcript_does_not_count_as_an_explanation(self):
        r = self.result(disabled_detail=[["Network", "8086-272B", "x"]], notices=["Selected devices:\nNetwork x 8086-272B"])
        self.assertEqual(gate.evaluate(self.machine, r, self.known)[0], "violation")

    def test_an_unnamed_or_raw_stop_is_a_violation(self):
        for text in ("KeyError: 'Network'", "RuntimeError: hardware report rejected: [\"Root.Monitor.x: Missing\"]"):
            self.assertEqual(gate.evaluate(self.machine, self.result(ok=False, refused=text), self.known)[0], "violation")

    def test_a_mac_model_no_machine_with_this_cpu_used_is_a_violation(self):
        self.assertEqual(gate.evaluate(self.machine, self.result(smbios="MacBookPro16,2"), self.known)[0], "violation")

    def test_a_known_good_card_that_is_not_planned_for_the_driver_is_a_violation(self):
        self.assertEqual(gate.evaluate(self.machine, self.result(notices=[]), self.known)[0], "violation")


class FixesFromTheReplay(unittest.TestCase):
    def run_one(self, section, dev, experimental=False):
        c = copy.deepcopy(census.BASELINE)
        c[section] = c.get(section, []) + [dev]
        return replay.replay(c, macos="24", experimental=experimental)

    def test_a_catalogued_bluetooth_driver_reaches_a_device_the_engine_switched_off(self):
        r = self.run_one("Bluetooth", {"name": "Qualcomm FastConnect 7800 Bluetooth", "Device ID": "0489-E0F3", "Bus Type": "USB"})
        self.assertIn("BluetoothWCN7850", r["kexts"])
        self.assertNotIn("0489-E0F3", r["disabled"])

    def test_a_held_back_driver_says_which_card_it_is_for(self):
        r = self.run_one("Network", {"name": "Realtek RTL8821CE", "Device ID": "10EC-C82F", "Bus Type": "PCI", "Subsystem ID": "00000000",
                                    "PCI Path": "PciRoot(0x0)/Pci(0x1c,0x0)/Pci(0x0,0x0)"})
        self.assertTrue(any("10EC-C82F" in n and "NOT in this build" in n for n in r["notices"]))

    def test_a_card_with_no_driver_anywhere_gets_a_plain_note_with_what_to_use(self):
        r = self.run_one("Network", {"name": "Intel(R) Wi-Fi 7 BE200 320MHz", "Device ID": "8086-272B", "Bus Type": "PCI",
                                    "Subsystem ID": "00000000", "PCI Path": "PciRoot(0x0)/Pci(0x1c,0x0)/Pci(0x0,0x0)"})
        note = next(n for n in r["notices"] if "8086-272B" in n and "\n" not in n)
        self.assertIn("no macOS driver", note)
        self.assertIn("Ethernet", note)

    def test_three_bare_press_enter_prompts_in_a_row_are_not_a_loop(self):
        from p1401 import engine
        h = engine.Headless(type("U", (), {"Utils": type("X", (), {})}), engine.Policy())
        h.tee = engine._Tee(False)
        for _ in range(5):
            self.assertEqual(h.request_input(None, "Press Enter to continue..."), "")

    def test_a_hygon_dhyana_is_planned_as_a_zen_1_with_a_notice_that_it_is_untested(self):
        from p1401.report import normalize
        rep, notes = normalize({"CPU": {"Manufacturer": "HygonGenuine", "Processor Name": "Hygon C86-3G", "Codename": "Unknown"},
                                "Motherboard": {"Name": "x", "Platform": "Desktop"}, "GPU": {"g": {"Manufacturer": "AMD", "Device ID": "1002-1234"}}})
        self.assertEqual((rep["CPU"]["Manufacturer"], rep["CPU"]["Codename"]), ("AMD", "Summit Ridge"))
        self.assertTrue(any("not been run on a Hygon PC" in n for n in notes))

    def test_a_zhaoxin_cpu_stops_with_the_exact_reason(self):
        from p1401.report import normalize
        with self.assertRaises(RuntimeError) as c:
            normalize({"CPU": {"Manufacturer": "CentaurHauls", "Processor Name": "ZHAOXIN KaiXian KX-U6780A"}, "Motherboard": {}, "GPU": {"g": {"Manufacturer": "AMD", "Device ID": "1002-1234"}}})
        self.assertIn("CentaurHauls", str(c.exception))
        self.assertIn("CPUID vendor", str(c.exception))

    def test_an_adapter_windows_shows_as_basic_display_is_named_from_its_pci_id(self):
        from p1401.report import normalize
        with self.assertRaises(RuntimeError) as c:
            normalize({"CPU": {"Manufacturer": "Intel"}, "Motherboard": {}, "GPU": {"Microsoft Basic Display Adapter": {
                "Manufacturer": "Unknown", "Device ID": "15AD-0405"}}})
        self.assertIn("VMware", str(c.exception))
        self.assertIn("virtual machine", str(c.exception))

    def test_an_ssdt_oem_table_id_padded_with_nul_bytes_gives_a_comment_the_plist_accepts(self):
        import plistlib
        from p1401 import acpi_shims
        name = acpi_shims.table_name(b"Artic\x00\x00\x00")
        self.assertEqual(name, "Artic")
        plistlib.dumps({"Comment": f"ALIB to XLIB in {name}"})      # a NUL in the string raises ValueError

    def test_a_processor_name_with_nul_and_binary_after_it_is_cut_at_the_readable_part(self):
        import plistlib
        from p1401.report import normalize
        rep, notes = normalize({"CPU": {"Manufacturer": "AMD", "Processor Name": "AMD Custom APU 0932\x00  AmdCcxVhFf3PeiInit Entry"},
                                "Motherboard": {"Name": "x", "Platform": "Laptop"}, "GPU": {"g": {"Manufacturer": "AMD", "Device ID": "1002-1234"}}})
        self.assertEqual(rep["CPU"]["Processor Name"], "AMD Custom APU 0932")
        plistlib.dumps({"revcpuname": rep["CPU"]["Processor Name"]})
        self.assertTrue(any("unreadable characters" in n for n in notes))

    def test_a_scan_with_an_empty_graphics_list_stops_with_a_sentence_not_an_attribute_error(self):
        from p1401.report import normalize
        with self.assertRaises(RuntimeError) as c:
            normalize({"CPU": {"Manufacturer": "AMD"}, "Motherboard": {"Platform": "Desktop"}, "GPU": {}})
        self.assertIn("no graphics adapter", str(c.exception))

    def test_the_macos_range_of_a_card_is_said_in_words(self):
        from p1401 import unsupported
        self.assertEqual(unsupported._darwin_range({"Compatibility": ("25.99.99", "20.0.0")}), "works with macOS 11 to 26")
        self.assertEqual(unsupported._darwin_range({"Compatibility": (None, None)}), "no macOS version")

    def test_a_scan_with_no_network_section_is_planned_not_rejected(self):
        c = copy.deepcopy(census.BASELINE)
        del c["Network"]
        r = replay.replay(c, macos="24")
        self.assertTrue(r["ok"], r["crash"] or r["refused"])

    def test_a_mobile_processor_the_scan_calls_a_desktop_is_set_up_as_a_laptop(self):
        from p1401.report import normalize
        rep, notes = normalize({"CPU": {"Manufacturer": "Intel", "Processor Name": "12th Gen Intel(R) Core(TM) i5-12450H"},
                                "Motherboard": {"Name": "Mini PC", "Platform": "Desktop"}, "GPU": {"g": {"Manufacturer": "AMD", "Device ID": "1002-1234"}}})
        self.assertEqual(rep["Motherboard"]["Platform"], "Laptop")


class ScanKeepsWhatTheResolverReads(unittest.TestCase):
    def test_input_sound_storage_and_cpu_fields_the_engine_reads_survive_into_the_failed_build_log(self):
        from p1401.report import diagnostic_hardware
        d = diagnostic_hardware({"CPU": {"Manufacturer": "Intel", "SIMD Features": "SSE4.2, AVX2"}, "Input": {"x": {
            "Bus Type": "ACPI", "Device": "ELAN0412", "Device Type": "I2C HID Device"}}, "Sound": {"s": {
            "Bus Type": "INTELAUDIO", "Controller Device ID": "8086-7A50"}}, "Storage Controllers": {"n": {
            "Bus Type": "PCI", "Device ID": "144D-A80A", "Disk Drives": ["Samsung SSD 980"]}}})
        self.assertEqual(d["Input"][0]["Device"], "ELAN0412")
        self.assertEqual(d["Sound"][0]["Controller Device ID"], "8086-7A50")
        self.assertEqual(d["Storage Controllers"][0]["Disk Drive Count"], 1)
        self.assertNotIn("Samsung", str(d["Storage Controllers"]))     # the drive's model stays private
        self.assertEqual(d["CPU"]["SIMD Features"], "SSE4.2, AVX2")


if __name__ == "__main__":
    unittest.main()
