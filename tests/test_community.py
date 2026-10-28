"""Community drivers (p1401/community.py): each is added only for hardware its Info.plist matches, only for a macOS its
author built it for, and - when it can cost the network, power or boot - only when the user opted in. Every pinned file
is licensed for 1401 and recorded in the mirror rules (10-22)."""
import copy
import hashlib
import io
import os
import plistlib
import sys
import tempfile
import types
import unittest
import zipfile

from p1401 import community, engine, licenses, netsupport

TAHOE, SEQUOIA = "25.0.0", "24.0.0"


def machine(**sections):
    """A scan report with the given "Device ID"s per section, e.g. Network=["10EC-B852"]."""
    report = {"Motherboard": {"Name": "SOMEVENDOR X1", "Platform": "Laptop"}, "CPU": {"Codename": "Raptor Lake"}}
    for section, ids in sections.items():
        report[section.replace("_", " ")] = {f"dev{i}": {"Device ID": d} for i, d in enumerate(ids)}
    return report


def names(added):
    return sorted(d["name"] for d in added)


class Choice(unittest.TestCase):
    def test_a_realtek_wifi6_card_is_named_but_not_added_without_the_opt_in(self):
        add, said = community.chosen(machine(Network=["10EC-B852"]), TAHOE, experimental=False)
        self.assertEqual(add, [])
        self.assertTrue(any("AirportRTW" in s and "NOT in this build" in s for s in said), said)

    def test_the_opt_in_adds_it_with_the_build_for_that_macos(self):
        add, _ = community.chosen(machine(Network=["10EC-B852"]), SEQUOIA, experimental=True)
        self.assertEqual(names(add), ["AirportRTW"])
        self.assertIn("Sequoia", community.build_for(add[0], SEQUOIA)[0])
        self.assertIn("Tahoe", community.build_for(add[0], TAHOE)[0])

    def test_a_card_the_engine_already_drives_is_left_to_the_engine(self):
        # 10EC-B822 is in the engine's rtw88 list; AirportRTW also matches it, and must not replace a working driver
        add, said = community.chosen(machine(Network=["10EC-B822"]), TAHOE, experimental=True)
        self.assertEqual(add, [])
        self.assertEqual(said, [])

    def test_bluetooth_firmware_loaders_need_no_opt_in(self):
        add, _ = community.chosen(machine(Bluetooth=["0489-E0FC"]), TAHOE, experimental=False)
        self.assertEqual(names(add), ["BluetoothWCN7850"])

    def test_a_driver_with_no_build_for_this_macos_is_not_added_and_says_so(self):
        report = machine()
        report["CPU"]["Codename"] = "Arrow Lake-HX"
        add, said = community.chosen(report, SEQUOIA, experimental=True)
        self.assertEqual(add, [])
        self.assertTrue(any("LegionCpuPower" in s and "no build for this macOS" in s for s in said), said)
        add, _ = community.chosen(report, TAHOE, experimental=True)
        self.assertEqual(names(add), ["LegionCpuPower"])

    def test_the_arrow_lake_i2c_ids_only_ride_along_with_voodooi2c(self):
        report = machine(System_Devices=["8086-7F4C"])
        self.assertEqual(community.chosen(report, TAHOE, False)[0], [])
        self.assertEqual(names(community.chosen(report, TAHOE, False, engine_kexts={"VoodooI2C"})[0]),
                         ["LegionI2CArrowLake"])

    def test_the_lenovo_fix_needs_a_lenovo_board(self):
        report = machine()
        self.assertEqual(community.chosen(report, TAHOE, True)[0], [])
        report["Motherboard"]["Name"] = "LENOVO 83F0"
        self.assertEqual(names(community.chosen(report, TAHOE, True)[0]), ["LegionCbmrFix.efi"])

    def test_the_amd_usb_fixes_come_together_for_single_vector_controllers(self):
        add, _ = community.chosen(machine(USB_Controllers=["1022-161D"]), SEQUOIA, experimental=True)
        self.assertEqual(names(add), ["KernReserveLow.efi", "XhciNudge"])
        self.assertEqual(community.chosen(machine(USB_Controllers=["8086-A0ED"]), SEQUOIA, True)[0], [])

    def test_strix_point_usb_gets_the_nudge_but_not_the_ram_reserve(self):
        add, _ = community.chosen(machine(USB_Controllers=["1022-151E"]), TAHOE, experimental=True)
        self.assertEqual(names(add), ["XhciNudge"])
        self.assertEqual(community.chosen(machine(USB_Controllers=["1022-151E"]), TAHOE, False)[0], [])


class Pins(unittest.TestCase):
    def test_every_pinned_file_is_licensed_for_1401_and_admitted(self):
        for d in community.DRIVERS:
            for url, size, sha in d["builds"].values():
                kind, project, _ = licenses.classify(url)
                key, entry = licenses.project(project or "")
                self.assertIsNotNone(entry, url)
                self.assertIn(entry["class"], licenses.ADMITTED, url)
                self.assertTrue(licenses.hostable(url)[0], url)
                self.assertRegex(sha, r"^[0-9a-f]{64}$")
                self.assertGreater(size, 0)

    def test_builds_are_only_for_the_macos_versions_1401_installs(self):
        for d in community.DRIVERS:
            self.assertTrue(set(d["builds"]) <= {community.SEQUOIA, community.TAHOE}, d["name"])

    def test_the_mt7925_wifi_kext_that_auto_joins_open_networks_is_not_here(self):
        # watchthelight MtkWlan 0.11.3 ships MtkAutoOpenSsids=[Boingo...] in its Info.plist: it would join open
        # hotspots by itself. Kept out until that default is gone.
        self.assertFalse(any("mt7925-hackintosh-wifi" in u for d in community.DRIVERS for u, _, _ in d["builds"].values()))


class EngineHooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine._load_engine()
        from Scripts.datasets import kext_data
        cls.kd = kext_data
        community.register()
        netsupport.register()

    def ocpe(self, checked=()):
        o = types.SimpleNamespace(k=types.SimpleNamespace(kexts=copy.deepcopy(self.kd.kexts), checked=[]))
        for k in o.k.kexts:
            k.checked = k.name in checked
        o.k.check_kext = lambda idx, mv: (o.k.checked.append(o.k.kexts[idx].name), setattr(o.k.kexts[idx], "checked", True))
        return o

    def test_register_is_idempotent_and_skips_uefi_drivers(self):
        before = len(self.kd.kexts)
        community.register()
        self.assertEqual(len(self.kd.kexts), before)
        self.assertNotIn("KernReserveLow.efi", self.kd.kext_index_by_name)

    def test_apply_pins_the_build_for_this_macos(self):
        o, notices = self.ocpe(), []
        community.apply_kexts(o, machine(Network=["10EC-B852"]), SEQUOIA, notices, experimental=True)
        self.assertEqual(o.k.checked, ["AirportRTW"])
        k = o.k.kexts[self.kd.kext_index_by_name["AirportRTW"]]
        self.assertIn("Sequoia", k.download_info["url"])

    def test_on_tahoe_mediatek_gets_the_native_menu_driver_and_not_the_old_one(self):
        o, notices = self.ocpe(), []
        report = machine(Network=["14C3-0616"])
        netsupport.apply_kexts(o, report, TAHOE, notices, experimental=True)
        community.apply_kexts(o, report, TAHOE, notices, experimental=True)
        self.assertEqual(o.k.checked, ["AirportMtkWlan"])
        self.assertFalse(any("no macOS driver" in n for n in notices), notices)

    def test_on_sequoia_mediatek_keeps_the_driver_it_had(self):
        o, notices = self.ocpe(), []
        report = machine(Network=["14C3-7922"])
        netsupport.apply_kexts(o, report, SEQUOIA, notices, experimental=True)
        community.apply_kexts(o, report, SEQUOIA, notices, experimental=True)
        self.assertEqual(o.k.checked, [netsupport.MTK_WIFI_KEXT])


class UefiDrivers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        oc = os.path.join(self.tmp.name, "EFI", "OC")
        os.makedirs(os.path.join(oc, "Drivers"))
        self.config = os.path.join(oc, "config.plist")
        with open(self.config, "wb") as fh:
            plistlib.dump({"UEFI": {"Drivers": [{"Path": "OpenRuntime.efi", "Enabled": True}]}}, fh)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("KernReserveLow.efi", b"MZ fake driver")
        self.zip = buf.getvalue()
        self.saved = copy.deepcopy(community.DRIVERS)
        d = next(d for d in community.DRIVERS if d["name"] == "KernReserveLow.efi")
        d["builds"] = {community.SEQUOIA: ("https://github.com/MonkaKokosowa/KernReserveLow/releases/download/1.0/x.zip",
                                           len(self.zip), hashlib.sha256(self.zip).hexdigest())}

    def tearDown(self):
        community.DRIVERS[:] = self.saved
        self.tmp.cleanup()

    def drivers(self):
        with open(self.config, "rb") as fh:
            return [d["Path"] for d in plistlib.load(fh)["UEFI"]["Drivers"]]

    def test_a_verified_driver_is_written_and_enabled(self):
        notices = []
        got = community.apply_efi_drivers(self.config, machine(USB_Controllers=["1022-161E"]), SEQUOIA, notices,
                                          lambda url: self.zip, experimental=True)
        self.assertEqual(got, ["KernReserveLow.efi"])
        self.assertEqual(self.drivers(), ["OpenRuntime.efi", "KernReserveLow.efi"])
        with open(os.path.join(os.path.dirname(self.config), "Drivers", "KernReserveLow.efi"), "rb") as fh:
            self.assertEqual(fh.read(), b"MZ fake driver")

    def entries(self):
        with open(self.config, "rb") as fh:
            return {d["Path"]: d for d in plistlib.load(fh)["UEFI"]["Drivers"]}

    def test_an_added_driver_carries_hideverbose_when_the_config_does(self):
        with open(self.config, "wb") as fh:
            plistlib.dump({"UEFI": {"Drivers": [{"Path": "OpenRuntime.efi", "Enabled": True, "HideVerbose": False}]}}, fh)
        community.apply_efi_drivers(self.config, machine(USB_Controllers=["1022-161E"]), SEQUOIA, [],
                                    lambda url: self.zip, experimental=True)
        self.assertIs(self.entries()["KernReserveLow.efi"].get("HideVerbose"), False)

    def test_an_added_driver_has_no_hideverbose_on_an_older_config(self):
        community.apply_efi_drivers(self.config, machine(USB_Controllers=["1022-161E"]), SEQUOIA, [],
                                    lambda url: self.zip, experimental=True)
        self.assertNotIn("HideVerbose", self.entries()["KernReserveLow.efi"])

    def test_bytes_that_do_not_match_the_pin_are_never_written(self):
        notices = []
        got = community.apply_efi_drivers(self.config, machine(USB_Controllers=["1022-161E"]), SEQUOIA, notices,
                                          lambda url: self.zip + b"x", experimental=True)
        self.assertEqual(got, [])
        self.assertEqual(self.drivers(), ["OpenRuntime.efi"])
        self.assertTrue(any("did not match its pinned SHA-256" in n for n in notices), notices)

    def test_without_the_opt_in_nothing_is_fetched(self):
        def refuse(url):
            raise AssertionError("fetched without the opt-in")
        self.assertEqual(community.apply_efi_drivers(self.config, machine(USB_Controllers=["1022-161E"]), SEQUOIA,
                                                     [], refuse, experimental=False), [])


if __name__ == "__main__":
    unittest.main()
