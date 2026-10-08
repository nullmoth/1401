import pathlib
import shutil
import tempfile
import unittest
from unittest.mock import patch
from p1401 import usbwriter


class UsbEfiVerification(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.source = self.root / 'source'
        self.destination = self.root / 'written'
        (self.source / 'OC').mkdir(parents=True)
        (self.source / 'OC/OpenCore.efi').write_bytes(b'boot file')
        shutil.copytree(self.source, self.destination)

    def test_matching_written_efi_passes_readback(self):
        usbwriter.verify_efi_copy(str(self.source), str(self.destination))

    def test_missing_or_corrupted_written_efi_is_not_ready(self):
        target = self.destination / 'OC/OpenCore.efi'
        for mode in ('corrupted', 'missing'):
            with self.subTest(mode=mode):
                if mode == 'corrupted':
                    target.write_bytes(b'corruption')
                else:
                    target.unlink()
                with self.assertRaisesRegex(usbwriter.UsbError, 'stick is not ready'):
                    usbwriter.verify_efi_copy(str(self.source), str(self.destination))

    def test_invalid_efi_is_refused_before_disk_commands(self):
        disk = {'Number': 3, 'FriendlyName': 'USB fixture', 'BusType': 'USB', 'Size': 16 * 10**9,
                'IsBoot': False, 'IsSystem': False, 'IsOffline': False, 'IsReadOnly': False, 'PartitionStyle': 'MBR'}
        with patch('p1401.validate.validate', return_value={'ok': False, 'invariants': ['mixed boot files']}), patch.object(usbwriter, '_ps') as commands, patch('p1401.rawdisk.wipe_mbr_fat32') as wipe:
            with self.assertRaisesRegex(usbwriter.UsbError, 'before erasing'):
                usbwriter.write(disk, str(self.source), {})
            commands.assert_not_called()
            wipe.assert_not_called()


if __name__ == '__main__':
    unittest.main()
