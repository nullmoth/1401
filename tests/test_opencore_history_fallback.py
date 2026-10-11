"""OpenCorePkg missing from the engine's download history (it reused a cached zip): the validator finds the cached zip
whose SHA-256 Dortania's build list publishes. A cached zip with any other hash is never accepted."""
import hashlib
import os
import tempfile
import unittest
from unittest import mock

from p1401 import validate


class HistoryFallback(unittest.TestCase):
    def setUp(self):
        self.cache = tempfile.mkdtemp()
        self.zipbytes = b"opencore zip bytes"
        with open(os.path.join(self.cache, "OpenCore-1.0.9-DEBUG.zip"), "wb") as fh:
            fh.write(self.zipbytes)
        self.listing = {"OpenCorePkg": {"versions": [{"links": {"debug": "https://x/OpenCore-1.0.9-DEBUG.zip",
                                                                "release": "https://x/OpenCore-1.0.9-RELEASE.zip"},
                                                      "hashes": {"debug": {"sha256": hashlib.sha256(self.zipbytes).hexdigest()},
                                                                 "release": {"sha256": "0" * 64}}}]}}

    def test_the_cached_zip_dortania_lists_is_used(self):
        with mock.patch.object(validate, "CACHE", self.cache):
            url, sha = validate._opencore_from_builds(fetch=lambda u: self.listing)
        self.assertTrue(url.endswith("-DEBUG.zip"))
        self.assertEqual(sha, hashlib.sha256(self.zipbytes).hexdigest())

    def test_a_cached_zip_with_another_hash_is_refused(self):
        with open(os.path.join(self.cache, "OpenCore-1.0.9-DEBUG.zip"), "wb") as fh:
            fh.write(b"tampered")
        with mock.patch.object(validate, "CACHE", self.cache):
            with self.assertRaises(validate.ValidatorUnavailable):
                validate._opencore_from_builds(fetch=lambda u: self.listing)


if __name__ == "__main__":
    unittest.main()
