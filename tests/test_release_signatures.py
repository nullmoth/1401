"""Updates from a newer release need a NullMoth signature, not only the SHA-256 the same release lists.

The 1401 Windows app runs as administrator and the NVIDIA driver package runs as root on the Mac. Both were accepted
when their bytes matched SHA256SUMS.txt from the same GitHub release, so whoever could replace a release's files could
replace both the file and its hash. p1401.release_sig verifies a detached Ed25519 signature against the release key."""
import base64
import hashlib
import os
import re
import tempfile
import unittest

from p1401 import nullmoth, release_sig

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = hashlib.sha256(b"test key, never a release key").digest()
KEY = release_sig.sign(b"", SEED)[1]


def sig(data):
    return base64.b64encode(release_sig.sign(data, SEED)[0])


class Ed25519(unittest.TestCase):
    # RFC 8032 section 7.1, tests 1 and 2
    VECTORS = [
        ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
         "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
         "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
        ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
         "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
         "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ]

    def test_rfc8032_vectors_sign_and_verify(self):
        for sk, pk, msg, want in self.VECTORS:
            s, pub = release_sig.sign(bytes.fromhex(msg), bytes.fromhex(sk))
            self.assertEqual(s.hex(), want)
            self.assertEqual(base64.b64decode(pub).hex(), pk)
            self.assertTrue(release_sig.verify(bytes.fromhex(msg), s, pub))

    def test_a_flipped_bit_or_another_key_fails(self):
        s, pub = release_sig.sign(b"package bytes", SEED)
        self.assertFalse(release_sig.verify(b"package bytez", s, pub))
        bad = bytearray(s); bad[40] ^= 1
        self.assertFalse(release_sig.verify(b"package bytes", bytes(bad), pub))
        self.assertFalse(release_sig.verify(b"package bytes", s, release_sig.PUBLIC_KEY))
        self.assertFalse(release_sig.verify(b"package bytes", "not base64!", pub))

    def test_the_release_key_is_the_one_the_mac_app_compiles_in(self):
        swift = open(os.path.join(HERE, "..", "mac", "Sources", "ReleaseSignature.swift"), encoding="utf-8").read()
        self.assertIn(f'publicKeyBase64 = "{release_sig.PUBLIC_KEY}"', swift)


class Updates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_an_unsigned_windows_app_is_refused(self):
        good = b"zip bytes"
        rel = ("9.9.9", "1401-Windows-9.9.9.zip", "https://x/w", hashlib.sha256(good).hexdigest())
        with self.assertRaises(RuntimeError):
            nullmoth.app_update("1.0.0", os.path.join(self.tmp.name, "a"), rel, lambda u, p: open(p, "wb").write(good))
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "a", "unpacked")))

    def test_a_windows_app_signed_for_other_bytes_is_refused(self):
        good = b"zip bytes"
        rel = ("9.9.9", "1401-Windows-9.9.9.zip", "https://x/w", hashlib.sha256(good).hexdigest(), "https://x/w.sig")
        fetch = lambda u, p: open(p, "wb").write(sig(b"other") if u.endswith(".sig") else good)  # noqa: E731
        with self.assertRaisesRegex(RuntimeError, "signature"):
            nullmoth.app_update("1.0.0", os.path.join(self.tmp.name, "b"), rel, fetch, sigkey=KEY)

    def test_an_unsigned_driver_package_never_reaches_the_app_folder_or_stick(self):
        data = b"driver package"
        rel = {"driver": ("nullmoth-nvidia-9.9.9.tar.gz", "https://x/p", hashlib.sha256(data).hexdigest()),
               "mac": None, "sigs": {}}
        d = os.path.join(self.tmp.name, "app")
        with self.assertRaises(RuntimeError):
            nullmoth.update([d], rel, lambda u, p: open(p, "wb").write(data))
        self.assertEqual([f for f in os.listdir(d) if not f.endswith(".part")], [])

    def test_a_signed_driver_package_is_placed(self):
        data = b"driver package"
        rel = {"driver": ("nullmoth-nvidia-9.9.9.tar.gz", "https://x/p", hashlib.sha256(data).hexdigest()),
               "mac": None, "sigs": {"nullmoth-nvidia-9.9.9.tar.gz.sig": "https://x/p.sig"}}
        d = os.path.join(self.tmp.name, "app")
        fetch = lambda u, p: open(p, "wb").write(sig(data) if u.endswith(".sig") else data)  # noqa: E731
        nullmoth.update([d], rel, fetch, sigkey=KEY)
        self.assertEqual(os.listdir(d), ["nullmoth-nvidia-9.9.9.tar.gz"])

    def test_latest_windows_names_the_signature(self):
        api = {"assets": [{"name": "1401-Windows-9.9.9.zip", "browser_download_url": "https://x/w"},
                          {"name": "1401-Windows-9.9.9.zip.sig", "browser_download_url": "https://x/w.sig"},
                          {"name": "SHA256SUMS.txt", "browser_download_url": "https://x/s"}]}
        rel = nullmoth.latest_windows(lambda u: api, lambda u: "0" * 64 + "  1401-Windows-9.9.9.zip\n")
        self.assertEqual(rel[4], "https://x/w.sig")
        self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", rel[3]))


if __name__ == "__main__":
    unittest.main()
