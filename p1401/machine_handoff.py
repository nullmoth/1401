"""Carry verified build identity to the installer without asserting live machine identity."""
import hashlib
import json
import os
from . import nullmoth, report

NAME = '.machine-profile.json'


def sha256(path):
    value = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            value.update(block)
    return value.hexdigest()


def efi_hashes(build):
    root = os.path.join(build, 'EFI')
    if os.path.islink(root):
        raise RuntimeError('The EFI directory is a link; rebuild before creating the installer.')
    files = {}
    for folder, directories, names in os.walk(root, followlinks=False):
        if any(os.path.islink(os.path.join(folder, n)) for n in directories + names):
            raise RuntimeError('The EFI contains a link; rebuild before creating the installer.')
        for name in sorted(names):
            path = os.path.join(folder, name)
            files[os.path.relpath(path, root).replace(os.sep, '/')] = sha256(path)
    if not files or 'OC/config.plist' not in files:
        raise RuntimeError('The EFI is incomplete; rebuild before creating the installer.')
    return dict(sorted(files.items()))


def create(report_path, result):
    value = nullmoth.system_profile(result.hardware)
    value.update(schema=2, identity_status='build_bound_live_unverified',
                 hardware=report.diagnostic_hardware(result.hardware),
                 disabled_devices=dict(result.disabled_devices),
                 acpi_fingerprints=list(result.acpi_fingerprints),
                 scan_sha256=sha256(report_path), efi_sha256=efi_hashes(result.out_dir),
                 macos_version=result.macos_version, smbios=result.smbios,
                 qualification={'boot': 'unverified', 'graphics': 'unverified',
                                'usb_ports': 'mapping_required', 'network': 'unverified',
                                'fan_control': 'not_assessed', 'rgb_control': 'not_assessed'})
    path = os.path.join(result.out_dir, NAME)
    with open(path + '.part', 'w', encoding='utf-8') as stream:
        json.dump(value, stream, indent=1, sort_keys=True)
    os.replace(path + '.part', path)
    return value


def verified(build, report_path=None):
    path = os.path.join(build, NAME)
    if not os.path.isfile(path):
        raise RuntimeError('The build has no verified machine profile. Rebuild before writing the installer.')
    with open(path, encoding='utf-8') as stream:
        value = json.load(stream)
    if not isinstance(value, dict) or value.get('schema') != 2:
        raise RuntimeError('The machine profile is not a verified build profile. Rebuild before writing the installer.')
    if report_path and value.get('scan_sha256') != sha256(report_path):
        raise RuntimeError('The scan changed after the EFI was built. Rebuild for the current scan before erasing the stick.')
    if value.get('efi_sha256') != efi_hashes(build):
        raise RuntimeError('The EFI changed after its machine profile was recorded. Rebuild before erasing the stick.')
    return value


def copy_to_installer(value, root):
    folder = os.path.join(root, 'NullMoth')
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, 'system-profile.json')
    data = json.dumps(value, indent=1, sort_keys=True).encode('utf-8')
    with open(path + '.part', 'wb') as stream:
        stream.write(data)
    os.replace(path + '.part', path)
    with open(path, 'rb') as stream:
        if stream.read() != data:
            raise RuntimeError('The written machine profile did not match the build. The stick is not ready.')
