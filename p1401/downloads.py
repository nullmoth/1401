"""Bounded, verified HTTPS requests for build dependencies."""
import socket
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request


class DownloadError(RuntimeError):
    pass


def github_contents_url(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'https' or parts.hostname not in ('raw.githubusercontent.com', 'github.com') or parts.username or parts.password:
        return None
    fields = parts.path.lstrip('/').split('/')
    if len(fields) < 4:
        return None
    owner, repo = fields[:2]
    rest = fields[2:]
    if parts.hostname == 'github.com':
        if not rest or rest[0] != 'raw':
            return None
        rest = rest[1:]
    if rest[:2] in (['refs', 'heads'], ['refs', 'tags']):
        rest = rest[2:]
    if len(rest) < 2 or not all((owner, repo, rest[0])):
        return None
    ref, path = rest[0], '/'.join(rest[1:])
    return ('https://api.github.com/repos/' + urllib.parse.quote(owner, safe='') + '/' +
            urllib.parse.quote(repo, safe='') + '/contents/' +
            urllib.parse.quote(urllib.parse.unquote(path), safe='/') + '?' +
            urllib.parse.urlencode({'ref': urllib.parse.unquote(ref)}))


def github_release_metadata(url):
    parts = urllib.parse.urlsplit(url)
    fields = parts.path.lstrip('/').split('/')
    if (parts.scheme != 'https' or parts.hostname != 'github.com' or parts.username or parts.password or
            len(fields) != 6 or fields[2:4] != ['releases', 'download'] or not all(fields)):
        return None
    owner, repo, _, _, tag, filename = fields
    base = 'https://api.github.com/repos/' + urllib.parse.quote(owner, safe='') + '/' + urllib.parse.quote(repo, safe='')
    return base + '/releases/tags/' + urllib.parse.quote(urllib.parse.unquote(tag), safe=''), urllib.parse.unquote(tag), urllib.parse.unquote(filename)


def _release_asset_response(fetcher, metadata, headers, timeout):
    endpoint, tag, filename = metadata
    metadata_headers = dict(headers, Accept='application/vnd.github+json')
    metadata_headers['Accept-Encoding'] = 'identity'
    with urllib.request.urlopen(urllib.request.Request(endpoint, headers=metadata_headers),
                                timeout=timeout, context=fetcher.ssl_context) as response:
        body = response.read(2 * 1024 * 1024 + 1)
    if len(body) > 2 * 1024 * 1024:
        raise DownloadError('GitHub release metadata exceeds the build dependency limit.')
    try:
        release = json.loads(body)
        assets = release['assets']
        if release['tag_name'] != tag or release.get('draft') or not isinstance(assets, list):
            raise ValueError('release differs')
        matches = [asset for asset in assets if isinstance(asset, dict) and asset.get('name') == filename and
                   asset.get('state') == 'uploaded' and type(asset.get('id')) is int and asset['id'] > 0]
        if len(matches) != 1:
            raise ValueError('asset missing or ambiguous')
    except (TypeError, KeyError, ValueError) as error:
        raise DownloadError('The official GitHub release does not identify the exact requested dependency asset. '
                            'Check its release URL before rebuilding.') from error
    asset_url = endpoint.split('/releases/tags/', 1)[0] + '/releases/assets/' + str(matches[0]['id'])
    asset_headers = dict(headers, Accept='application/octet-stream')
    response = urllib.request.urlopen(urllib.request.Request(asset_url, headers=asset_headers),
                                      timeout=timeout, context=fetcher.ssl_context)
    if 'json' in (response.getheader('Content-Type') or '').lower():
        response.close()
        raise DownloadError('GitHub returned release metadata instead of the dependency file. Rebuild after the asset is available.')
    return response


def make_request(fetcher, url, timeout=20):
    """Use the official contents endpoint when the raw host is unreachable."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
        raise DownloadError('Build dependencies require an HTTPS URL without credentials.')
    fallback = github_contents_url(url)
    release_metadata = github_release_metadata(url)
    if release_metadata:
        fallback = release_metadata[0]
    endpoints = [url] + ([fallback] if fallback else [])
    for index, endpoint in enumerate(endpoints):
        request_host = urllib.parse.urlsplit(endpoint).hostname
        headers = dict(fetcher.request_headers)
        headers['Accept-Encoding'] = 'gzip, deflate'
        if index:
            headers = {k: v for k, v in headers.items() if k.lower() not in ('authorization', 'cookie', 'host')}
            headers['Accept'] = 'application/vnd.github.raw+json'
        attempts = 1 if fallback and index == 0 else 3
        for attempt in range(attempts):
            try:
                if index and release_metadata:
                    return _release_asset_response(fetcher, release_metadata, headers, min(max(timeout, 10), 30))
                return urllib.request.urlopen(urllib.request.Request(endpoint, headers=headers),
                                              timeout=min(max(timeout, 10), 30), context=fetcher.ssl_context)
            except urllib.error.HTTPError as error:
                code = error.code
                error.close()
                if code not in (408, 429, 500, 502, 503, 504):
                    raise DownloadError(f'Dependency request to {request_host} returned HTTP {code}. '
                                        'The file or release URL must be checked before rebuilding.') from error
                reason = f'HTTP {code}'
            except (ssl.SSLError, urllib.error.URLError, OSError) as error:
                cause = error.reason if isinstance(error, urllib.error.URLError) else error
                if isinstance(cause, ssl.SSLError):
                    raise DownloadError('Dependency TLS verification failed. Check the system clock, '
                                        'trusted certificates and HTTPS proxy configuration.') from error
                if not isinstance(error, (urllib.error.URLError, socket.timeout, ConnectionError, socket.gaierror)):
                    raise
                reason = type(cause).__name__
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
    raise DownloadError(f'Could not download from {request_host} ({reason}). '
                        'Check the network or Windows proxy settings, then rebuild.')


def verified_context(self):
    from . import tls
    return tls.context()
