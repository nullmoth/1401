#!/usr/bin/env python3
"""The Windows app sends a scan's ACPI tables (acpi-bundle.zip) with a failed-run log only when the consent text it showed
named them, and that text is translated. Static checks on windows/App (the app builds on the mini, not under test here)."""
import pathlib, re, sys, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FORM = (ROOT / "windows/App/MainForm.cs").read_text(encoding="utf-8")
LOC = (ROOT / "windows/App/Loc.cs").read_text(encoding="utf-8")


def offer_log():
    i = FORM.index("void OfferLog(string file, string kind)")
    return FORM[i:FORM.index("\n        }\n", i)]


class AcpiConsent(unittest.TestCase):
    def test_the_tables_are_found_before_the_question_is_asked(self):
        body = offer_log()
        self.assertLess(body.index('"acpi-bundle.zip"'), body.index("MessageBox.Show("))

    def test_the_question_names_the_tables_when_they_will_be_sent(self):
        body = offer_log()
        m = re.search(r"if \(acpiZip != null\)\s*(?://[^\n]*\n\s*)?text = Loc\.F\(", body)
        self.assertIsNotNone(m, "no consent variant chosen for the tables")
        self.assertIn("ACPI firmware tables", body[m.end():body.index("MessageBox.Show(")])

    def test_the_tables_are_sent_only_under_that_same_condition(self):
        body = offer_log()
        send = body.index('"1401-acpi-tables.zip"')
        guard = body.rindex("if (acpiZip != null)", 0, send)
        self.assertGreater(guard, body.index("MessageBox.Show("))
        self.assertNotIn("File.Exists(acpiZip)", body[body.index("MessageBox.Show("):])

    def test_the_consent_variant_is_translated(self):
        i = LOC.find("and this PC's ACPI firmware tables")
        self.assertGreater(i, 0)
        self.assertIn("ACPI 固件表", LOC[i:i + 1500])


if __name__ == "__main__":
    sys.exit(unittest.main())
