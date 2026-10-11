"""The macOS image is read back from the stick after writing and checked against Apple's chunklist: a stick that changed
or dropped data stops the write instead of booting to "OCB: DMG has been altered" (1.0.22 / 1.2.0 startup logs)."""
import hashlib
import os
import tempfile
import unittest

from p1401 import apple


def chunked(data, size):
    return [(len(data[i:i + size]), hashlib.sha256(data[i:i + size]).digest()) for i in range(0, len(data), size)]


class ReadBack(unittest.TestCase):
    def setUp(self):
        self.data = os.urandom(5 * 4096 + 123)
        self.chunks = chunked(self.data, 4096)
        fd, self.img = tempfile.mkstemp(); os.close(fd)

    def write(self, b):
        with open(self.img, "wb") as fh:
            fh.write(b)

    def test_an_intact_image_reads_back_clean_in_any_block_size(self):
        self.write(self.data)
        self.assertEqual(apple.verify_written(self.img, self.chunks), [])
        small = lambda p: iter([self.data[i:i + 1000] for i in range(0, len(self.data), 1000)])
        self.assertEqual(apple.verify_written(self.img, self.chunks, read=small), [])

    def test_one_flipped_byte_names_its_chunk(self):
        b = bytearray(self.data); b[2 * 4096 + 7] ^= 1
        self.write(bytes(b))
        self.assertEqual(apple.verify_written(self.img, self.chunks), [3])

    def test_a_short_image_and_a_long_one_both_fail(self):
        self.write(self.data[:-500])   # 500 bytes short: the 123-byte last chunk is gone and chunk 5 is cut
        self.assertEqual(apple.verify_written(self.img, self.chunks), [5])
        self.write(self.data + b"extra")
        self.assertEqual(apple.verify_written(self.img, self.chunks), [7])


if __name__ == "__main__":
    unittest.main()
