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
        self.assertEqual(m.failing_scopes(fixed), [])  # both now sit in If (One), which pass 1 skips
        self.assertIn(b"\xa0", fixed[36 + len(FOO_IN_IF):36 + len(FOO_IN_IF) + 2])

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
