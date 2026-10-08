"""Reject self-consistent dependency caches that cannot produce an EFI."""
import json
import os
import plistlib
from xml.parsers.expat import ExpatError


OPENCORE_FILES = ('EFI/BOOT/BOOTx64.efi', 'EFI/OC/OpenCore.efi', 'EFI/OC/config.plist')
CONFIG_SECTIONS = ('ACPI', 'Booter', 'DeviceProperties', 'Kernel', 'Misc', 'NVRAM', 'PlatformInfo', 'UEFI')


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
