"""Windows launcher safety/quality checks: output collection, consent defaults, fail-closed disk fallback."""
import pathlib
import unittest

APP = pathlib.Path(__file__).resolve().parents[1] / "windows" / "App"
MAIN = (APP / "MainForm.cs").read_text(encoding="utf-8")
DISKS = (APP / "Disks.cs").read_text(encoding="utf-8")


class Output(unittest.TestCase):
    def test_scan_and_write_output_are_locked(self):
        # Engine.Run delivers stdout and stderr on two threads; List<T>.Add is not thread-safe.
        self.assertIn("lock (scanLines) scanLines.Add(l)", MAIN)
        self.assertIn("lock (writeLines) writeLines.Add(l)", MAIN)
        self.assertIn("lock (lines) lines.Add(l)", MAIN)


class Consent(unittest.TestCase):
    def test_enter_does_not_send_a_log_by_default(self):
        self.assertIn('Loc.T("1401 - sending the log"), MessageBoxButtons.OKCancel, MessageBoxIcon.Information, '
                      'MessageBoxDefaultButton.Button2', MAIN)

    def test_the_screen_line_dialog_defaults_to_cancel(self):
        self.assertIn("f.AcceptButton = cancel; f.CancelButton = cancel;", MAIN)
        self.assertNotIn("f.AcceptButton = send;", MAIN)


class DiskFallback(unittest.TestCase):
    def test_an_unknown_os_disk_fails_closed(self):
        block = DISKS.split("static void AddUsbInterfaceDisks", 1)[1].split("static uint OsDiskNumber", 1)[0]
        self.assertIn("if (osDisk == uint.MaxValue) return;", block)


if __name__ == "__main__":
    unittest.main()
