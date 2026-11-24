"""The ACPI compiler (iasl) on Windows is a pinned, hash-checked ACPICA release.

The engine downloads iasl.exe the first time it reads a PC's ACPI tables, from a link written into its code
(ACPICA 20251212), with no hash and no mirror. 1401 3.0 logs: nine PCs stopped with "iasl crashed on this DSDT
(exit 3221225477 = 0xc0000005)" and then "dsdt.aml could not be disassembled". Their uploaded tables were run through
three versions: 20251212 crashes on one of them (segfault, measured on macOS too), 20200925 and 20260408 read all of
them. The pin is ACPICA 20260408, whose GitHub release digest matches the hash below. ACPICA is BSD-3-Clause OR
GPL-2.0, so the mirror may carry it for networks where GitHub fails.

An iasl.exe from an earlier download that is not the pinned one is replaced, so an app folder that already holds the
crashing version does not keep using it."""
import hashlib
import os

URL = "https://github.com/acpica/acpica/releases/download/20260408/iasl-win-20260408.zip"
ZIP_SHA256 = "121f5e4f30b1df63d09052294e4a605d4dee2dfb9599fa24af4ac6015df02b70"
EXE_SHA256 = "739c597bcee4563f18d13e73b2051bb661707713e6154cf5712a1b7eef4a5df9"
VERSION = "20260408"


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stale(path):
    """True when path is an iasl.exe that is not the pinned build (unreadable counts as stale)."""
    try:
        return os.path.isfile(path) and _sha256(path) != EXE_SHA256
    except OSError:
        return True


def install(dsdt_cls, platform):
    """Point the engine's Windows iasl at the pinned release and check the archive's hash on download."""
    if getattr(dsdt_cls, "_1401_iasl_pin", False):
        return
    dsdt_cls.get_latest_iasl = lambda self: URL

    download = dsdt_cls._download_and_extract

    def _download_and_extract(self, temp, url):
        if url != URL:
            return download(self, temp, url)
        fetcher = self.fetcher
        plain = fetcher.download_and_save_file

        def checked(resource_url, destination_path, sha256_hash=None):
            if resource_url == URL:
                sha256_hash = ZIP_SHA256
            return plain(resource_url, destination_path, sha256_hash)
        fetcher.download_and_save_file = checked
        try:
            return download(self, temp, url)
        finally:
            fetcher.download_and_save_file = plain
    dsdt_cls._download_and_extract = _download_and_extract

    check = dsdt_cls.check_iasl

    def check_iasl(self, legacy=False, try_downloading=True):
        if platform == "win32" and not legacy and try_downloading:
            here = os.path.dirname(os.path.realpath(check.__code__.co_filename))
            exe = os.path.join(here, "iasl.exe")
            if stale(exe):
                print(f"Replacing iasl.exe with ACPICA {VERSION} (the earlier version crashes on some firmware tables).")
                try:
                    os.remove(exe)
                except OSError as error:
                    print(f"Could not replace the old iasl.exe ({type(error).__name__}: {error}); using it.")
        return check(self, legacy=legacy, try_downloading=try_downloading)
    dsdt_cls.check_iasl = check_iasl
    dsdt_cls._1401_iasl_pin = True
