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

    def test_a_file_written_wrong_once_is_copied_again_and_passes(self):
        target = self.destination / 'OC/OpenCore.efi'
        for mode in ('corrupted', 'missing'):
            with self.subTest(mode=mode):
                if mode == 'corrupted':
                    target.write_bytes(b'corruption')
                else:
                    target.unlink()
                usbwriter.verify_efi_copy(str(self.source), str(self.destination))
                self.assertEqual(target.read_bytes(), b'boot file')

    def test_a_stick_that_keeps_changing_a_file_is_not_ready_and_names_it(self):
        target = self.destination / 'OC/OpenCore.efi'
        target.write_bytes(b'corruption')
        def bad_copy(src, dst):
            pathlib.Path(dst).write_bytes(b'still wrong')
        with self.assertRaisesRegex(usbwriter.UsbError, r'OC.OpenCore\.efi.*stick is not ready.*antivirus'):
            usbwriter.verify_efi_copy(str(self.source), str(self.destination), copy=bad_copy)

    def test_a_copy_that_fails_again_is_not_ready(self):
        (self.destination / 'OC/OpenCore.efi').unlink()
        def refused(src, dst):
            raise PermissionError('held by a scanner')
        with self.assertRaisesRegex(usbwriter.UsbError, 'stick is not ready'):
            usbwriter.verify_efi_copy(str(self.source), str(self.destination), copy=refused)

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
