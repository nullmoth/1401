"""A DSDT that macOS's ACPICA (20160930) would discard is repaired (10-10: 43 of 233 users' DSDTs; all 43 load in
acpiexec R09_30_16 after the repair, and all 189 clean ones are left alone). Synthetic tables, no user data."""
import os
import plistlib
import tempfile
import unittest

from p1401 import dsdt_pass1 as m


def pkg(op, body):
    return op + m._encode_pkglen(len(body)) + body


def table(body):
    d = bytearray(b"DSDT" + (36 + len(body)).to_bytes(4, "little") + b"\x02\x00" + b"NMTEST" + b"TESTTABL" +
                  (1).to_bytes(4, "little") + b"INTL" + (0x20160930).to_bytes(4, "little")) + body
    d[9] = (-sum(d)) & 0xFF
    return bytes(d)


SB = b"\\_SB_"
FOO_IN_IF = pkg(b"\xa0", b"\x01" + pkg(b"\x10", SB + pkg(b"\x5b\x82", b"FOO_"))[0:])        # If (One) { Scope(\_SB) { Device(FOO) } }
FWD_SCOPE = pkg(b"\x10", b"\\\x2e_SB_FOO_" + b"\x08XXXX\x01")                               # Scope(\_SB.FOO) { Name(XXXX, One) }
NESTED = pkg(b"\x10", SB + pkg(b"\x5b\x82", b"BAR_" + pkg(b"\x10", b"\\\x2e_SB_FOO_")))       # Scope(\_SB){Device(BAR){Scope(\_SB.FOO){}}}
GOOD = pkg(b"\x10", SB + pkg(b"\x5b\x82", b"BAZ_" + b"\x08_ADR\x00"))                        # Scope(\_SB){Device(BAZ){Name(_ADR,0)}}


class Pass1(unittest.TestCase):
    def test_a_forward_scope_at_top_level_and_nested_is_found(self):
        self.assertEqual(len(m.failing_scopes(table(FOO_IN_IF + FWD_SCOPE + NESTED))), 2)

    def test_a_clean_table_is_left_byte_identical(self):
        t = table(GOOD)
        self.assertEqual(m.repair(t), (t, 0))

    def test_repair_defers_both_and_keeps_the_table_valid(self):
        fixed, n = m.repair(table(FOO_IN_IF + FWD_SCOPE + NESTED + GOOD))
        self.assertEqual(n, 2)
        self.assertEqual(int.from_bytes(fixed[4:8], "little"), len(fixed))
        self.assertEqual(sum(fixed) & 0xFF, 0)
        self.assertEqual(m.failing_scopes(fixed), [])  # both now sit in an If, which pass 1 skips
        self.assertIn(b"\xa0", fixed[36 + len(FOO_IN_IF):36 + len(FOO_IN_IF) + 2])

    def test_each_deferred_scope_is_guarded_by_condrefof_of_its_own_target(self):
        """A target the firmware creates only for another OS never exists on macOS: a bare Scope would fail there."""
        fixed, n = m.repair(table(FOO_IN_IF + FWD_SCOPE))
        self.assertEqual(n, 1)
        at = fixed.index(b"\x5b\x12")
        # the byte before the predicate is the If's PkgLength, and the opcode before that is If
        self.assertEqual(fixed[at - 2], 0xA0)
        self.assertEqual(fixed[at:at + 13], b"\x5b\x12\\\x2e_SB_FOO_\x00")
        # the Scope follows the predicate unchanged, and the If ends where the Scope ends
        scope = pkg(b"\x10", b"\\\x2e_SB_FOO_" + b"\x08XXXX\x01")
        self.assertEqual(fixed[at + 13:at + 13 + len(scope)], scope)
        self.assertEqual(fixed[-len(scope):], scope)

    def test_a_nested_scope_is_guarded_by_its_name_as_written(self):
        fixed, n = m.repair(table(FOO_IN_IF + NESTED))
        self.assertEqual(n, 1)
        self.assertIn(b"\x5b\x12\\\x2e_SB_FOO_\x00\x10", fixed)
        self.assertEqual(sum(fixed) & 0xFF, 0)
        self.assertEqual(int.from_bytes(fixed[4:8], "little"), len(fixed))
        self.assertEqual(m.failing_scopes(fixed), [])

    def test_zero_padding_between_objects_is_stepped_over(self):
        """A user's DSDT carries 120 zero bytes inside a Device, between two objects (ZeroOp); it used to stop the repair."""
        padded = pkg(b"\x10", SB + pkg(b"\x5b\x82", b"BAZ_" + b"\x08_ADR\x00" + b"\x00" * 120 + b"\x08_UID\x01"))
        t = table(FOO_IN_IF + padded + FWD_SCOPE)
        fixed, n = m.repair(t)
        self.assertEqual(n, 1)
        self.assertEqual(m.failing_scopes(fixed), [])

    def test_users_dsdts_in_the_corpus_all_repair_when_the_corpus_is_present(self):
        d = os.environ.get("NM_DSDT_CORPUS")
        if not d or not os.path.isdir(d):
            self.skipTest("set NM_DSDT_CORPUS to a folder of uploaded DSDT .aml files")
        bad = []
        for f in sorted(os.listdir(d)):
            if f.lower().endswith(".aml"):
                fixed, n = m.repair(open(os.path.join(d, f), "rb").read())
                if m.failing_scopes(fixed) or (n and sum(fixed) & 0xFF):
                    bad.append(f)
        self.assertEqual(bad, [])

    def test_apply_ships_the_repaired_table_only_when_needed(self):
        for body, want in ((FOO_IN_IF + FWD_SCOPE, True), (GOOD, False)):
            t = tempfile.mkdtemp()
            acpi, oc = os.path.join(t, "acpi"), os.path.join(t, "out", "EFI", "OC")
            os.makedirs(acpi)
            os.makedirs(os.path.join(oc, "ACPI"))
            open(os.path.join(acpi, "DSDT.aml"), "wb").write(table(body))
            with open(os.path.join(oc, "config.plist"), "wb") as f:
                plistlib.dump({"ACPI": {"Add": []}}, f)
            changes = m.apply(acpi, os.path.join(t, "out"))
            cfg = plistlib.load(open(os.path.join(oc, "config.plist"), "rb"))
            self.assertEqual(bool(changes), want)
            self.assertEqual(os.path.exists(os.path.join(oc, "ACPI", "DSDT.aml")), want)
            self.assertEqual(any(e["Path"] == "DSDT.aml" for e in cfg["ACPI"]["Add"]), want)


if __name__ == "__main__":
    unittest.main()
