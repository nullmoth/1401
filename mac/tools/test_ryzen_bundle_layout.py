#!/usr/bin/env python3
"""mac/build.sh copies Resources/* into the app and hashes every entry as a plain file: a folder in Resources stops the build
("cp: Resources/ryzenadj-macos is a directory"). The RyzenAdj source lives beside Resources, not in it."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class Layout(unittest.TestCase):
    def test_resources_holds_only_plain_files(self):
        self.assertEqual([p.name for p in (ROOT / "Resources").iterdir() if not p.is_file()], [])

    def test_the_ryzenadj_source_is_outside_the_bundle_and_the_script_and_hash_list_are_in(self):
        self.assertTrue((ROOT / "ryzenadj-macos/build.sh").is_file() and (ROOT / "ryzenadj-macos/osdep_macos.c").is_file())
        for n in ("nullmoth-ryzen-power.sh", "ryzenadj.sha256"):
            self.assertTrue((ROOT / "Resources" / n).is_file(), n)


if __name__ == "__main__":
    unittest.main()
