"""A chunklist a network delivered gzip-compressed is unpacked before its signature is checked; a compressed file that is
not Apple's still fails the signature check, and an oversized one is refused."""
import gzip
import unittest

from p1401 import apple


class GzipChunklist(unittest.TestCase):
    def test_plain_bytes_pass_through(self):
        self.assertEqual(apple.unwrap_chunklist(b"CNKL1234"), b"CNKL1234")

    def test_gzip_is_unpacked(self):
        self.assertEqual(apple.unwrap_chunklist(gzip.compress(b"CNKL" + b"x" * 500)), b"CNKL" + b"x" * 500)

    def test_unpacked_bytes_still_need_apples_signature(self):
        with self.assertRaises(apple.AppleError):
            apple.parse_chunklist(apple.unwrap_chunklist(gzip.compress(b"not a chunklist at all" * 10)))

    def test_a_huge_unpack_is_refused(self):
        with self.assertRaises(apple.AppleError):
            apple.unwrap_chunklist(gzip.compress(b"\0" * (2 << 20)))


if __name__ == "__main__":
    unittest.main()
