"""A hardware report written before this Windows session is not built from; the PC is checked again.

NM-Q7Q8YRXT: the user turned Intel VMD off in the firmware and the next Build still stopped on "the reported Intel VMD
controller" - the report it read was the one from before the restart. A firmware change needs a restart, so a report
older than the boot is the signal: the engine refuses it with the two times, and the app re-runs Check this PC."""
import os
import tempfile
import time
import unittest
from pathlib import Path

from p1401 import engine

ROOT = Path(__file__).resolve().parents[1]


class StaleReport(unittest.TestCase):
    def report(self, written):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__('shutil').rmtree(d, ignore_errors=True))
        path = os.path.join(d, 'Report.json')
        with open(path, 'w') as fh:
            fh.write('{}')
        os.utime(path, (written, written))
        return path

    def test_a_report_from_before_this_boot_is_refused_with_both_times(self):
        booted = time.time() - 600
        message = engine.stale_scan_message(self.report(booted - 3600), booted=booted)
        self.assertIsNotNone(message)
        self.assertIn('checked before its last restart', message)
        self.assertIn('Run Check this PC again', message)
        self.assertIn(time.strftime('%Y-%m-%d %H:%M', time.localtime(booted)), message)

    def test_a_report_from_this_boot_passes(self):
        booted = time.time() - 600
        self.assertIsNone(engine.stale_scan_message(self.report(booted + 60), booted=booted))

    def test_a_report_within_the_slack_of_the_boot_time_passes(self):
        # the boot time is derived from the uptime counter; a report written in the same minute is not stale
        booted = time.time() - 600
        self.assertIsNone(engine.stale_scan_message(self.report(booted - engine.STALE_SCAN_SLACK + 5), booted=booted))

    def test_an_unknown_boot_time_never_blocks_a_build(self):
        # simulated on every platform: the packaged Windows check treats a skipped test as a failure
        from unittest import mock
        with mock.patch.object(engine, 'boot_epoch', return_value=None):
            self.assertIsNone(engine.stale_scan_message(self.report(0)))

    def test_a_missing_report_is_left_to_the_existing_check(self):
        self.assertIsNone(engine.stale_scan_message('/nonexistent/Report.json', booted=time.time()))

    def test_the_build_checks_before_reading_the_report(self):
        source = (ROOT / 'p1401/engine.py').read_text()
        build = source[source.index('def build('):]
        self.assertLess(build.index('stale_scan_message(report_path)'), build.index('open(report_path, "rb")'))

    def test_the_app_rechecks_a_pc_that_restarted_since_its_scan(self):
        form = (ROOT / 'windows/App/MainForm.cs').read_text()
        step = form[form.index('bool rechecking = page == 1 && scanned && ScanEvidence.OlderThanThisBoot(scanDir)'):form.index('"p1401.scan "')]
        self.assertIn('if (rechecking) scanned = built = false;', step)
        self.assertIn('restarted since it was checked; checking it again', step)
        evidence = (ROOT / 'windows/App/ScanEvidence.cs').read_text()
        self.assertIn('internal static bool OlderThanThisBoot(string dir)', evidence)
        self.assertIn('GetTickCount64()', evidence)
        self.assertIn('File.GetLastWriteTimeUtc(report) < booted - TimeSpan.FromMinutes(1)', evidence)


if __name__ == '__main__':
    unittest.main()
