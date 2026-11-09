#!/usr/bin/env python3
"""Send logs uploads at most 16 files per run (ReportQueue.select). A recorded flicker sample and the EFI files must be among
them: the flicker sample is critical, and critical files keep the order sendLogs gives them instead of the arbitrary order an
unstable sort left. The EFI scan writes a line per partition so a report with no EFI files says why.

usage: test_send_logs_selection.py [Sources dir]   (the selection arms compile Swift: a Mac with Xcode)"""
import re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv.pop(1)) if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else ROOT / "Sources"
QUEUE = (SRC / "ReportQueue.swift").read_text()
MAIN = (SRC / "main.swift").read_text()
SETUP = (ROOT / "Resources/nullmoth-setup.sh").read_text()


def critical_names():
    m = re.search(r'let critical = \[(.*?)\]\.contains', QUEUE, re.S)
    return re.findall(r'"([^"]+)"', m.group(1))


def select_source():
    i = QUEUE.index("    static func select(")
    return QUEUE[i:QUEUE.index("\n    }\n", i) + 6]


class Selection(unittest.TestCase):
    def test_the_flicker_sample_is_critical(self):
        self.assertTrue(any(k in "display-flicker-sample.txt" for k in critical_names()))

    def test_the_flicker_sample_leads_the_send_order(self):
        m = re.search(r'let important = \["([^"]+)"', MAIN)
        self.assertEqual(m.group(1), "display-flicker-sample.txt")

    @unittest.skipUnless(shutil.which("xcrun"), "needs Xcode")
    def test_with_twenty_critical_files_the_first_eight_given_are_kept_in_order(self):
        crit = critical_names()
        prog = ("import Foundation\nstruct Entry { let pending: URL; let old: Bool; let critical: Bool; let date: Date }\n"
                "enum Q {\n" + select_source() + "}\n"
                "let names = [\"display-flicker-sample.txt\"] + (1...12).map { \"disk0s1-efi-config\\($0).txt\" } + (1...7).map { \"arm-\\($0).txt\" } + (1...6).map { \"macos-WindowServer-\\($0).ips\" }\n"
                "let crit: [String] = [" + ",".join('"%s"' % c for c in crit) + "]\n"
                "let e = names.map { n in Entry(pending: URL(fileURLWithPath: \"/p/\" + n), old: false, critical: crit.contains { n.contains($0) }, date: Date()) }\n"
                "for c in Q.select(e) { print(c.pending.lastPathComponent) }\n")
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "s.swift").write_text(prog)
            r = subprocess.run(["xcrun", "swiftc", str(Path(d) / "s.swift"), "-o", str(Path(d) / "s")], capture_output=True, text=True, timeout=180)
            self.assertEqual(r.returncode, 0, r.stderr[-800:])
            out = subprocess.run([str(Path(d) / "s")], capture_output=True, text=True).stdout.split()
        self.assertEqual(len(out), 16)
        self.assertEqual(out[0], "display-flicker-sample.txt")
        self.assertEqual(out[1:4], ["disk0s1-efi-config1.txt", "disk0s1-efi-config2.txt", "disk0s1-efi-config3.txt"])


class EfiScan(unittest.TestCase):
    def test_every_partition_outcome_is_written(self):
        for phrase in ("did not mount", "file(s) collected", "Clover (not read)", "mounted, no EFI/OC folder",
                       "no EFI, FAT or Basic Data partition was listed"):
            self.assertIn(phrase, SETUP)

    def test_the_scan_file_is_named_to_count_as_critical(self):
        self.assertIn('efiscan="$COLLECT/disks-efi-scan.txt"', SETUP)
        self.assertTrue(any(k in "disks-efi-scan.txt" for k in critical_names()))


if __name__ == "__main__":
    unittest.main()
