"""Regression checks for the WinForms layout contract.

The GUI itself only runs on Windows, so these checks keep the source-level
layout invariants covered on the cross-platform test runner.  The packaged
Windows verification still exercises the real form when a Windows runner is
available.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "windows/App/MainForm.cs").read_text()


class WindowsLayout(unittest.TestCase):
    def test_main_form_wraps_notes_and_reflows_for_dpi_and_resize(self):
        self.assertIn("body.AutoScroll = true", SOURCE)
        self.assertIn("note.AutoSize = true", SOURCE)
        self.assertIn("note.MaximumSize", SOURCE)
        self.assertIn("body.Resize +=", SOURCE)
        self.assertIn("DpiChanged +=", SOURCE)
        self.assertIn("LayoutBody()", SOURCE)
        self.assertIn("FitToWorkingArea()", SOURCE)
        self.assertIn("body.AutoScrollPosition = Point.Empty", SOURCE)
        self.assertIn("availableOuterWidth", SOURCE)
        self.assertIn("MinimumSize = new Size(minWidth, minHeight)", SOURCE)
        self.assertIn("FitToWorkingArea(e.DeviceDpiNew)", SOURCE)
        self.assertIn("chromeWidth", SOURCE)
        self.assertIn("availableClientWidth", SOURCE)
        self.assertNotIn("side[i].Font = i == page ? ActiveStepFont : Theme.Body", SOURCE)
        self.assertIn("side[i].Font.Bold", SOURCE)

    def test_guide_is_positioned_by_layout_instead_of_overlapping_note(self):
        self.assertNotIn("guide.Bounds = new Rectangle(24, 110, 620, 360)", SOURCE)
        self.assertIn("guide.Top =", SOURCE)
        self.assertIn("guide.Height =", SOURCE)

    def test_footer_buttons_follow_the_available_width(self):
        self.assertIn("foot.Resize +=", SOURCE)
        self.assertIn("next.Left =", SOURCE)
        self.assertIn("back.Left =", SOURCE)

    def test_log_upload_dialog_wraps_long_diagnostics(self):
        self.assertIn("AutoScroll = true", SOURCE)
        self.assertIn("AutoSize = true", SOURCE)
        self.assertIn("MaximumSize = new Size(contentWidth, 0)", SOURCE)


if __name__ == "__main__":
    unittest.main()
