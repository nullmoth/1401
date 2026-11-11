"""Validation must use the dependency cache that produced the EFI's OpenCore files.

A fallback cache (OCK_Files-2) is normal when the base folder refuses writes. Validation used to read the base
folder's history and compare the EFI with a different OpenCore commit, failing with a false "OpenCore.efi differs"
invariant (the x570 corpus build did this).
"""
import os
import tempfile
import unittest
from unittest import mock

from p1401 import engine, validate


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


class Select(unittest.TestCase):
    def test_the_cache_holding_the_efi_release_is_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "OCK_Files")
            fallback = base + "-2"
            write(os.path.join(base, "OpenCorePkg", "EFI", "OC", "OpenCore.efi"), b"old release")
            write(os.path.join(fallback, "OpenCorePkg", "EFI", "OC", "OpenCore.efi"), b"new release")
            efi = os.path.join(tmp, "efi")
            write(os.path.join(efi, "EFI", "OC", "OpenCore.efi"), b"new release")
            with mock.patch.object(engine, "OCK_CACHE", base), \
                 mock.patch.object(engine, "ACTIVE_OCK_CACHE", base), \
                 mock.patch.object(validate, "CACHE", os.path.join(tmp, "cache")):
                validate._select_cache_for(efi)
                self.assertEqual(engine.ACTIVE_OCK_CACHE, fallback)

    def test_no_match_keeps_the_active_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, "OCK_Files")
            write(os.path.join(base, "OpenCorePkg", "EFI", "OC", "OpenCore.efi"), b"release")
            efi = os.path.join(tmp, "efi")
            write(os.path.join(efi, "EFI", "OC", "OpenCore.efi"), b"something else")
            with mock.patch.object(engine, "OCK_CACHE", base), \
                 mock.patch.object(engine, "ACTIVE_OCK_CACHE", base), \
                 mock.patch.object(validate, "CACHE", os.path.join(tmp, "cache")):
                validate._select_cache_for(efi)
                self.assertEqual(engine.ACTIVE_OCK_CACHE, base)


if __name__ == "__main__":
    unittest.main()
