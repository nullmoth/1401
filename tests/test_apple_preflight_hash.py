"""preflight() must hash the first chunk it samples, not merely count the bytes a server returned."""
import hashlib
import os
import unittest
from unittest import mock

from p1401 import apple

CHUNKS = [os.urandom(64), os.urandom(32), os.urandom(16)]
LIST = [(len(c), hashlib.sha256(c).digest()) for c in CHUNKS]


class PreflightHash(unittest.TestCase):
    def test_a_first_chunk_that_matches_is_reported_verified(self):
        class S:
            status = 200
            headers = {}

            def read(self, n=-1):
                return CHUNKS[0][:n] if n is not None else CHUNKS[0]

            def close(self):
                pass

        info = {"image_url": "http://oscdn/x/BaseSystem.dmg", "image_token": "t"}
        with mock.patch.object(apple, "fetch_chunklist", lambda i: b"signed"),              mock.patch.object(apple, "parse_chunklist", lambda d: LIST),              mock.patch.object(apple, "_asset", lambda u, t, e=None: S()):
            got = apple.preflight(info)
        self.assertTrue(got["verified"])
        self.assertEqual(got["sampled"], len(CHUNKS[0]))

    def test_a_first_chunk_that_does_not_match_is_refused_before_the_erase(self):
        class S:
            status = 200
            headers = {}

            def read(self, n=-1):
                return b"X" * len(CHUNKS[0])

            def close(self):
                pass

        info = {"image_url": "http://oscdn/x/BaseSystem.dmg", "image_token": "t"}
        with mock.patch.object(apple, "fetch_chunklist", lambda i: b"signed"),              mock.patch.object(apple, "parse_chunklist", lambda d: LIST),              mock.patch.object(apple, "_asset", lambda u, t, e=None: S()):
            with self.assertRaises(apple.AppleError) as e:
                apple.preflight(info)
        self.assertIn("signed hash", str(e.exception))
        self.assertIn("Nothing was erased", str(e.exception))


if __name__ == "__main__":
    unittest.main()
