"""A stick that read back a few chunks wrong gets those chunks written once more, each re-fetched and checked against
Apple's signed hashes; a stick that keeps losing data still fails, and a re-fetched chunk that fails its hash is refused."""
import hashlib
import os
import tempfile
import unittest

from p1401 import apple


def image(n=6, size=4096):
    parts = [os.urandom(size) for _ in range(n)]
    return parts, [(size, hashlib.sha256(p).digest()) for p in parts]


class RepairWritten(unittest.TestCase):
    def setUp(self):
        self.parts, self.chunks = image()
        self.dir = tempfile.TemporaryDirectory()
        self.img = os.path.join(self.dir.name, "BaseSystem.dmg")
        with open(self.img, "wb") as fh:
            fh.write(b"".join(self.parts))

    def tearDown(self):
        self.dir.cleanup()

    def corrupt(self, *numbers):
        with open(self.img, "r+b") as fh:
            for i in numbers:
                fh.seek((i - 1) * 4096 + 100)
                fh.write(b"\xff" * 16)

    def fetch(self, offset, size):
        return self.parts[offset // 4096][:size]

    def plain(self, path):
        with open(path, "rb") as fh:
            yield fh.read()

    def test_a_few_bad_chunks_are_written_again_and_pass(self):
        self.corrupt(2, 5)
        bad = apple.verify_written(self.img, self.chunks, self.plain)
        self.assertEqual(bad, [2, 5])
        self.assertEqual(apple.repair_written({}, self.img, self.chunks, bad, fetch=self.fetch, read=self.plain), [])

    def test_a_stick_that_keeps_losing_data_still_fails(self):
        self.corrupt(3)

        def lossy(path):
            with open(path, "rb") as fh:
                data = bytearray(fh.read())
            data[2 * 4096 + 7] ^= 0xFF  # chunk 3 reads back wrong every time
            yield bytes(data)
        self.assertEqual(apple.repair_written({}, self.img, self.chunks, [3], fetch=self.fetch, read=lossy), [3])

    def test_a_refetched_chunk_that_fails_apples_hash_is_refused(self):
        self.corrupt(4)
        with self.assertRaises(apple.AppleError):
            apple.repair_written({}, self.img, self.chunks, [4], fetch=lambda o, s: b"\0" * s, read=self.plain)

    def test_a_tail_longer_than_the_chunklist_is_not_repaired(self):
        self.assertEqual(apple.repair_written({}, self.img, self.chunks, [7], fetch=self.fetch, read=self.plain), [7])

    def test_a_local_image_is_the_source_for_its_own_repair(self):
        src = os.path.join(self.dir.name, "src.dmg")
        with open(src, "wb") as fh:
            fh.write(b"".join(self.parts))
        self.corrupt(1)
        self.assertEqual(apple.repair_written({"local": True, "image_path": src}, self.img, self.chunks, [1],
                                              read=self.plain), [])


if __name__ == "__main__":
    unittest.main()
