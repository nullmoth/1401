"""Firmware without a memory attributes table (OpenCore: "MAT support is 0") gets the no-MAT booter quirks."""
import unittest
from types import SimpleNamespace

from p1401 import bootfix

Q0 = {"DevirtualiseMmio": False, "SetupVirtualMap": False, "RebuildAppleMemoryMap": True,
      "EnableWriteUnprotector": False, "SyncRuntimePermissions": True}


def run(logs, cpu="Intel", stopped="", quirks=None):
    cfg = {"Booter": {"Quirks": dict(quirks or Q0)}}
    changes = []
    bootfix.apply(cfg, SimpleNamespace(hardware={"CPU": {"Manufacturer": cpu}}), logs, lambda *a: changes.append(a), stopped)
    return cfg["Booter"]["Quirks"], [c[0] for c in changes]


def boot(mat, stamp="2026-10-24T10:00", entry=4):
    return (f"OCABC: MAT support is {mat}\n"
            "OCABC: ALRBL 1 RTDFRG 1 DEVMMIO 0 NOSU 0 NOVRWR 0 NOSB 0 FBSIG 0 NOHBMAP 0 SMSLIDE 1 WRUNPROT 0 CLRTS 0\n"
            f"OCB: Should boot from 1. 1401 (T:{entry}|F:1|G:0|E:1|DEF:0)\nAAPL: #[EB|LOG:DT] {stamp}\nAAPL: #[EB|LOG:EXITBS:START] {stamp}\n")


class NoMatFirmware(unittest.TestCase):
    def test_mat_zero_switches_to_the_write_unprotector_pairing(self):
        q, ch = run([boot(0)])
        self.assertEqual(ch, ["bootlog-firmware-nomat"])
        self.assertTrue(q["EnableWriteUnprotector"])
        self.assertFalse(q["RebuildAppleMemoryMap"])
        self.assertFalse(q["SyncRuntimePermissions"])
        self.assertEqual(q["DevirtualiseMmio"], Q0["DevirtualiseMmio"])

    def test_mat_one_changes_nothing(self):
        q, ch = run([boot(1)])
        self.assertEqual((q, ch), (Q0, []))

    def test_one_log_with_mat_zero_wins_over_one_with_mat_one(self):
        _, ch = run([boot(1), boot(0, "2026-10-24T11:00", entry=2)])  # one installer start: not frozen
        self.assertEqual(ch, ["bootlog-firmware-nomat"])

    def test_a_config_that_already_has_the_pairing_is_left_alone(self):
        done = {**Q0, "RebuildAppleMemoryMap": False, "EnableWriteUnprotector": True, "SyncRuntimePermissions": False}
        q, ch = run([boot(0)], quirks=done)
        self.assertEqual((q, ch), (done, []))

    def test_a_frozen_boot_is_left_to_the_hand_off_ladder(self):
        _, ch = run([boot(0)], stopped="the screen froze at EXITBS:START")
        self.assertEqual(ch, ["bootlog-handoff-nomat"])

    def test_amd_gets_the_same_three_quirks_when_not_frozen(self):
        q, ch = run([boot(0)], cpu="AMD")
        self.assertEqual(ch, ["bootlog-firmware-nomat"])
        self.assertEqual(q["SetupVirtualMap"], Q0["SetupVirtualMap"])


if __name__ == "__main__":
    unittest.main()
