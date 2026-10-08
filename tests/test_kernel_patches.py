import copy
import sys
import unittest
from unittest.mock import Mock
from p1401 import engine
from p1401.downloads import DownloadError

sys.path.insert(0, engine.UPSTREAM)
from Scripts.gathering_files import gatheringFiles
from Scripts.config_prodigy import ConfigProdigy
from Scripts.datasets import kext_data
from Scripts.utils import Utils


class RequiredKernelPatches(unittest.TestCase):
    def setUp(self):
        engine._patient_downloads()
        self.gatherer = gatheringFiles.__new__(gatheringFiles)
        self.gatherer.fetcher = Mock()
        self.gatherer.utils = Mock()

    def test_failed_download_cannot_be_acknowledged_into_incomplete_efi(self):
        self.gatherer.fetcher.fetch_and_parse_content.side_effect = DownloadError('Dependency request failed')
        with self.assertRaises(DownloadError):
            self.gatherer.get_kernel_patches('Hyper Threading Patches', 'https://github.com/example/patches')
        self.gatherer.utils.request_input.assert_not_called()

    def test_missing_or_empty_patch_sets_stop_build(self):
        for body in (None, {}, {'Kernel': {}}, {'Kernel': {'Patch': []}}, {'Kernel': {'Patch': 'invalid'}}):
            with self.subTest(body=body):
                self.gatherer.fetcher.fetch_and_parse_content.return_value = body
                with self.assertRaises(DownloadError):
                    self.gatherer.get_kernel_patches('AMD Vanilla Patches', 'https://github.com/example/patches')
        self.gatherer.utils.request_input.assert_not_called()

    def test_cancellation_is_not_swallowed_into_an_empty_patch_list(self):
        self.gatherer.fetcher.fetch_and_parse_content.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.gatherer.get_kernel_patches('Hyper Threading Patches', 'https://github.com/example/patches')
        self.gatherer.utils.request_input.assert_not_called()

    def test_rerun_retrieves_patch_set_after_transient_failure(self):
        patches = [{'Identifier': 'kernel', 'Enabled': True, 'Find': b'find', 'Replace': b'data'}]
        self.gatherer.fetcher.fetch_and_parse_content.side_effect = [DownloadError('network'), {'Kernel': {'Patch': patches}}]
        with self.assertRaises(DownloadError):
            self.gatherer.get_kernel_patches('Hyper Threading Patches', 'https://github.com/example/patches')
        self.assertEqual(self.gatherer.get_kernel_patches('Hyper Threading Patches', 'https://github.com/example/patches'), patches)

    def test_selected_raptor_topology_patches_cannot_silently_disappear(self):
        prodigy = ConfigProdigy.__new__(ConfigProdigy)
        prodigy.g = self.gatherer
        prodigy.utils = Utils()
        selected = copy.deepcopy(kext_data.kexts)
        for kext in selected:
            kext.checked = kext.name == 'CpuTopologyRebuild'
        self.gatherer.hyper_threading_patches_url = 'https://github.com/b00t0x/CpuTopologyRebuild/raw/refs/heads/master/patches_ht.plist'
        self.gatherer.fetcher.fetch_and_parse_content.side_effect = DownloadError('network')
        with self.assertRaises(DownloadError):
            prodigy.load_kernel_patch('HM770', 'Intel', 'Raptor Lake-HX', '24', 'NVIDIA', {}, '24.0.0', selected, True)
        self.gatherer.fetcher.fetch_and_parse_content.assert_called_once_with(self.gatherer.hyper_threading_patches_url, 'plist')
        self.gatherer.utils.request_input.assert_not_called()


if __name__ == '__main__':
    unittest.main()
