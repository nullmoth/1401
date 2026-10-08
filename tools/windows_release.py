"""Prepare and package a Windows candidate from verified release inputs."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import runpy
import shutil
import stat
import subprocess
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

REPO = Path(__file__).resolve().parents[1]
INPUTS = REPO / 'windows' / 'release-inputs.json'


def sha(path):
    result = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def version():
    value = ET.parse(REPO / 'windows/App/App.csproj').findtext('./PropertyGroup/Version')
    if not value or not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise RuntimeError('Invalid Windows application version.')
    manifest = ET.parse(REPO / 'windows/App/app.manifest')
    identity = manifest.find('{urn:schemas-microsoft-com:asm.v1}assemblyIdentity')
    if identity is None or identity.attrib.get('version') != value + '.0':
        raise RuntimeError('The application and manifest versions differ.')
    return value


def get(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'https' or parts.username or parts.password:
        raise RuntimeError('Release inputs require HTTPS.')
    headers = {'User-Agent': 'NullMothBuildVerification/1.0'}
    if parts.hostname == 'api.github.com' and os.environ.get('GH_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GH_TOKEN']
    request = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(request, timeout=60)


def download(url, digest, destination):
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise RuntimeError('A verified SHA-256 is required for every release input.')
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and sha(destination) == digest:
        return destination
    partial = destination.with_suffix(destination.suffix + '.part')
    try:
        with get(url) as response, open(partial, 'wb') as output:
            shutil.copyfileobj(response, output)
        if sha(partial) != digest:
            raise RuntimeError('Release input checksum mismatch: ' + destination.name)
        os.replace(partial, destination)
    finally:
        partial.unlink(missing_ok=True)
    return destination


def extract_baseline(archive, destination):
    destination = Path(destination)
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            original = entry.orig_filename
            name = PurePosixPath(original)
            if (not name.parts or name.parts[0] != '1401' or name.is_absolute() or
                    '..' in name.parts or '\\' in original or ':' in original or
                    stat.S_ISLNK(entry.external_attr >> 16)):
                raise RuntimeError('Unsafe baseline ZIP member.')
        source.extractall(destination)


def deterministic_zip(root, destination):
    root = Path(root)
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(root.rglob('*'), key=lambda item: item.relative_to(root).as_posix()):
            if path.is_symlink():
                raise RuntimeError('Windows package contains a symlink.')
            if not path.is_file():
                continue
            name = root.name + '/' + path.relative_to(root).as_posix()
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | (0o755 if path.suffix == '.exe' else 0o644)) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, path.read_bytes(), compresslevel=9)


def validate_companion_release(release, inputs):
    if release.get('draft') or release.get('tag_name') != inputs['driver_release']:
        raise RuntimeError('The bundled companion must be published with the exact reviewed tag.')
    # Candidate assembly can use an explicitly reviewed companion before the paired
    # stable release. Downloaded asset digests still require all three independent pins.
    if release.get('prerelease') and inputs.get('companion_prerelease_reviewed') is not True:
        raise RuntimeError('The bundled companion is still in installation review.')


def prepare(args):
    inputs = json.loads(INPUTS.read_text())
    package = runpy.run_path(str(REPO / 'p1401/nullmoth.py'))['PACKAGE']
    release_prefix = 'https://github.com/nullmoth/nvidia-macos-driver/releases/download/' + inputs['driver_release'] + '/'
    if package['url'] != release_prefix + package['name']:
        raise RuntimeError('The source driver package pin must match the reviewed driver release.')
    if not re.fullmatch(r'[0-9a-f]{64}', inputs.get('mac_sha256') or ''):
        raise RuntimeError('The final Mac companion SHA-256 must be reviewed and pinned before building.')
    stage = Path(args.stage).resolve()
    if stage.exists() and any(stage.iterdir()):
        raise RuntimeError('The candidate staging directory must be empty.')
    stage.mkdir(parents=True, exist_ok=True)
    cache = Path(args.cache).resolve()
    baseline = download(inputs['baseline_url'], inputs['baseline_sha256'], cache / 'baseline.zip')
    extract_baseline(baseline, stage)
    root = stage / '1401'
    compiled = Path(args.compiled).resolve()
    if not compiled.is_file() or compiled.read_bytes()[:2] != b'MZ':
        raise RuntimeError('A newly compiled Windows executable is required.')
    shutil.copyfile(compiled, root / '1401.exe')
    app = root / 'engine/app'
    shutil.rmtree(app / 'p1401')
    shutil.copytree(REPO / 'p1401', app / 'p1401', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    runpy.run_path(str(REPO / 'tools/build_cpu_helper.py'))['build'](REPO, app / 'bin')
    tracked = subprocess.check_output(['git', '-C', str(REPO), 'ls-files', '-z', 'upstream'], text=True).split('\0')
    for relative in filter(None, tracked):
        target = app / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, target)
    with get('https://api.github.com/repos/nullmoth/nvidia-macos-driver/releases/tags/' + inputs['driver_release']) as response:
        release = json.load(response)
    validate_companion_release(release, inputs)
    assets = {asset['name']: asset for asset in release.get('assets', [])}
    sums_asset = assets.get('SHA256SUMS.txt')
    if not sums_asset or not (sums_asset.get('digest') or '').startswith('sha256:'):
        raise RuntimeError('The driver release must have a server-hashed checksum manifest.')
    sums_path = download(sums_asset['browser_download_url'], sums_asset['digest'][7:], cache / 'driver-sums.txt')
    sums = {fields[-1]: fields[0] for line in sums_path.read_text().splitlines()
            if len(fields := line.split()) == 2 and re.fullmatch(r'[0-9a-f]{64}', fields[0])}
    for name, expected in [(package['name'], package['sha256']), (inputs['mac_asset'], inputs['mac_sha256'])]:
        asset = assets.get(name)
        if not asset or asset.get('digest') != 'sha256:' + expected or sums.get(name) != expected:
            raise RuntimeError('Source pin, release asset digest and checksum manifest disagree: ' + name)
    bundle = root / 'NullMoth'
    for path in bundle.iterdir():
        if re.fullmatch(r'(?:1401-Mac-.*\.zip|nullmoth-nvidia-.*\.tar\.gz)', path.name):
            path.unlink()
    for name, expected in [(package['name'], package['sha256']), (inputs['mac_asset'], inputs['mac_sha256'])]:
        download(assets[name]['browser_download_url'], expected, bundle / name)
    (root / 'README.txt').write_text('1401 ' + version() + ' for Windows.\nKeep the entire 1401 folder together.\n'
                                  'Run 1401.exe to check the PC and build its macOS installation setup.\n'
                                  'Hardware support depends on the detected devices; this package does not qualify every machine.\n')
    fixtures = cache / 'fixtures'
    fixtures.mkdir(parents=True, exist_ok=True)
    download(inputs['opencore_url'], inputs['opencore_sha256'], fixtures / 'OpenCore-1.0.8-RELEASE.zip')
    fetch_fixture(inputs['fixture_slug'], fixtures)
    print('Verified Windows candidate prepared.')


def fetch_fixture(slug, destination):
    manifest = json.loads((REPO / 'tests/corpus/manifest.json').read_text())
    selected = next(entry for entry in manifest['entries'] if entry['slug'] == slug)
    commit = selected['commit']
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise RuntimeError('The public planning fixture must be commit-pinned.')
    base = 'https://api.github.com/repos/' + selected['repo'] + '/contents/'
    proof = {'slug': slug, 'repo': selected['repo'], 'commit': commit, 'files': {}}
    paths = [selected['path'].strip('/') + '/Report.json', selected['path'].strip('/') + '/ACPI']
    for path in paths:
        with get(base + urllib.parse.quote(path, safe='/') + '?ref=' + commit) as response:
            listing = json.load(response)
        entries = listing if isinstance(listing, list) else [listing]
        for entry in entries:
            name = entry['name']
            if entry.get('type') != 'file' or not (name == 'Report.json' or name.lower().endswith(('.aml', '.dat'))):
                continue
            if name != Path(name).name or ':' in name or '\\' in name or entry.get('size', 0) > 4 * 1024 * 1024:
                raise RuntimeError('Invalid planning fixture member.')
            if not re.fullmatch(r'[0-9a-f]{40}', entry['sha']):
                raise RuntimeError('Invalid planning fixture Git object ID.')
            blob_url = 'https://api.github.com/repos/' + selected['repo'] + '/git/blobs/' + entry['sha']
            with get(blob_url) as response:
                blob = json.load(response)
            if blob.get('encoding') != 'base64' or blob.get('sha') != entry['sha'] or blob.get('size', 0) > 4 * 1024 * 1024:
                raise RuntimeError('Invalid planning fixture Git blob response.')
            data = base64.b64decode(''.join(blob['content'].split()), validate=True)
            if len(data) != blob.get('size') or len(data) > 4 * 1024 * 1024 or hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != entry['sha']:
                raise RuntimeError('Planning fixture does not match its pinned Git object.')
            relative = name if name == 'Report.json' else 'ACPI/' + name
            target = Path(destination) / slug / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            proof['files'][relative] = hashlib.sha256(data).hexdigest()
    if 'Report.json' not in proof['files'] or not any(name.startswith('ACPI/') for name in proof['files']):
        raise RuntimeError('Planning fixture has no complete report and ACPI table set.')
    (Path(destination) / 'fixture-proof.json').write_text(json.dumps(proof, indent=2, sort_keys=True) + '\n')


def package(args):
    root = Path(args.stage).resolve() / '1401'
    evidence = json.loads(Path(args.evidence).read_text())
    if evidence.get('ok') is not True or evidence.get('version') != version():
        raise RuntimeError('Successful verification of this packaged version is required.')
    actual = {path.relative_to(root).as_posix(): sha(path) for path in sorted(root.rglob('*'))
              if path.is_file()}
    if actual != evidence.get('candidate_files'):
        raise RuntimeError('The candidate files changed after packaged verification.')
    for generated in (root / 'engine/app/upstream/OpCore-Simplify/OCK_Files', root / 'engine/app/upstream/OpCore-Simplify/Results'):
        if generated.exists():
            shutil.rmtree(generated)
    for path in root.rglob('*'):
        if path.name == '__pycache__' or path.suffix == '.pyc':
            raise RuntimeError('The candidate contains generated Python bytecode.')
    manifest_path = root / 'BUILD-MANIFEST.json'
    files = {path.relative_to(root).as_posix(): sha(path) for path in sorted(root.rglob('*'))
             if path.is_file() and path != manifest_path}
    manifest = {'version': version(), 'source_commit': subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip(),
                'release_inputs': json.loads(INPUTS.read_text()), 'verification_sha256': sha(args.evidence), 'files': files}
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / ('1401-Windows-' + version() + '.zip')
    deterministic_zip(root, archive)
    (output / 'SHA256SUMS.txt').write_text(sha(archive) + '  ' + archive.name + '\n')
    shutil.copyfile(args.evidence, output / 'windows-verification.json')
    print('Verified candidate ZIP created; release publication is a separate step.')


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    prepare_parser = commands.add_parser('prepare')
    prepare_parser.add_argument('--stage', required=True)
    prepare_parser.add_argument('--cache', required=True)
    prepare_parser.add_argument('--compiled', required=True)
    package_parser = commands.add_parser('package')
    package_parser.add_argument('--stage', required=True)
    package_parser.add_argument('--evidence', required=True)
    package_parser.add_argument('--output', required=True)
    args = parser.parse_args()
    prepare(args) if args.command == 'prepare' else package(args)


if __name__ == '__main__':
    main()
