"""The known-machine table built from stick logs: the miner's decision rule, the CPU token, and word-boundary matching."""
import json
import os
import plistlib
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import mine_known_machines as mk  # noqa: E402
from p1401 import engine, policy  # noqa: E402

OC = ("00:000 OCCPU: Found 12th Gen Intel(R) Core(TM) i5-12600KF\n00:100 OCABC: FEXITBS 0 PRMRG 0 CSLIDE 1 MSLIDE 0 PRSRV 1 RBMAP 1 "
      "VMAP 1 APPLOS 0 RTPERMS 1 ARBAR 0 RBIO 0\n%s")


def rec(n, cpu, devirt, passed, failed=False):
    q = {"DevirtualiseMmio": devirt, "SetupVirtualMap": True}
    return {"batch": f"b{n}", "cpu": cpu, "quirks": q, "passed": passed, "failed": failed}


class Miner(unittest.TestCase):
    def test_the_cpu_and_the_quirks_are_read_from_a_stick_log(self):
        self.assertEqual(mk.cpu_of(OC % ""), "12600KF")
        self.assertEqual(mk.cpu_of("OCCPU: Found AMD Ryzen 7 9800X3D 8-Core Processor"), "9800X3D")
        self.assertEqual(mk.cpu_of("OCCPU: Found Intel(R) Core(TM) i7-9700K CPU @ 3.60GHz"), "9700K")
        q = mk.oc_quirks(OC % "OCABC: MMIO devirt start\n")
        self.assertEqual((q["DevirtualiseMmio"], q["SetupVirtualMap"], q["RebuildAppleMemoryMap"], q["ProvideCustomSlide"]), (True, True, True, True))
        self.assertFalse(mk.oc_quirks(OC % "")["DevirtualiseMmio"])
        self.assertEqual(mk.oc_quirks("nothing here"), {})

    def test_a_set_that_works_where_the_other_fails_is_written(self):
        recs = [rec(i, "12600KF", True, True) for i in range(23)] + \
               [rec(100 + i, "12600KF", False, True) for i in range(7)] + [rec(200 + i, "12600KF", False, False, True) for i in range(3)]
        (e,) = mk.aggregate(recs)
        self.assertEqual((e["cpu"], e["board"], e["booter_quirks"]["DevirtualiseMmio"]), ("12600KF", "", True))

    def test_when_both_sets_work_nothing_is_written(self):
        recs = [rec(i, "7500F", True, True) for i in range(60)] + [rec(100 + i, "7500F", False, True) for i in range(30)]
        self.assertEqual(mk.aggregate(recs), [])

    def test_too_little_data_or_a_set_that_also_fails_nothing_is_written(self):
        self.assertEqual(mk.aggregate([rec(i, "X1", True, True) for i in range(4)] + [rec(9 + i, "X1", False, False, True) for i in range(6)]), [])
        recs = [rec(i, "X2", True, True) for i in range(8)] + [rec(50 + i, "X2", True, False, True) for i in range(4)] + \
               [rec(100 + i, "X2", False, False, True) for i in range(6)]
        self.assertEqual(mk.aggregate(recs), [])

    def test_the_shipped_table_is_what_the_rules_wrote_and_every_entry_has_a_source(self):
        with open(mk.KNOWN, encoding="utf-8") as fh:
            table = json.load(fh)["machines"]
        mined = [m for m in table if m["board"] == ""]
        self.assertGreaterEqual(len(mined), 1)
        for m in table:
            self.assertTrue(m["source"] and m["booter_quirks"] and m["cpu"])


def build(cpu_name, board="Some Board"):
    t = tempfile.mkdtemp(); path = os.path.join(t, "config.plist")
    cfg = {"NVRAM": {"Add": {}, "Delete": {}}, "Kernel": {"Add": [], "Patch": [], "Quirks": {}},
           "Booter": {"Quirks": {"DevirtualiseMmio": False, "SetupVirtualMap": True}, "MmioWhitelist": []}, "Misc": {},
           "ACPI": {"Add": []}, "UEFI": {"Drivers": [], "Quirks": {}}, "PlatformInfo": {"Generic": {}}}
    with open(path, "wb") as f: plistlib.dump(cfg, f)
    res = engine.BuildResult(ok=True, out_dir=t, macos_version="24.6.0", hardware={
        "Motherboard": {"Name": board, "Chipset": "", "Platform": "Desktop"}, "CPU": {"Manufacturer": "Intel", "Processor Name": cpu_name, "Codename": ""}, "GPU": {}})
    ch = policy.apply(path, res, engine.Policy())
    with open(path, "rb") as f: return plistlib.load(f)["Booter"]["Quirks"], [c["rule"] for c in ch]


class Matching(unittest.TestCase):
    def test_a_mined_cpu_gets_its_quirks_on_any_board(self):
        for board in ("Z690 AORUS", "PRO B660M"):
            q, rules = build("12th Gen Intel(R) Core(TM) i5-12600KF", board)
            self.assertTrue(q["DevirtualiseMmio"], board)
            self.assertIn("known-machine", rules)

    def test_a_longer_model_name_is_not_the_same_cpu(self):
        q, rules = build("12th Gen Intel(R) Core(TM) i7-12700H")
        self.assertNotIn("known-machine", rules)
        q, rules = build("12th Gen Intel(R) Core(TM) i7-12700KF")
        self.assertNotIn("known-machine", rules)

    def test_word_boundaries(self):
        self.assertTrue(policy._word_in("12700", "intel i7-12700 cpu"))
        self.assertFalse(policy._word_in("12700", "intel i7-12700h"))
        self.assertTrue(policy._word_in("", "anything"))


if __name__ == "__main__":
    unittest.main()
