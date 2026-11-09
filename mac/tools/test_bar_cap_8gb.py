#!/usr/bin/env python3
"""An installed EFI that resizes the GPU window above 8 GB (ResizeGpuBars 14+) stops the boot at PCI configuration on cards
with a 16 GB BAR1; setup caps it at 13 and leaves -1 and smaller values alone."""
import pathlib
import subprocess
import unittest

T = (pathlib.Path(__file__).resolve().parents[1] / "Resources/nullmoth-setup.sh").read_text()
a = T.index("case \"$bar\" in ''|*[!0-9]*)")
SNIP = T[a:T.index("\n", T.index("esac", a))]


def edits(bar):
    p = subprocess.run(["/bin/bash", "-c", f'EDITS=(); bar="{bar}"\n{SNIP}\nprintf "%s\\n" "${{EDITS[@]}}"'], capture_output=True, text=True)
    return [l for l in p.stdout.splitlines() if l.startswith("UEFI")]


class BarCap(unittest.TestCase):
    def test_above_8gb_is_capped(self):
        for v in (14, 15, 20):
            self.assertEqual(edits(v), ["UEFI.Quirks.ResizeGpuBars|-integer|13"], v)

    def test_8gb_and_below_and_unset_stay(self):
        for v in (13, 12, 0, -1, "", "x"):
            self.assertEqual(edits(v), [], v)


if __name__ == "__main__":
    unittest.main()
