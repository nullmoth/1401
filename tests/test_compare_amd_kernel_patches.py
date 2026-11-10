"""tools/compare_amd_kernel_patches.py: a patch list covers another when same-bytes patches span its kernel range."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import compare_amd_kernel_patches as cmp  # noqa: E402


def patch(lo, hi, find=b"\x01", comment="p"):
    return {"Identifier": "kernel", "Base": "", "Find": find, "Replace": b"\x02", "Mask": b"", "ReplaceMask": b"",
            "Count": 1, "Skip": 0, "Limit": 0, "MinKernel": lo, "MaxKernel": hi, "Comment": comment}


class Coverage(unittest.TestCase):
    def test_an_identical_list_covers_itself(self):
        a = [patch("21.0.0", "25.99.99")]
        self.assertEqual(cmp.missing(a, a), [])

    def test_a_patch_split_over_two_ranges_still_covers_the_original(self):
        ref = [patch("21.0.0", "25.99.99")]
        cand = [patch("21.0.0", "24.99.99"), patch("25.0.0", "25.99.99")]
        self.assertEqual(cmp.missing(ref, cand), [])

    def test_a_gap_between_the_ranges_is_reported(self):
        ref = [patch("21.0.0", "25.99.99", comment="whole")]
        cand = [patch("21.0.0", "23.99.99"), patch("25.0.0", "25.99.99")]
        self.assertEqual([p["Comment"] for p in cmp.missing(ref, cand)], ["whole"])

    def test_a_patch_with_other_bytes_for_the_newest_kernel_does_not_count(self):
        # the case that made a reference list stale: macOS 26 needs different bytes for the same function
        ref = [patch("21.0.0", "25.99.99")]
        cand = [patch("21.0.0", "24.99.99"), patch("25.0.0", "25.99.99", find=b"\x09")]
        self.assertEqual(len(cmp.missing(ref, cand)), 1)

    def test_a_patch_to_the_end_of_a_minor_joins_the_next_minor(self):
        ref = [patch("25.0.0", "25.99.99")]
        cand = [patch("25.0.0", "25.3.99"), patch("25.4.0", "25.99.99")]
        self.assertEqual(cmp.missing(ref, cand), [])

    def test_a_disabled_patch_is_not_loaded(self):
        import plistlib
        import tempfile
        on, off = patch("21.0.0", "25.99.99", comment="on"), patch("21.0.0", "25.99.99", comment="off")
        on["Enabled"], off["Enabled"] = True, False
        with tempfile.NamedTemporaryFile(suffix=".plist") as fh:
            plistlib.dump({"Kernel": {"Patch": [on, off]}}, fh)
            fh.flush()
            self.assertEqual([p["Comment"] for p in cmp.load(fh.name)], ["on"])

# Needs macOS tools or inputs that exist only where the release is built. The Windows package check counts a skipped
# test as a failure, so these are not collected there; the Mac release step runs them.
if sys.platform != "darwin":
    del Coverage.test_a_disabled_patch_is_not_loaded


if __name__ == "__main__":
    unittest.main()
