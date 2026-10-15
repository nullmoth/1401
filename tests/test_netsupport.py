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

NATIVE = {"8086-2723"}          # Intel AX200
EXPERIMENTAL = set(netsupport.MEDIATEK_WIFI_IDS)
BT = {"8087-0029"}              # Intel BT
ETH = {"10EC-8168"}             # Realtek RTL8111


def _report(net=None, bt=None):
    return {"Network": {n: {"Device ID": d} for n, d in (net or {}).items()},
            "Bluetooth": {n: {"Device ID": d} for n, d in (bt or {}).items()}}


def _classify(net=None, bt=None):
    return netsupport.network_support(_report(net, bt), NATIVE, EXPERIMENTAL, BT, ETH)


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

    def test_mediatek_only_is_experimental_and_offline(self):
        # NEGATIVE CONTROL: if MediaTek were treated as native this would say the installer has internet.
        s = _classify(net={"wifi": "14C3-0616"})  # MT7922
        self.assertEqual(s["wifi"], "experimental")
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

    def test_register_adds_kexts_and_ids_once(self):
        from Scripts.datasets import kext_data, pci_data
        self.assertIsNotNone(kext_data.kext_index_by_name.get(netsupport.MTK_WIFI_KEXT))
        self.assertIsNotNone(kext_data.kext_index_by_name.get(netsupport.MTK_BT_KEXT))
        names = [k.name for k in kext_data.kexts]
        self.assertEqual(names.count(netsupport.MTK_WIFI_KEXT), 1)
        self.assertIn("14C3-0616", pci_data.WirelessCardIDs)

    def test_apply_enables_kexts_for_a_mediatek_machine(self):
        from Scripts.datasets import kext_data
        km = type("M", (), {"checked": None, "check_kext": lambda s, i, mv, f=False: s.checked.append(i)})()
        km.checked = []
        o = type("O", (), {"k": km})()
        netsupport.apply_kexts(o, _report(net={"w": "14C3-0616"}, bt={"b": "0E8D-0616"}), "24.0.0", [])
        want = {kext_data.kext_index_by_name[netsupport.MTK_WIFI_KEXT],
                kext_data.kext_index_by_name[netsupport.MTK_BT_KEXT]}
        self.assertTrue(want.issubset(set(km.checked)))

    def test_no_mediatek_device_adds_no_mediatek_kext(self):
        # NEGATIVE CONTROL.
        from Scripts.datasets import kext_data
        km = type("M", (), {"checked": None, "check_kext": lambda s, i, mv, f=False: s.checked.append(i)})()
        km.checked = []
        o = type("O", (), {"k": km})()
        netsupport.apply_kexts(o, _report(net={"w": "8086-2723"}), "24.0.0", [])
        want = {kext_data.kext_index_by_name[netsupport.MTK_WIFI_KEXT],
                kext_data.kext_index_by_name[netsupport.MTK_BT_KEXT]}
        self.assertFalse(set(km.checked) & want)


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
