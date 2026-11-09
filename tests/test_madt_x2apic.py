"""Firmware that lists its processors only as MADT type 9 (x2APIC) leaves macOS with no processor to count; the build
ships the same table with type 0 entries (1401 #252, #64). Synthetic tables."""
import os
import plistlib
import tempfile
import unittest

from p1401 import madt


def x2(apic, uid, flags=1):
    return b"\x09\x10\x00\x00" + apic.to_bytes(4, "little") + flags.to_bytes(4, "little") + uid.to_bytes(4, "little")


def lapic(uid, apic, flags=1):
    return bytes([0, 8, uid, apic]) + flags.to_bytes(4, "little")


IOAPIC = b"\x01\x0c\x02\x00" + (0xFEC00000).to_bytes(4, "little") + (0).to_bytes(4, "little")
OVERRIDE = b"\x02\x0a\x00\x00" + (2).to_bytes(4, "little") + (2).to_bytes(2, "little")[::-1] + b"\x00\x00"[:0]
X2NMI = b"\x0a\x0c" + (5).to_bytes(2, "little") + (0xFFFFFFFF).to_bytes(4, "little") + b"\x01\x00\x00\x00"


def table(body):
    d = bytearray(b"APIC" + (44 + len(body)).to_bytes(4, "little") + b"\x05\x00" + b"ALASKA" + b"A M I   " +
                  (1).to_bytes(4, "little") + b"AMI " + (0x1000013).to_bytes(4, "little") +
                  (0xFEE00000).to_bytes(4, "little") + (1).to_bytes(4, "little")) + body
    d[9] = (-sum(d)) & 0xFF
    return bytes(d)


X2_ONLY = table(b"".join(x2(2 * i, i) for i in range(24)) + IOAPIC + X2NMI)


class Madt(unittest.TestCase):
    def test_a_table_with_only_x2apic_processors_is_rewritten_as_type_0(self):
        fixed, n = madt.rewrite(X2_ONLY)
        self.assertEqual(n, 24)
        types = [t for t, _ in madt.entries(fixed)]
        self.assertEqual((types.count(0), types.count(9), types.count(1), types.count(4), types.count(10)), (24, 0, 1, 1, 0))
        self.assertEqual([(e[2], e[3]) for t, e in madt.entries(fixed) if t == 0][:3], [(0, 0), (1, 2), (2, 4)])
        self.assertEqual(int.from_bytes(fixed[4:8], "little"), len(fixed))
        self.assertEqual(sum(fixed) & 0xFF, 0)
        self.assertEqual(fixed[:36][:4] + fixed[8:36][:0], b"APIC")
        self.assertEqual(fixed[36:44], X2_ONLY[36:44])                       # local APIC address and flags unchanged

    def test_the_nmi_all_processors_uid_becomes_0xff_with_its_flags_and_lint(self):
        fixed, _ = madt.rewrite(X2_ONLY)
        (nmi,) = [e for t, e in madt.entries(fixed) if t == 4]
        self.assertEqual(nmi, bytes([4, 6, 0xFF]) + (5).to_bytes(2, "little") + b"\x01")

    def test_flags_are_kept_so_a_disabled_processor_stays_disabled(self):
        fixed, _ = madt.rewrite(table(x2(0, 0, 1) + x2(2, 1, 0)))
        self.assertEqual([e[4:8] for t, e in madt.entries(fixed) if t == 0], [b"\x01\x00\x00\x00", b"\x00\x00\x00\x00"])

    def test_a_table_that_already_has_type_0_is_left_alone(self):
        mixed = table(lapic(0, 0) + x2(2, 1))
        self.assertEqual(madt.rewrite(mixed), (mixed, 0))

    def test_ids_that_do_not_fit_one_byte_leave_the_firmware_table_alone(self):
        big = table(x2(0x1FF, 0) + x2(0, 1))
        self.assertEqual(madt.rewrite(big), (big, 0))

    def test_a_truncated_table_is_refused_not_guessed(self):
        bad = bytearray(X2_ONLY[:-5])                                         # the last entry is cut short
        bad[4:8] = len(bad).to_bytes(4, "little")
        with self.assertRaises(madt.Unsupported):
            madt.entries(bytes(bad))

    def run_apply(self, data, name="APIC.aml"):
        t = tempfile.mkdtemp()
        acpi, out = os.path.join(t, "acpi"), os.path.join(t, "out")
        os.makedirs(acpi)
        os.makedirs(os.path.join(out, "EFI", "OC", "ACPI"))
        with open(os.path.join(acpi, name), "wb") as f:
            f.write(data)
        with open(os.path.join(out, "EFI", "OC", "config.plist"), "wb") as f:
            plistlib.dump({"ACPI": {"Add": [], "Delete": []}}, f)
        changes = madt.apply(acpi, out)
        with open(os.path.join(out, "EFI", "OC", "config.plist"), "rb") as f:
            return out, changes, plistlib.load(f)["ACPI"]

    def test_apply_deletes_the_firmware_madt_and_adds_ours(self):
        out, changes, acpi = self.run_apply(X2_ONLY)
        self.assertEqual([c["rule"] for c in changes], [madt.RULE])
        self.assertEqual([e["Path"] for e in acpi["Add"]], [madt.SHIM_FILE])
        (d,) = acpi["Delete"]
        self.assertEqual((d["TableSignature"], d["OemTableId"], d["TableLength"], d["All"]), (b"APIC", b"A M I   ", len(X2_ONLY), False))
        with open(os.path.join(out, "EFI", "OC", "ACPI", madt.SHIM_FILE), "rb") as f:
            self.assertEqual(madt.rewrite(X2_ONLY)[0], f.read())

    def test_apply_leaves_an_ordinary_machine_untouched(self):
        out, changes, acpi = self.run_apply(table(b"".join(lapic(i, 2 * i) for i in range(8)) + IOAPIC))
        self.assertEqual((changes, acpi["Add"], acpi["Delete"]), ([], [], []))
        self.assertFalse(os.path.exists(os.path.join(out, "EFI", "OC", "ACPI", madt.SHIM_FILE)))

    def test_apply_without_a_madt_dump_does_nothing(self):
        self.assertEqual(self.run_apply(b"DSDT", "DSDT.aml")[1], [])


if __name__ == "__main__":
    unittest.main()
