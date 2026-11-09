"""The Ryzen laptop notice (p1401/ryzen_power.py): only a Ryzen laptop gets it, and it promises nothing it cannot do."""
import unittest

from p1401 import ryzen_power


def rep(mfr="AMD", name="AMD Ryzen 7 7840U w/ Radeon 780M Graphics", platform="Laptop"):
    return {"CPU": {"Manufacturer": mfr, "Processor Name": name}, "Motherboard": {"Platform": platform}}


class Notice(unittest.TestCase):
    def test_a_ryzen_laptop_gets_one_notice(self):
        self.assertEqual(len(ryzen_power.notes(rep())), 1)

    def test_a_ryzen_desktop_an_intel_laptop_and_an_empty_scan_get_none(self):
        self.assertEqual(ryzen_power.notes(rep(platform="Desktop")), [])
        self.assertEqual(ryzen_power.notes(rep(mfr="Intel", name="13th Gen Intel(R) Core(TM) i7-1360P")), [])
        self.assertEqual(ryzen_power.notes(rep(name="AMD Athlon Silver 3050U")), [])
        self.assertEqual(ryzen_power.notes({}), [])
        self.assertEqual(ryzen_power.notes(None), [])

    def test_the_notice_says_it_is_opt_in_and_what_it_needs(self):
        n = ryzen_power.NOTE
        for word in ("off unless you turn it on", "NMSMN", "nmsmn=1", "root"):
            self.assertIn(word, n)


if __name__ == "__main__":
    unittest.main()
