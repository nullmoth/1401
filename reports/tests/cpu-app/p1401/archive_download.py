"""Validate downloaded ZIP structure before replacing a dependency download."""
import functools
import hashlib
import os
import tempfile
import time
import urllib.parse
import zipfile
from .downloads import DownloadError


def _asset(url):
    name = urllib.parse.unquote(urllib.parse.urlsplit(url).path.rsplit('/', 1)[-1])
    if not name or len(name) > 96 or not name.isascii() or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-' for c in name):
        return 'dependency archive'
    return name


def harden(download):
    """Stage privately and retain the existing downloader's checksum policy."""
    @functools.wraps(download)
    def wrapped(fetcher, resource_url, destination_path, sha256_hash=None):
        if not str(destination_path).lower().endswith('.zip'):
            return download(fetcher, resource_url, destination_path, sha256_hash)
        parent = os.path.dirname(os.path.abspath(destination_path))
        for attempt in range(3):
            fd, temporary = tempfile.mkstemp(prefix='.dependency-', suffix='.partial', dir=parent)
            os.close(fd)
            try:
                if not download(fetcher, resource_url, temporary, sha256_hash):
                    return False
                try:
                    with zipfile.ZipFile(temporary) as archive: archive.infolist()
                except (zipfile.BadZipFile, EOFError):
                    digest = hashlib.sha256()
                    with open(temporary, 'rb') as stream:
                        for block in iter(lambda: stream.read(1024 * 1024), b''): digest.update(block)
                    detail = (f'Downloaded {_asset(resource_url)} is not a readable ZIP '
                              f'(bytes {os.path.getsize(temporary)}, SHA256 {digest.hexdigest()}). '
                              'No dependency archive was replaced. The response content and endpoint must be checked.')
                    if attempt == 2: raise DownloadError(detail) from None
                    print(detail + f' Retrying in {attempt + 1} s.')
                    time.sleep(attempt + 1)
                    continue
                os.replace(temporary, destination_path)
                return True
            finally:
                try: os.unlink(temporary)
                except FileNotFoundError: pass
        raise AssertionError('Archive retry loop did not return')
    return wrapped
