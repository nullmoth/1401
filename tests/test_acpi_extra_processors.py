"""29 processor devices in the DSDT against 20 enabled in the MADT (Arrow Lake HX laptops, 1401 #141 #110): the extra ones
are hidden from macOS with one DSDT patch each; tables that disagree on numbering, or agree on the count, are left alone."""
import os
import plistlib
import tempfile
import unittest

from p1401 import acpi_cpus, dsdt_pass1 as d
from tests.test_madt_x2apic import table as madt_table, lapic, x2


def cpu(name, uid):
    body = name + b"\x08_HID\x0dACPI0007\x00" + b"\x08_UID" + (bytes([0x0A, uid]) if uid > 1 else bytes([uid]))
    return b"\x5b\x82" + d._encode_pkglen(len(body)) + body


def dsdt(n):
    body = b"\x10" + d._encode_pkglen(5 + sum(len(cpu(b"C%03d" % i, i)) for i in range(n)) + 0) + b"\\_SB_" if False else b""
    devs = b"".join(cpu(b"C%03d" % i, i) for i in range(n))
    scope = b"\x10" + d._encode_pkglen(len(b"\\_SB_") + len(devs)) + b"\\_SB_" + devs
    t = bytearray(b"DSDT" + (36 + len(scope)).to_bytes(4, "little") + b"\x02\x00" + b"ALASKA" + b"A M I   " + (1).to_bytes(4, "little") +
                  b"INTL" + (0x20230331).to_bytes(4, "little")) + scope
    t[9] = (-sum(t)) & 0xFF
    return bytes(t)


def run(dsdt_bytes, madt_bytes):
    t = tempfile.mkdtemp()
    acpi, out = os.path.join(t, "a"), os.path.join(t, "o")
    os.makedirs(acpi); os.makedirs(os.path.join(out, "EFI", "OC"))
    for n, b in (("DSDT.aml", dsdt_bytes), ("APIC.aml", madt_bytes)):
        with open(os.path.join(acpi, n), "wb") as f: f.write(b)
    with open(os.path.join(out, "EFI", "OC", "config.plist"), "wb") as f: plistlib.dump({"ACPI": {"Patch": []}}, f)
    ch = acpi_cpus.apply(acpi, out)
    with open(os.path.join(out, "EFI", "OC", "config.plist"), "rb") as f: return ch, plistlib.load(f)["ACPI"]["Patch"]


MADT20 = madt_table(b"".join(lapic(i, 2 * i) for i in range(20)))


class ExtraProcessors(unittest.TestCase):
    def test_29_devices_against_20_enabled_hide_the_nine_extra(self):
        ch, patches = run(dsdt(29), MADT20)
        self.assertEqual(len(patches), 9)
        self.assertEqual(sorted(p["Find"][:4] for p in patches), sorted(b"C%03d" % i for i in range(20, 29)))
        for p in patches:
            self.assertEqual(len(p["Find"]), len(p["Replace"]))
            self.assertIn(b"ACPI0007", p["Find"]); self.assertIn(b"XCPI0007", p["Replace"])
            self.assertEqual((p["TableSignature"], p["OemTableId"]), (b"DSDT", b"A M I   "))
            self.assertEqual(dsdt(29).count(p["Find"]), 1)
        self.assertEqual([c["rule"] for c in ch], [acpi_cpus.RULE])

    def test_x2apic_only_madt_counts_too(self):
        _, patches = run(dsdt(24), madt_table(b"".join(x2(2 * i, i) for i in range(20))))
        self.assertEqual(len(patches), 4)

    def test_same_count_changes_nothing(self):
        self.assertEqual(run(dsdt(20), MADT20), ([], []))

    def test_a_disabled_madt_processor_is_not_counted_as_enabled(self):
        m = madt_table(b"".join(lapic(i, 2 * i, 1 if i < 18 else 0) for i in range(20)))
        _, patches = run(dsdt(20), m)
        self.assertEqual(sorted(p["Find"][:4] for p in patches), [b"C018", b"C019"])

    def test_numbering_that_does_not_match_leaves_everything_alone(self):
        m = madt_table(b"".join(lapic(100 + i, 2 * i) for i in range(20)))      # MADT UIDs 100..119, DSDT UIDs 0..28
        self.assertEqual(run(dsdt(29), m), ([], []))

    def test_no_madt_or_dsdt_is_no_change(self):
        t = tempfile.mkdtemp()
        self.assertEqual(acpi_cpus.apply(t, t), [])


if __name__ == "__main__":
    unittest.main()
