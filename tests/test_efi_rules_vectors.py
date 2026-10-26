"""The Swift checker in the Mac app is tested against mac/tests/efi_rules/vectors.json. If the rules or the Python checker
change and the file is not regenerated, the Swift side would be checked against old answers; this fails first."""
import os
import unittest

from tools import efi_rules_vectors


class Vectors(unittest.TestCase):
    def test_vectors_match_the_python_checker(self):
        with open(efi_rules_vectors.OUT, encoding="utf-8") as fh:
            on_disk = fh.read()
        self.assertEqual(on_disk, efi_rules_vectors.render(), "run: python3 tools/efi_rules_vectors.py")

    def test_vectors_cover_both_outcomes(self):
        cases = efi_rules_vectors.cases()[0]
        self.assertTrue(any(c["issues"] for c in cases) and any(not c["issues"] for c in cases))
        self.assertTrue(all(c["after_fix"] == [] for c in cases), "a fix left an issue")


if __name__ == "__main__":
    unittest.main()
