"""Stick logs sent from the Windows app name the board and CPU the stick was built for (from the stick's
NullMoth/system-profile.json). EXITBS:START freezes (49 uploads) could only be grouped by CPU because no upload named
the board; the per-board quirk table needs it."""
import pathlib
import unittest

FORM = (pathlib.Path(__file__).resolve().parents[1] / "windows/App/MainForm.cs").read_text()


class StickLogNamesBoard(unittest.TestCase):
    def test_the_board_note_rides_with_the_stick_log(self):
        loop = FORM[FORM.index("internal async void OfferStickLogs"):FORM.index("if (found.Count == 0)")]
        self.assertIn("var board = StickBoard(d.RootDirectory.FullName);", loop)
        self.assertIn("provenance.Add(board);", loop)
        send = FORM[FORM.index("var what = \"startup log from the stick\""):]
        self.assertIn("string.Join(\"; \", provenance)", send[:400])

    def test_the_board_comes_from_the_sticks_own_profile_bounded(self):
        fn = FORM[FORM.index("internal static string StickBoard"):FORM.index("static string RedactConfig")]
        self.assertIn('Path.Combine(root, "NullMoth", "system-profile.json")', fn)
        self.assertIn('field("board")', fn)
        self.assertIn('field("cpu")', fn)
        self.assertIn("Length > 1 << 20", fn)
        self.assertIn("catch (Exception) { return \"\"; }", fn)

    def test_the_profile_writer_still_records_board_and_cpu(self):
        src = (pathlib.Path(__file__).resolve().parents[1] / "p1401/nullmoth.py").read_text()
        body = src[src.index("def system_profile"):src.index("RELEASE_API")]
        self.assertIn('"board": mb.get("Name")', body)
        self.assertIn('"cpu": cpu.get("Processor Name")', body)


if __name__ == "__main__":
    unittest.main()
