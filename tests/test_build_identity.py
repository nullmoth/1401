"""A rebuild for the same PC keeps its Mac's serial number, board serial, UUID and ROM.

Bug report 10-14: recovering from a failed driver update meant rebuilding the EFI on Windows, and every rebuild gave
the Mac a new serial number (a new Mac to iCloud and iMessage)."""
import inspect
import os
import plistlib
import tempfile
import unittest

from p1401 import engine

HW = {"Motherboard": {"Name": "B660M DS3H"}, "CPU": {"Processor Name": "12th Gen Intel(R) Core(TM) i7-12700F"}}
OLD = {"SystemSerialNumber": "C02OLDSERIAL", "MLB": "C02OLDBOARDSERIAL", "SystemUUID": "11111111-2222-3333-4444-555555555555",
       "ROM": b"\x01\x02\x03\x04\x05\x06", "SystemProductName": "MacPro7,1"}
NEW = {"SystemSerialNumber": "C02NEWSERIAL", "MLB": "C02NEWBOARDSERIAL", "SystemUUID": "99999999-8888-7777-6666-555555555555",
       "ROM": b"\x0a\x0b\x0c\x0d\x0e\x0f", "SystemProductName": "MacPro7,1"}


class H:
    def __init__(self):
        self.notices = []


def write_build(out, generic, key=None):
    os.makedirs(os.path.join(out, "EFI", "OC"), exist_ok=True)
    with open(os.path.join(out, "EFI", "OC", "config.plist"), "wb") as f:
        plistlib.dump({"PlatformInfo": {"Generic": dict(generic)}}, f)
    open(os.path.join(out, engine.MARKER), "w").write("built by 1401\n")
    if key is not None:
        open(os.path.join(out, engine.IDENTITY_FOR), "w").write(key + "\n")


def generic_of(out):
    with open(os.path.join(out, "EFI", "OC", "config.plist"), "rb") as f:
        return plistlib.load(f)["PlatformInfo"]["Generic"]


class KeepIdentity(unittest.TestCase):
    def rebuild(self, old, new, key_on_disk=None, hw=HW):
        with tempfile.TemporaryDirectory() as out:
            key = engine._machine_key(hw)
            write_build(out, old, key_on_disk)
            prior = engine._prior_identity(out, key)
            engine._prepare_out(out)
            write_build(out, new)
            h = H()
            engine._keep_identity(out, prior, key, h)
            return generic_of(out), h.notices, open(os.path.join(out, engine.IDENTITY_FOR)).read().strip()

    def test_a_rebuild_for_the_same_pc_and_model_keeps_the_identity(self):
        g, notes, key = self.rebuild(OLD, NEW, engine._machine_key(HW))
        for k in engine.IDENTITY_KEYS:
            self.assertEqual(g[k], OLD[k], k)
        self.assertTrue(any("kept the serial number" in n for n in notes), notes)
        self.assertEqual(key, engine._machine_key(HW))

    def test_a_build_folder_from_before_the_pc_was_recorded_keeps_the_identity(self):
        g, _, _ = self.rebuild(OLD, NEW, None)
        self.assertEqual(g["SystemSerialNumber"], OLD["SystemSerialNumber"])

    def test_a_new_mac_model_gets_its_own_serial_and_says_so(self):
        g, notes, _ = self.rebuild(OLD, dict(NEW, SystemProductName="iMac20,1"))
        self.assertEqual(g["SystemSerialNumber"], NEW["SystemSerialNumber"])
        self.assertTrue(any("Mac model changed" in n for n in notes), notes)

    def test_negative_control_a_folder_built_for_another_pc_is_not_reused(self):
        other = {"Motherboard": {"Name": "X870E"}, "CPU": {"Processor Name": "AMD Ryzen 9 9900X"}}
        g, notes, _ = self.rebuild(OLD, NEW, engine._machine_key(other))
        self.assertEqual(g["SystemSerialNumber"], NEW["SystemSerialNumber"])
        self.assertEqual(notes, [])

    def test_negative_control_a_placeholder_serial_is_not_carried_over(self):
        g, _, _ = self.rebuild(dict(OLD, SystemSerialNumber=engine.PLACEHOLDER_SERIALS[0]), NEW)
        self.assertEqual(g["SystemSerialNumber"], NEW["SystemSerialNumber"])

    def test_no_previous_build_means_nothing_to_keep(self):
        with tempfile.TemporaryDirectory() as out:
            self.assertIsNone(engine._prior_identity(out, engine._machine_key(HW)))

    def test_build_reads_the_identity_before_the_wipe_and_restores_it_after_the_engine(self):
        src = inspect.getsource(engine.build)
        self.assertLess(src.index("_prior_identity(out_dir"), src.index("_prepare_out(out_dir)"))
        self.assertLess(src.index("o.build_opencore_efi("), src.index("_keep_identity(out_dir"))
        self.assertLess(src.index("_keep_identity(out_dir"), src.index("policy_mod.apply("))


if __name__ == "__main__":
    unittest.main()
