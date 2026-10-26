"""ocvalidate opens its argument with the ANSI file API, so a config under a Windows account named outside the system
code page could not be read (115 build logs, 10-24 to 10-26: "Failed to read %USERPROFILE%\\?M?N\\..."). It is run from
the config's folder with the bare, ASCII file name."""
import os
import subprocess
import tempfile
import unittest
from unittest import mock

from p1401 import validate


class UnicodeProfilePath(unittest.TestCase):
    def test_validator_gets_the_bare_name_and_runs_in_the_config_folder(self):
        folder = os.path.join(tempfile.mkdtemp(), "王小明", "EFI", "OC")   # a Chinese account name
        os.makedirs(folder)
        cfg = os.path.join(folder, "config.plist")
        open(cfg, "wb").close()
        seen = {}
        def run(command, **kw):
            seen["command"], seen["cwd"] = command, kw.get("cwd")
            return subprocess.CompletedProcess(command, 0, "No issues found.", "")
        with mock.patch.object(validate, "ocvalidate_path", return_value="ocvalidate.exe"), \
             mock.patch.object(validate.subprocess, "run", side_effect=run):
            self.assertEqual(validate.run_ocvalidate(cfg)[0], True)
        self.assertEqual(seen["command"], ["ocvalidate.exe", "config.plist"])
        self.assertEqual(seen["cwd"], folder)
        self.assertTrue(all(ord(c) < 128 for c in seen["command"][1]), "the validator must only ever see an ASCII name")


if __name__ == "__main__":
    unittest.main()
