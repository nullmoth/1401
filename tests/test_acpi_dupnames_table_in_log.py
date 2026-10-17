"""A DSDT iasl could not read travels in the build log, so the repair can be written from the upload.

Three build logs (AMD board "ALASKA A M I 01072009", 27282 B; a Haswell board, 54792 B) ended with "ACPI Error:
AE_ALREADY_EXISTS, During name lookup/catalog" and iasl exit -1. That is not a crash and names no object, so the rename
repair had nothing to go on, and the "kept copy" sat in the loader's temp folder, deleted when the build ended: the logs
carried its path and no bytes. The record now carries the table and the message says the log is what to send."""
import base64
import hashlib
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from p1401 import acpi_dupnames as ad

LOOKUP = ("", "ACPI Error: AE_ALREADY_EXISTS, During name lookup/catalog (20241212/psobject-372)\n", 4294967295)


def dsdt_bytes(size=27282):
    head = b"DSDT" + size.to_bytes(4, "little") + b"\x02\x00" + b"ALASKA" + b"A M I   " + b"\x09\x20\x07\x01" + b"INTL" + b"\x31\x03\x22\x20"
    return head + b"\x5b\x82\x06UP00\x00" * 2 + b"\x00" * (size - len(head) - 16)


class TableInLog(unittest.TestCase):
    def run_tolerated(self, result, data):
        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        path = os.path.join(tmp, "dsdt.aml")
        with open(path, "wb") as fh:
            fh.write(data)
        iasl = os.path.join(tmp, "iasl")

        class Runner:
            calls = 0

            def run(self, command):
                self.calls += 1
                return result
        records, printed = [], []
        d = SimpleNamespace(r=Runner(), iasl=iasl)
        with mock.patch("builtins.print", lambda *a, **k: printed.append(" ".join(str(x) for x in a))), ad.tolerate(d, records):
            d.r.run({"args": [iasl, "-dl", "-l", path]})
        return records, printed, d.r.calls

    def test_a_duplicate_name_iasl_did_not_identify_is_recorded_with_the_table(self):
        data = dsdt_bytes()
        records, printed, calls = self.run_tolerated(LOOKUP, data)
        self.assertEqual(calls, 1)  # nothing to rename: not retried
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual(r["hex"], "0xffffffff")
        self.assertIn("a name is defined twice", r["reason"])
        self.assertEqual(base64.b64decode(r["dsdt_b64"]), data)
        self.assertEqual(r["dsdt_sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(r["dsdt_size"], len(data))
        self.assertEqual(r["dsdt_oem"], "ALASKA A M I")

    def test_the_message_says_the_log_is_what_to_send(self):
        _, printed, _ = self.run_tolerated(LOOKUP, dsdt_bytes())
        text = "\n".join(printed)
        self.assertIn("iasl stopped on this DSDT", text)
        self.assertIn("a name is defined twice and iasl did not say which", text)
        self.assertIn("send the log with Send logs", text)
        self.assertNotIn("crashed", text)

    def test_a_real_crash_keeps_its_wording_and_also_carries_the_table(self):
        data = dsdt_bytes(2000)
        records, printed, _ = self.run_tolerated(("", "", 3221225477), data)
        self.assertEqual(records[0]["hex"], "0xc0000005")
        self.assertNotIn("reason", records[0])
        self.assertEqual(base64.b64decode(records[0]["dsdt_b64"]), data)
        self.assertIn("iasl crashed on this DSDT", "\n".join(printed))
        self.assertIn("included in this build log", "\n".join(printed))

    def test_a_table_over_the_cap_is_described_not_embedded(self):
        records, _, _ = self.run_tolerated(LOOKUP, b"DSDT" + b"\x00" * (ad.TABLE_IN_LOG_MAX + 100))
        self.assertNotIn("dsdt_b64", records[0])
        self.assertIn("not included", records[0]["dsdt_error"])

    def test_a_named_duplicate_is_still_renamed_as_before(self):
        # the existing repair path is untouched: a message that names the object leads to a rename and a retry
        tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        path = os.path.join(tmp, "dsdt.aml")
        dev = lambda n: b"\x5b\x82" + bytes([len(n) + 1]) + n  # noqa: E731
        with open(path, "wb") as fh:
            fh.write(b"HDR" + dev(b"UP00") + dev(b"UP00"))
        iasl = os.path.join(tmp, "iasl")

        class Runner:
            def run(self, command):
                with open(path, "rb") as fh:
                    if len(ad.device_names(fh.read(), b"UP00")) > 1:
                        return ("", "Failure creating named object [\\_SB.PCI0.GPP7.UP00], AE_ALREADY_EXISTS", 255)
                return ("ok", "", 0)
        records = []
        d = SimpleNamespace(r=Runner(), iasl=iasl)
        with mock.patch("builtins.print"), ad.tolerate(d, records):
            r = d.r.run({"args": [iasl, "-dl", "-l", path]})
        self.assertEqual(r[2], 0)
        self.assertEqual(records[0]["copies"], 1)


if __name__ == "__main__":
    unittest.main()
