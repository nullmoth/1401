"""The shared validator runner: a binary the OS kills is signed ad hoc in a private copy and run again; one that is still killed
is reported as the OS killing it, not as a validation failure."""
import os
import sys
import tempfile
import unittest

from tests.ocvalidate_run import run_validator


@unittest.skipUnless(sys.platform == "darwin", "the signing retry is macOS behaviour")
class Runner(unittest.TestCase):
    def cfg(self):
        p = os.path.join(tempfile.mkdtemp(), "config.plist")
        open(p, "w").write("x")
        return p

    def test_an_ordinary_run_returns_the_process(self):
        p = run_validator(b"#!/bin/sh\necho fine\nexit 3\n", self.cfg())
        self.assertEqual((p.returncode, p.stdout.strip()), (3, "fine"))

    def test_a_binary_killed_once_is_signed_and_run_again(self):
        marker = os.path.join(tempfile.mkdtemp(), "m")
        tool = f"#!/bin/sh\nif [ -f {marker} ]; then echo second; exit 0; fi\ntouch {marker}\nkill -9 $$\n".encode()
        p = run_validator(tool, self.cfg())
        self.assertEqual((p.returncode, p.stdout.strip()), (0, "second"))

    def test_a_binary_killed_every_time_says_the_os_killed_it(self):
        with self.assertRaises(AssertionError) as c:
            run_validator(b"#!/bin/sh\nkill -9 $$\n", self.cfg())
        self.assertIn("validator killed by the OS", str(c.exception))


if __name__ == "__main__":
    unittest.main()
