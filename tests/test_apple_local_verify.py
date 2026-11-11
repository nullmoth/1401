"""A local recovery image is fully checked BEFORE the stick is erased, and a preflight sample is hashed.

The writer used to verify a local BaseSystem.dmg only while copying it, i.e. after the erase; a corrupt, unsigned or
wrong-version local image then cost the user their stick before it was refused. preflight() counted the bytes a server
returned without hashing them, so a proxy could pass it with any bytes.
"""
import hashlib
import os
import tempfile
import unittest
from unittest import mock

from p1401 import apple, usbwriter

CHUNKS = [os.urandom(64), os.urandom(32), os.urandom(16)]
IMAGE = b"".join(CHUNKS)
LIST = [(len(c), hashlib.sha256(c).digest()) for c in CHUNKS]
STICK = {"Number": 2, "FriendlyName": "aigo U350", "SerialNumber": "FC262A0B28EE2", "BusType": "USB",
         "Size": 125304832000}


def local(tmp, data=None, marker=None):
    open(os.path.join(tmp, "BaseSystem.chunklist"), "wb").write(b"signed")
    open(os.path.join(tmp, "BaseSystem.dmg"), "wb").write(IMAGE if data is None else data)
    if marker is not None:
        open(os.path.join(tmp, "BaseSystem.product.json"), "w", encoding="utf-8").write(marker)
    with mock.patch.object(apple, "parse_chunklist", lambda d: LIST):
        return apple.local_image(tmp, 25)


class VerifyLocal(unittest.TestCase):
    def test_every_chunk_is_checked_before_the_erase(self):
        with tempfile.TemporaryDirectory() as tmp:
            info = local(tmp)
            with mock.patch.object(apple, "parse_chunklist", lambda d: LIST):
                got = apple.verify_local(info)
        self.assertEqual(got["bytes"], len(IMAGE))
        self.assertEqual(got["chunks"], len(LIST))

    def test_a_flipped_byte_is_refused(self):
        bad = bytearray(IMAGE); bad[3] ^= 1
        with tempfile.TemporaryDirectory() as tmp:
            info = local(tmp, bytes(bad))
            with mock.patch.object(apple, "parse_chunklist", lambda d: LIST):
                with self.assertRaises(apple.AppleError) as e:
                    apple.verify_local(info)
        self.assertIn("Nothing was erased", str(e.exception))

    def test_a_cut_short_image_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            info = local(tmp, IMAGE[:-5])
            with mock.patch.object(apple, "parse_chunklist", lambda d: LIST):
                with self.assertRaises(apple.AppleError) as e:
                    apple.verify_local(info)
        self.assertIn("cut short", str(e.exception))


class VersionMarker(unittest.TestCase):
    def test_an_image_marked_for_another_macos_is_refused_before_the_erase(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(apple.AppleError) as e:
                local(tmp, marker='{"product": "macOS 15", "darwin": 24}')
        self.assertIn("Darwin 24", str(e.exception))
        self.assertIn("Nothing was erased", str(e.exception))

    def test_a_matching_or_missing_marker_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            info = local(tmp, marker='{"product": "macOS 26", "darwin": 25}')
        self.assertTrue(info["version_known"])
        self.assertEqual(info["product"], "macOS 26")
        with tempfile.TemporaryDirectory() as tmp:
            info = local(tmp)
        self.assertFalse(info["version_known"])


class BeforeErase(unittest.TestCase):
    def test_a_local_image_that_fails_verification_stops_before_write(self):
        with tempfile.TemporaryDirectory() as root, \
             mock.patch.object(usbwriter, "list_disks", return_value=[STICK]), \
             mock.patch.object(usbwriter, "eligible", return_value=(True, [])), \
             mock.patch("p1401.machine_handoff.verified", return_value=None), \
             mock.patch("p1401.netsupport.needs_local_image", return_value=False), \
             mock.patch("p1401.apple.local_image", return_value={"local": True, "name": "local"}), \
             mock.patch("p1401.apple.verify_local", side_effect=apple.AppleError("chunk 2 fails Apple's hash")), \
             mock.patch.object(usbwriter, "write") as write, \
             mock.patch("builtins.print") as out:
            rc = usbwriter.cli_write(["2", "efi", "25"])
        self.assertEqual(rc, 1)
        write.assert_not_called()
        line = " ".join(str(c.args[0]) for c in out.call_args_list if c.args)
        self.assertIn("1401-RECOVERY-IMAGE", line)
        self.assertIn("nothing has been erased", line)


if __name__ == "__main__":
    unittest.main()
