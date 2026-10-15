"""RDNA 4 (RX 9070 / Navi 48) display driver. The community AMDRadeonRDNA4 kext (BSD-3), built from a pinned commit and
self-hosted with its licence, is added to the EFI only for the two Navi 48 device IDs it handles. A user with an RX 9070
gets the driver (with an honest 'experimental, no acceleration' notice); no other card ever loads it; the exact bytes
are recorded in the mirror so the build fetches them verified."""
import sys
import unittest

from p1401 import amd_rdna4, engine, mirror


def amd(did, device_type="Discrete GPU"):
    return {"Manufacturer": "AMD", "Device ID": "1002-" + did, "Device Type": device_type}


class FakeKextMgr:
    def __init__(self):
        self.checked = []

    def check_kext(self, idx, mv):
        self.checked.append((idx, mv))
        return True


class FakeOcpe:
    def __init__(self):
        self.k = FakeKextMgr()


class Applies(unittest.TestCase):
    def test_navi48_ids_apply(self):
        for did in ("7550", "7551"):
            self.assertTrue(amd_rdna4.applies({"GPU": {"RX 9070": amd(did)}}), did)

    def test_other_amd_and_non_amd_do_not_apply(self):
        for did in ("73BF", "7480", "7590", "15D8"):   # native, RDNA3, Navi44, APU
            self.assertFalse(amd_rdna4.applies({"GPU": {"card": amd(did)}}), did)
        self.assertFalse(amd_rdna4.applies({"GPU": {"RTX": {"Device ID": "10DE-7550"}}}))  # same low 16 bits, NVIDIA
        self.assertFalse(amd_rdna4.applies({"GPU": {}}))


class MirrorRecorded(unittest.TestCase):
    def test_the_built_artifact_is_in_the_mirror_by_sha256_and_size(self):
        mirror.entries()
        e = mirror.entries().get(amd_rdna4.PACKAGE["url"])
        self.assertIsNotNone(e, "RDNA4 kext url not in mirror.json")
        self.assertEqual(e["sha256"], amd_rdna4.PACKAGE["sha256"])
        self.assertEqual(e["size"], amd_rdna4.PACKAGE["size"])

    def test_notice_is_honest_about_no_acceleration(self):
        self.assertIn("no graphics acceleration", amd_rdna4.NOTICE)
        self.assertIn("experimental", amd_rdna4.NOTICE)
        self.assertTrue(amd_rdna4.NOTICE.startswith("Graphics:"))


class RegisterAndApply(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if engine.UPSTREAM not in sys.path:
            sys.path.insert(0, engine.UPSTREAM)

    def test_register_adds_the_kext_with_a_direct_download_and_lilu_dependency(self):
        amd_rdna4.register()
        from Scripts.datasets import kext_data
        idx = kext_data.kext_index_by_name.get(amd_rdna4.KEXT)
        self.assertIsNotNone(idx)
        k = kext_data.kexts[idx]
        self.assertEqual(k.download_info, {"url": amd_rdna4.PACKAGE["url"], "sha256": amd_rdna4.PACKAGE["sha256"]})
        self.assertIn("Lilu", k.requires_kexts)
        self.assertFalse(k.github_repo)  # no GitHub release; fetched by direct url + sha256
        amd_rdna4.register()  # idempotent
        self.assertEqual(kext_data.kext_index_by_name.get(amd_rdna4.KEXT), idx)

    def test_apply_turns_the_kext_on_for_a_navi48_machine_and_adds_the_notice(self):
        amd_rdna4.register()
        from Scripts.datasets import kext_data
        ocpe, notices = FakeOcpe(), []
        amd_rdna4.apply_kexts(ocpe, {"GPU": {"RX 9070 XT": amd("7550")}}, "24.0.0", notices)
        self.assertEqual(ocpe.k.checked, [(kext_data.kext_index_by_name[amd_rdna4.KEXT], "24.0.0")])
        self.assertTrue(any("RX 9070" in n for n in notices), notices)

    def test_negative_control_no_navi48_means_no_kext_and_no_notice(self):
        amd_rdna4.register()
        ocpe, notices = FakeOcpe(), []
        amd_rdna4.apply_kexts(ocpe, {"GPU": {"RX 7900 XTX": amd("744C")}}, "24.0.0", notices)
        self.assertEqual(ocpe.k.checked, [])
        self.assertEqual(notices, [])

    def test_fail_safe_a_broken_engine_object_never_raises(self):
        notices = []
        amd_rdna4.apply_kexts(object(), {"GPU": {"RX 9070": amd("7550")}}, "24.0.0", notices)  # object() has no .k
        self.assertTrue(any("could not be applied" in n for n in notices), notices)


if __name__ == "__main__":
    unittest.main()
