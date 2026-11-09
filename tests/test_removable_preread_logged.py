"""The app's own read of a removable volume's OpenCore config, done before setup so macOS asks for Removable Volumes in
1401's name, writes its outcome into the setup log. 2.7.2 setups still stopped on "not letting 1401 read" (11-02,
11-06) and nothing said whether the app's read had been refused as well."""
import pathlib
import unittest

MAIN = (pathlib.Path(__file__).resolve().parents[1] / "mac/Sources/main.swift").read_text()


class PrereadLogged(unittest.TestCase):
    def block(self):
        a = MAIN.index("let preread = DispatchGroup()")
        return MAIN[a:MAIN.index("let res = Bundle.main.resourceURL!", a)]

    def test_each_read_outcome_reaches_the_setup_log(self):
        b = self.block()
        for needle in ('"refused (errno', '"read ok"', "not finished within 3 s", "SavedReports.append(Data(prereadText.utf8), to: log)"):
            self.assertIn(needle, b)

    def test_the_log_line_is_written_before_the_privileged_setup_starts(self):
        self.assertLess(MAIN.index("SavedReports.append(Data(prereadText.utf8), to: log)"),
                        MAIN.index("let run = Privileged.run(cmd, timeout: 30 * 60)"))


if __name__ == "__main__":
    unittest.main()
