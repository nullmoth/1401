"""The Mac app's setup never picks a Windows (NTFS) partition as the OpenCore partition (driver issue #453): a copied
EFI folder there was chosen and its config backup failed, because macOS mounts NTFS read-only."""
import os
import pathlib
import subprocess
import tempfile
import unittest

SETUP = pathlib.Path(__file__).resolve().parents[1] / "mac/Resources/nullmoth-setup.sh"

# `diskutil info` as macOS prints it for each kind of partition the auto-discovery loop lists
INFO = {
    "disk2s3": "   File System Personality:  NTFS\n   Type (Bundle):             ntfs\n   Read-Only Volume:          Yes\n",
    "disk2s4": "   File System Personality:  UFSD_NTFS\n   Type (Bundle):             ufsd_NTFS\n",
    "disk3s1": "   File System Personality:  MS-DOS FAT32\n   Type (Bundle):             msdos\n",
    "disk0s1": "   File System Personality:  MS-DOS FAT32\n   Type (Bundle):             msdos\n   Partition Type: EFI\n",
}


def is_ntfs(dev):
    text = SETUP.read_text()
    start = text.index("is_ntfs() {")
    end = text.index("mount_efi() {", start)
    with tempfile.TemporaryDirectory() as d:
        fake = pathlib.Path(d, "diskutil")
        fake.write_text("#!/bin/bash\ncase \"$2\" in\n" + "".join(
            f"  {k}) printf '%s' '{v}';;\n" for k, v in INFO.items()) + "  *) exit 1;;\nesac\n")
        fake.chmod(0o755)
        r = subprocess.run(["/bin/bash", "-c", text[start:end] + f'\nis_ntfs {dev}'], env={**os.environ, "PATH": d + ":/usr/bin:/bin"})
        return r.returncode == 0


class SetupSkipsNtfs(unittest.TestCase):
    def test_an_ntfs_partition_is_skipped(self):
        self.assertTrue(is_ntfs("disk2s3"))
        self.assertTrue(is_ntfs("disk2s4"))  # a third-party NTFS driver

    def test_a_fat32_stick_and_an_esp_are_still_candidates(self):
        self.assertFalse(is_ntfs("disk3s1"))
        self.assertFalse(is_ntfs("disk0s1"))

    def test_a_partition_diskutil_cannot_describe_is_not_skipped(self):
        self.assertFalse(is_ntfs("disk9s9"))

    def test_the_discovery_loop_uses_it_before_mounting(self):
        text = SETUP.read_text()
        loop = text[text.index("# OpenCore can live on an EFI partition or on any FAT32 partition"):]
        loop = loop[:loop.index("done")]
        self.assertLess(loop.index("is_ntfs \"$d\""), loop.index("mount_efi \"$d\""))


if __name__ == "__main__":
    unittest.main()
