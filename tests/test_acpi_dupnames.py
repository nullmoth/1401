"""A DSDT that declares the same Method twice (a GPE handler \\_GPE._L02 the firmware defines in more than one branch)
makes iasl stop with AE_ALREADY_EXISTS exactly like a repeated Device. The Device-only scan left it unrepaired and the
build stopped at "dsdt.aml could not be disassembled" (BIOSTAR B650MT-E PRO, 1401 #1 / driver #7)."""
import os
import tempfile
import unittest
from types import SimpleNamespace

from p1401 import acpi_dupnames as ad


def dev(name, body=b""):
    return b"\x5b\x82" + bytes([len(name) + len(body) + 1]) + name + body


def meth(name, body=b""):  # Method op: 14 PkgLength NameSeg MethodFlags body
    inner = name + b"\x00" + body
    return b"\x14" + bytes([len(inner) + 1]) + inner


class MethodDuplicates(unittest.TestCase):
    def test_a_method_declared_twice_is_found(self):
        aml = bytearray(b"HDR" + meth(b"_L02") + meth(b"_L02"))
        self.assertEqual(len(ad.method_names(aml, b"_L02")), 2)

    def test_the_later_method_is_renamed_and_the_first_kept(self):
        aml = bytearray(b"HDR" + meth(b"_L02") + b"\xa0\x01" + meth(b"_L02", b"\x00"))
        self.assertEqual(ad.rename_later(aml, b"_L02", 0), 1)
        self.assertEqual(len(ad.method_names(aml, b"_L02")), 1)
        self.assertEqual(len(ad.method_names(aml, b"Z000")), 1)

    def test_a_method_defined_once_is_left_alone(self):
        aml = bytearray(b"HDR" + meth(b"_L08"))
        self.assertEqual(ad.rename_later(aml, b"_L08", 0), 0)

    def test_a_repeated_device_still_works(self):
        aml = bytearray(b"HDR" + dev(b"UP00") + dev(b"UP00") + dev(b"UP00"))
        self.assertEqual(ad.rename_later(aml, b"UP00", 0), 2)

    def test_a_name_that_is_neither_device_nor_method_gives_zero(self):
        aml = bytearray(b"HDR" + meth(b"_L02"))
        self.assertEqual(ad.rename_later(aml, b"M237", 0), 0)


class ToleratesTheMethodClash(unittest.TestCase):
    """The real flow: iasl refuses the table with AE_ALREADY_EXISTS on \\_GPE._L02 until the later Method is renamed,
    then disassembles. The DSDT is only read to plan the build; it is never shipped in the EFI."""

    def test_iasl_disassembles_after_the_method_is_renamed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "DSDT.aml")
            with open(path, "wb") as fh:
                fh.write(b"HDR" + meth(b"_L02") + meth(b"_L02") + meth(b"_L02"))
            iasl = os.path.join(tmp, "iasl")

            class Runner:
                def __init__(self):
                    self.calls = 0

                def run(self, command):
                    self.calls += 1
                    with open(path, "rb") as fh:
                        data = fh.read()
                    if len(ad.method_names(data, b"_L02")) > 1:
                        return ("", "Firmware Error (ACPI): Failure creating named object "
                                    "[\\_GPE._L02], AE_ALREADY_EXISTS", 255)
                    return ("ok", "", 0)

            d = SimpleNamespace(r=Runner(), iasl=iasl)
            records = []
            with ad.tolerate(d, records):
                result = d.r.run({"args": [iasl, "-dl", "-l", path]})
            self.assertEqual(result[2], 0)
            self.assertTrue(records and records[0]["copies"] == 2)
            self.assertEqual(records[0]["renamed"], "\\_GPE._L02")


if __name__ == "__main__":
    unittest.main()
