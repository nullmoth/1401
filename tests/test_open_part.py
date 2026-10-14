"""The stick's folder disappearing between being made and the image file being opened does not end the write (1.15 write
log: "FileNotFoundError: No such file or directory: 'D:\\com.apple.recovery.boot\\BaseSystem.dmg.part'" right after
the erase and the chunklist fetch). No network."""
import hashlib, io, os, shutil, tempfile, unittest
from unittest.mock import patch

from p1401 import apple

CHUNKS = [os.urandom(3000), os.urandom(1234)]
IMAGE = b"".join(CHUNKS)
LIST = [(len(c), hashlib.sha256(c).digest()) for c in CHUNKS]
INFO = {"image_url": "http://oscdn.apple.com/x/BaseSystem.dmg", "image_token": "t",
        "chunklist_url": "http://oscdn.apple.com/x/BaseSystem.chunklist", "chunklist_token": "t", "product": "test"}


class Stream(io.BytesIO):
    status = 200
    headers = {}


class OpenPart(unittest.TestCase):
    def download(self, t, chunklist):
        with patch.object(apple, "fetch_chunklist", chunklist), patch.object(apple, "parse_chunklist", lambda d: LIST), \
                patch.object(apple, "_asset", lambda *a, **k: Stream(IMAGE)), patch.object(apple.time, "sleep", lambda s: None):
            return apple.download(INFO, t)

    def test_a_folder_dropped_by_a_remount_is_made_again_and_the_image_lands(self):
        with tempfile.TemporaryDirectory() as t:
            def remounting_fetch(info):  # the stick re-mounts while the chunklist is fetched: the folder is gone
                shutil.rmtree(os.path.join(t, "com.apple.recovery.boot"))
                return b"cl"
            out = self.download(t, remounting_fetch)
            self.assertEqual(open(out["image"], "rb").read(), IMAGE)
            self.assertEqual(open(out["chunklist"], "rb").read(), b"cl")

    def test_negative_control_a_stick_that_never_comes_back_still_fails_loudly(self):
        with tempfile.TemporaryDirectory() as t:
            gone = os.path.join(t, "stick")
            os.makedirs(gone)
            def vanished_fetch(info):
                shutil.rmtree(gone)
                return b"cl"
            with self.assertRaises(FileNotFoundError):
                self.download(gone, vanished_fetch)


if __name__ == "__main__":
    unittest.main()
