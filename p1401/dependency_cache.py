"""Reject self-consistent dependency caches that cannot produce an EFI."""
import json
import os
import plistlib
import time
from xml.parsers.expat import ExpatError


OPENCORE_FILES = ('EFI/BOOT/BOOTx64.efi', 'EFI/OC/OpenCore.efi', 'EFI/OC/config.plist')
CONFIG_SECTIONS = ('ACPI', 'Booter', 'DeviceProperties', 'Kernel', 'Misc', 'NVRAM', 'PlatformInfo', 'UEFI')


def tolerate_cache_locks(utils, cache_root):
    """Retry only Windows sharing/lock violations while clearing this build's cache."""
    if getattr(utils, '_1401_cache_locks', False):
        return
    original = utils.create_folder
    root = os.path.normcase(os.path.abspath(cache_root))

    def create_folder(path, remove_content=False):
        target = os.path.normcase(os.path.abspath(path))
        inside = target == root or target.startswith(root + os.sep)
        for attempt in range(4):
            try:
                return original(path, remove_content=remove_content)
            except PermissionError as error:
                if not inside or not remove_content or getattr(error, 'winerror', None) not in (32, 33):
                    raise
                if attempt == 3:
                    raise RuntimeError('The dependency cache is still locked by another process. '
                                       'Close other 1401 windows or programs using the cache, then rebuild. '
                                       'The EFI was not completed.') from error
                time.sleep(0.5 * (2 ** attempt))

    utils.create_folder = create_folder
    utils._1401_cache_locks = True


def harden(checker):
    if getattr(checker, '_1401_complete_cache', False):
        return
    original = checker.verify_folder_integrity

    def verify(folder, manifest_path=None):
        valid, issues = original(folder, manifest_path)
        if not valid:
            return valid, issues
        manifest_path = manifest_path or os.path.join(folder, 'manifest.json')
        try:
            with open(manifest_path, encoding='utf-8') as stream:
                manifest = json.load(stream)
            if not manifest:
                return False, {'incomplete': ['Dependency cache contains no files.']}
            if os.path.basename(os.path.normpath(folder)).lower() == 'opencorepkg':
                missing = [path for path in OPENCORE_FILES if not os.path.isfile(os.path.join(folder, path))]
                if missing:
                    return False, {'incomplete': missing}
                with open(os.path.join(folder, 'EFI', 'OC', 'config.plist'), 'rb') as stream:
                    config = plistlib.load(stream)
                if not isinstance(config, dict) or any(not isinstance(config.get(key), dict) for key in CONFIG_SECTIONS):
                    return False, {'incomplete': ['The OpenCore configuration template is invalid.']}
        except (OSError, ValueError, plistlib.InvalidFileException, ExpatError):
            return False, {'incomplete': ['The dependency manifest or OpenCore template could not be read.']}
        return valid, issues

    checker.verify_folder_integrity = verify
    checker._1401_complete_cache = True
