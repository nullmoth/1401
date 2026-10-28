"""Network-adapter support: the classifier, and MediaTek Wi-Fi/Bluetooth registration.

The classifier must tell a card that works in the installer (native, or Ethernet) from one that does not
(MediaTek's experimental driver, or none at all), because that decides whether the user needs an offline
installer. The negative controls are a MediaTek-only machine (must be flagged offline, not treated as native) and
a non-MediaTek machine (must get no MediaTek kext).
"""
import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from p1401 import netsupport

NATIVE = {"8086-2723"}                                   # Intel AX200
EXPERIMENTAL = set(netsupport.MEDIATEK_WIFI_KEXT_IDS)    # MediaTek IDs the SimpleMtkWlan kext matches
UNSUPPORTED = set(netsupport.MEDIATEK_WIFI_IDS) - EXPERIMENTAL  # MediaTek Wi-Fi with no driver (RZ616, MT7925)
BT = {"8087-0029"}                                       # Intel BT
ETH = {"10EC-8168"}                                      # Realtek RTL8111


def _report(net=None, bt=None):
    return {"Network": {n: {"Device ID": d} for n, d in (net or {}).items()},
            "Bluetooth": {n: {"Device ID": d} for n, d in (bt or {}).items()}}


def _classify(net=None, bt=None):
    return netsupport.network_support(_report(net, bt), NATIVE, EXPERIMENTAL, BT, ETH, UNSUPPORTED)


class Classifier(unittest.TestCase):
    def test_native_wifi_is_installer_online(self):
        s = _classify(net={"wifi": "8086-2723"})
        self.assertEqual(s["wifi"], "native")
        self.assertFalse(s["offline_recommended"])
        self.assertEqual(s["notice"], "")

    def test_ethernet_is_installer_online(self):
        s = _classify(net={"eth": "10EC-8168"})
        self.assertTrue(s["ethernet"])
        self.assertFalse(s["offline_recommended"])

    def test_mediatek_supported_is_experimental_and_offline(self):
        # NEGATIVE CONTROL: if MediaTek were treated as native this would say the installer has internet.
        s = _classify(net={"wifi": "14C3-7922"})  # MT7922, matched by the kext
        self.assertEqual(s["wifi"], "experimental")
        self.assertTrue(s["offline_recommended"])
        self.assertIn("offline installer", s["notice"])

    def test_mediatek_unsupported_card_is_offline(self):
        # RZ616 (0616) has no driver: present, but no macOS Wi-Fi, so the installer is offline-only.
        s = _classify(net={"wifi": "14C3-0616"})
        self.assertEqual(s["wifi"], "unsupported")
        self.assertTrue(s["offline_recommended"])
        self.assertIn("offline installer", s["notice"])

    def test_no_adapter_is_flagged_with_a_reason(self):
        s = _classify()
        self.assertEqual(s["wifi"], "none")
        self.assertTrue(s["offline_recommended"])
        self.assertIn("No network adapter", s["notice"])

    def test_mediatek_with_ethernet_is_online(self):
        s = _classify(net={"wifi": "14C3-0616", "eth": "10EC-8168"})
        self.assertFalse(s["offline_recommended"])
        self.assertEqual(s["notice"], "")


@unittest.skipUnless(os.path.isdir(os.path.join(REPO, "upstream", "OpCore-Simplify")),
                     "engine datasets not present")
class MediaTekKexts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        up = os.path.join(REPO, "upstream", "OpCore-Simplify")
        if up not in sys.path:
            sys.path.insert(0, up)
        netsupport.register()
        netsupport.register()  # twice: must stay idempotent

    def test_register_pins_both_kext_assets(self):
        from Scripts.datasets import kext_data, pci_data
        # The pins the build fetches: each kext's exact URL and SHA-256.
        bt = kext_data.kexts[kext_data.kext_index_by_name[netsupport.MTK_BT_KEXT]].download_info
        self.assertEqual(bt.get("url"), netsupport.MTK_BT_URL)
        self.assertEqual(bt.get("sha256"), netsupport.MTK_BT_SHA256)
        wlan = kext_data.kexts[kext_data.kext_index_by_name[netsupport.MTK_WIFI_KEXT]].download_info
        self.assertEqual(wlan.get("url"), netsupport.MTK_WIFI_URL)
        self.assertEqual(wlan.get("sha256"), netsupport.MTK_WIFI_SHA256)
        self.assertEqual([k.name for k in kext_data.kexts].count(netsupport.MTK_WIFI_KEXT), 1)
        self.assertIn("14C3-7922", pci_data.WirelessCardIDs)

    def test_apply_enables_wlan_for_a_matched_card_when_experimental_drivers_are_on(self):
        from Scripts.datasets import kext_data
        km = type("M", (), {"checked": None, "check_kext": lambda s, i, mv, f=False: s.checked.append(i)})()
        km.checked = []
        o = type("O", (), {"k": km})()
        notices = []
        netsupport.apply_kexts(o, _report(net={"w": "14C3-7922"}, bt={"b": "0E8D-0616"}), "24.0.0", notices,
                               experimental=True)
        self.assertIn(kext_data.kext_index_by_name[netsupport.MTK_WIFI_KEXT], km.checked)
        self.assertIn(kext_data.kext_index_by_name[netsupport.MTK_BT_KEXT], km.checked)

    def test_by_default_a_matched_card_gets_bluetooth_but_not_the_wlan_kext(self):
        from Scripts.datasets import kext_data
        km = type("M", (), {"checked": None, "check_kext": lambda s, i, mv, f=False: s.checked.append(i)})()
        km.checked = []
        o = type("O", (), {"k": km})()
        notices = []
        netsupport.apply_kexts(o, _report(net={"w": "14C3-7922"}, bt={"b": "0E8D-0616"}), "24.0.0", notices)
        self.assertNotIn(kext_data.kext_index_by_name[netsupport.MTK_WIFI_KEXT], km.checked)
        self.assertIn(kext_data.kext_index_by_name[netsupport.MTK_BT_KEXT], km.checked)
        self.assertTrue(any("Include experimental drivers" in n for n in notices), notices)

    def test_apply_does_not_enable_wlan_for_an_unsupported_card(self):
        # NEGATIVE CONTROL: RZ616 (0616) is a MediaTek Wi-Fi card the kext does NOT match - no kext, only a notice.
        from Scripts.datasets import kext_data
        km = type("M", (), {"checked": None, "check_kext": lambda s, i, mv, f=False: s.checked.append(i)})()
        km.checked = []
        o = type("O", (), {"k": km})()
        notices = []
        netsupport.apply_kexts(o, _report(net={"w": "14C3-0616"}), "24.0.0", notices)
        self.assertNotIn(kext_data.kext_index_by_name[netsupport.MTK_WIFI_KEXT], km.checked)
        self.assertTrue(any("MediaTek Wi-Fi" in n for n in notices))

    def test_common_bt_rebrands_enable_the_bt_kext(self):
        # 13D3-3585 is the most common MediaTek BT id in the field; it and the other re-brands below are in
        # SimpleMtkBtFw's Info.plist, so the kext must now be enabled for them.
        from Scripts.datasets import kext_data
        bt_idx = kext_data.kext_index_by_name[netsupport.MTK_BT_KEXT]
        for did in ("13D3-3585", "0489-E0F6", "13D3-3568", "13D3-3567", "13D3-3614", "04CA-3802"):
            km = type("M", (), {"checked": None, "check_kext": lambda s, i, mv, f=False: s.checked.append(i)})()
            km.checked = []
            o = type("O", (), {"k": km})()
            netsupport.apply_kexts(o, _report(bt={"b": did}), "24.0.0", [])
            self.assertIn(bt_idx, km.checked, f"{did} should enable the MediaTek BT kext")

    def test_unsupported_bt_rebrand_is_not_enabled(self):
        # NEGATIVE CONTROL: a MediaTek-named re-brand that SimpleMtkBtFw does NOT match (not in its Info.plist)
        # must not turn the kext on, or the build would promise Bluetooth the driver cannot bring up.
        from Scripts.datasets import kext_data
        bt_idx = kext_data.kext_index_by_name[netsupport.MTK_BT_KEXT]
        km = type("M", (), {"checked": None, "check_kext": lambda s, i, mv, f=False: s.checked.append(i)})()
        km.checked = []
        o = type("O", (), {"k": km})()
        netsupport.apply_kexts(o, _report(bt={"b": "13D3-3596"}), "24.0.0", [])
        self.assertNotIn(bt_idx, km.checked)

    def test_no_mediatek_device_adds_no_mediatek_kext(self):
        # NEGATIVE CONTROL.
        from Scripts.datasets import kext_data
        km = type("M", (), {"checked": None, "check_kext": lambda s, i, mv, f=False: s.checked.append(i)})()
        km.checked = []
        o = type("O", (), {"k": km})()
        netsupport.apply_kexts(o, _report(net={"w": "8086-2723"}), "24.0.0", [])
        self.assertNotIn(kext_data.kext_index_by_name[netsupport.MTK_BT_KEXT], km.checked)
        self.assertNotIn(kext_data.kext_index_by_name[netsupport.MTK_WIFI_KEXT], km.checked)


class BtMissingIds(unittest.TestCase):
    """#336: an RZ616 (0e8d:0616) got SimpleMtkBtFw, which does not list that ID, and Bluetooth stayed off."""

    def _efi(self, d, extra=None):
        import plistlib
        k = os.path.join(d, "EFI", "OC", "Kexts", "SimpleMtkBtFw.kext", "Contents")
        os.makedirs(k)
        pers = {"SimpleMtkBtFw_MT7922A_35f5_7922": {"IOClass": "SimpleMtkBtFw", "idVendor": 0x35F5, "idProduct": 0x7922},
                "SimpleMtkBtFw_MT7921_0e8d_0608": {"IOClass": "SimpleMtkBtFw", "idVendor": 0x0E8D, "idProduct": 0x0608}}
        pers.update(extra or {})
        with open(os.path.join(k, "Info.plist"), "wb") as fh:
            plistlib.dump({"IOKitPersonalities": pers}, fh)
        return os.path.join(k, "Info.plist")

    def _load(self, p):
        import plistlib
        with open(p, "rb") as fh:
            return plistlib.load(fh)["IOKitPersonalities"]

    def test_an_unlisted_rz616_gets_a_copy_of_the_mt7922_entry(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._efi(d); notes = []
            added = netsupport.add_missing_bt_ids(d, _report(bt={"b": "0E8D-0616"}), notes)
            self.assertEqual(added, ["0E8D-0616"], notes)
            e = self._load(p)["SimpleMtkBtFw_MT7922A_0e8d_0616"]
            self.assertEqual((e["idVendor"], e["idProduct"], e["IOClass"]), (0x0E8D, 0x0616, "SimpleMtkBtFw"))

    def test_an_id_already_listed_is_left_alone(self):
        # NEGATIVE CONTROL: the kext already matches 0e8d:0608, so nothing is written.
        with tempfile.TemporaryDirectory() as d:
            p = self._efi(d); before = self._load(p)
            self.assertEqual(netsupport.add_missing_bt_ids(d, _report(bt={"b": "0E8D-0608"}), []), [])
            self.assertEqual(self._load(p), before)

    def test_no_kext_in_the_efi_changes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(netsupport.add_missing_bt_ids(d, _report(bt={"b": "0E8D-0616"}), []), [])


@unittest.skipUnless(os.path.isdir(os.path.join(REPO, "upstream", "OpCore-Simplify")),
                     "engine datasets not present")
class BtHashVerified(unittest.TestCase):
    """The pinned MediaTek BT asset is fetched only when its SHA-256 matches: a good hash passes, a tampered one is
    refused (the build then fails rather than shipping unknown bytes). Exercises the engine's real download path."""

    def _fetcher(self, data):
        up = os.path.join(REPO, "upstream", "OpCore-Simplify")
        if up not in sys.path:
            sys.path.insert(0, up)
        from Scripts import resource_fetcher
        from p1401 import mirror
        rf = resource_fetcher.ResourceFetcher()
        rf._make_request = lambda url, timeout=10: mirror.Response(data, url)
        return rf

    def test_good_hash_passes_tampered_refused(self):
        import hashlib, io, zipfile
        # A real (minimal) kext archive, so the download path's ZIP validation is satisfied and only the hash decides.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("SimpleMtkBtFw-x/SimpleMtkBtFw.kext/Contents/Info.plist", "<plist></plist>")
        data = buf.getvalue()
        good = hashlib.sha256(data).hexdigest()
        rf = self._fetcher(data)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "SimpleMtkBtFw.zip")
            self.assertTrue(rf.download_and_save_file("https://example/SimpleMtkBtFw.zip", p, good))
            # NEGATIVE CONTROL: the same bytes under a wrong (tampered) hash must be refused.
            self.assertFalse(rf.download_and_save_file("https://example/SimpleMtkBtFw.zip", p, "0" * 64))

    def test_pinned_bt_sha_matches_the_live_asset(self):
        # The pin recorded in netsupport must be the real 1.0.0 RELEASE asset's hash (verified against the live release).
        self.assertEqual(netsupport.MTK_BT_SHA256,
                         "b6afbe453db5827e7e2c8cdd045374f4fa6760f63e6ae26a3f322aa75dc84954")

    def test_pinned_wlan_pin_is_the_built_artifact(self):
        # Guards the Wi-Fi pin against accidental edits: the hash/size/url of the kext 1401 built and hosts.
        self.assertEqual(netsupport.MTK_WIFI_SHA256,
                         "da0ef98222f7d29a6e3cdde91185348b7fe8abdf5c324c5e2349295996ee18f9")
        self.assertEqual(netsupport.MTK_WIFI_SIZE, 1822103)
        self.assertEqual(netsupport.MTK_WIFI_URL, "https://nullmothsystems.com/mirror/" + netsupport.MTK_WIFI_SHA256)
        # The mirror manifest must carry the same pin, or a blocked-network build could not fetch it.
        from p1401 import mirror
        self.assertIn(netsupport.MTK_WIFI_URL, mirror.entries())
        self.assertEqual(mirror.entries()[netsupport.MTK_WIFI_URL]["sha256"], netsupport.MTK_WIFI_SHA256)


class OfflineMarker(unittest.TestCase):
    """The build leaves a marker so the writer defaults to the offline image path on a PC with no installer network."""

    def test_offline_build_makes_the_writer_require_a_local_image(self):
        with tempfile.TemporaryDirectory() as d:
            netsupport.write_marker(d, {"offline_recommended": True, "wifi": "none", "ethernet": False})
            self.assertTrue(netsupport.needs_local_image(d))

    def test_online_build_does_not_block_the_writer(self):
        # NEGATIVE CONTROL: a machine with a supported adapter must not be forced onto the offline path.
        with tempfile.TemporaryDirectory() as d:
            netsupport.write_marker(d, {"offline_recommended": False, "wifi": "native", "ethernet": True})
            self.assertFalse(netsupport.needs_local_image(d))

    def test_missing_marker_does_not_block(self):
        # An older build (no marker) must keep the previous behaviour, not stop the writer.
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(netsupport.needs_local_image(d))


if __name__ == "__main__":
    unittest.main()
