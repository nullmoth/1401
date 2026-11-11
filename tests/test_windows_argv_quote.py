"""Engine.Q must quote one argument the way Windows parses it.

The old Q() only replaced an embedded quote with \\" and wrapped the whole value in quotes. A folder ending in a
backslash and containing a space (C:\\Program Files\\1401\\) then escaped the closing quote, and CommandLineToArgvW
merged the following --stick-id, --stick-size and --stick-name into the previous argument. The writer, with no
identity, fell back to the bare disk number.
"""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
APP = REPO / "windows" / "App"


def csc():
    path = pathlib.Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
    return str(path) if path.is_file() else None


class ArgvQuoting(unittest.TestCase):
    def test_the_app_uses_the_tested_quoter(self):
        engine = (APP / "Engine.cs").read_text(encoding="utf-8")
        self.assertIn("public static string Q(string s) { return Argv.Quote(s); }", engine)

    @unittest.skipUnless(sys.platform == "win32" and csc(), "needs Windows and the .NET Framework compiler")
    def test_quote_round_trips_through_windows_own_parser(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = os.path.join(tmp, "argv-check.exe")
            build = subprocess.run([csc(), "/nologo", "/target:exe", "/out:" + exe,
                                    str(APP / "Argv.cs"), str(REPO / "tests" / "native" / "ArgvQuoteCheck.cs")],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            ran = subprocess.run([exe], capture_output=True, text=True, timeout=60)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
            self.assertIn("OK argv quoting", ran.stdout)


if __name__ == "__main__":
    unittest.main()
