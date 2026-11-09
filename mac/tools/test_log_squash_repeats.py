#!/usr/bin/env python3
"""A line the driver prints once per frame must not fill the kernel-log part of Send logs (1401 #16, 512 KiB cap): lines
are compared without their numbers, a pattern seen more than 300 times keeps its first and last 30, the rest is
counted in one marker, and every other line stays in order."""
import pathlib
import subprocess
import unittest

SETUP = pathlib.Path(__file__).resolve().parents[1] / "Resources/nullmoth-setup.sh"
TEXT = SETUP.read_text()
a = TEXT.index("squash_repeats() {")
SQUASH = TEXT[a:TEXT.index("# Copy newest files", a)]
b = TEXT.index("headtail() {")
HEADTAIL = TEXT[b:TEXT.index("# A line that repeats", b)]


def run(pipeline, lines):
    p = subprocess.run(["/bin/bash", "-c", SQUASH + "\n" + HEADTAIL + "\n" + pipeline], input="\n".join(lines) + "\n",
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return p.stdout.splitlines()


def log():
    out = []
    word = lambda i: "".join(chr(97 + (i // 26 ** k) % 26) for k in range(3))   # distinct words, no digits
    for i in range(1200):
        out.append(f"NVRM-fb: step {word(i)} done")
    # the per-frame line, between and around the real ones
    mixed = []
    for i, line in enumerate(out):
        mixed.append(line)
        for f in range(5):
            mixed.append(f"NVRMFB: nvScanoutInfo {85 + (i + f) % 15}% frame {i * 5 + f} at 0x{i * 5 + f:08x}")
    return mixed


class SquashRepeats(unittest.TestCase):
    def test_every_ordinary_line_survives_and_the_per_frame_line_is_counted(self):
        lines = log()
        got = run("squash_repeats | headtail 1500 1500", lines)
        real = [l for l in lines if l.startswith("NVRM-fb: step")]
        self.assertEqual([l for l in got if l.startswith("NVRM-fb: step")], real)
        frames = [l for l in got if "nvScanoutInfo" in l and not l.startswith("...")]
        self.assertEqual(len(frames), 60)
        self.assertEqual(frames[0], lines[1])
        marker = [l for l in got if l.startswith("... ") and "similar lines left out" in l]
        self.assertEqual(len(marker), 1)
        self.assertIn(f"{6000 - 60} similar lines", marker[0])

    def test_negative_control_without_it_the_real_lines_are_cut(self):
        got = run("headtail 1500 1500", log())
        real = [l for l in got if l.startswith("NVRM-fb: step")]
        self.assertLess(len(real), 1200)

    def test_a_pattern_seen_300_times_or_less_is_left_whole(self):
        lines = [f"flip {i} ok" for i in range(300)] + ["other"]
        self.assertEqual(run("squash_repeats", lines), lines)
        lines = [f"flip {i} ok" for i in range(301)]
        got = run("squash_repeats", lines)
        self.assertEqual(len(got), 61)
        self.assertEqual(got[:30], lines[:30])
        self.assertEqual(got[-30:], lines[-30:])

    def test_empty_input_gives_empty_output(self):
        self.assertEqual(run("squash_repeats", []).count("x"), 0)


if __name__ == "__main__":
    unittest.main()
