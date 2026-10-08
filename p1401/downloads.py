"""Bounded, verified HTTPS requests for build dependencies."""
import socket
import math
from email.utils import parsedate_to_datetime
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request


class DownloadError(RuntimeError):
    pass


# Header values are diagnostic inputs, never text for the log.
_MAX_HEADER = 128
_MAX_WAIT = 7 * 24 * 60 * 60


def _header(headers, name):
    try:
        values = headers.get_all(name) if hasattr(headers, 'get_all') else None
        if values is not None:
            if len(values) != 1:
                return None
            value = values[0]
        else:
            value = headers.get(name)
            if value is None:
                value = headers.get({'x-ratelimit-remaining': 'X-RateLimit-Remaining',
                                     'x-ratelimit-reset': 'X-RateLimit-Reset',
                                     'retry-after': 'Retry-After'}.get(name, name.title()))
        if (not isinstance(value, str) or len(value) > _MAX_HEADER or
                not value.isascii() or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            return None
        return value.strip()
    except (AttributeError, TypeError):
        return None


def _unsigned(value, maximum=9999999999):
    if not isinstance(value, str) or not 1 <= len(value) <= 10 or not value.isascii() or not value.isdecimal():
        return None
    number = int(value)
    return number if number <= maximum else None


def _now(value):
    value = time.time() if value is None else value
    if type(value) not in (int, float) or not 0 <= value <= 9999999999 or not math.isfinite(value):
        return None
    return value


def _retry_delay(value, now):
    if not isinstance(value, str) or len(value) > _MAX_HEADER or not value.isascii():
        return None
    number = _unsigned(value)
    if number is not None:
        return number
    if value is None or now is None:
        return None
    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            return None
        return max(0, math.ceil(date.timestamp() - now))
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _wait_message(wait):
    if wait is None:
        return 'The retry time is unavailable; wait before rebuilding.'
    if wait > _MAX_WAIT:
        return 'The requested delay exceeds the supported diagnostic window; retry later.'
    return f'Wait at least {wait} s before rebuilding.'


def github_rate_limit(host, code, headers, now=None):
    """Use bounded GitHub rate headers without asserting dependency validity."""
    if not isinstance(host, str) or len(host) > 253:
        return None
    host = host.lower()
    if (code not in (403, 429) or
            not (host == 'github.com' or host.endswith('.github.com')) or
            any(not label or len(label) > 63 or not label.isascii() or
                not all(c.isalnum() or c == '-' for c in label) or label.startswith('-') or label.endswith('-')
                for label in host.split('.'))):
        return None
    current = _now(now)
    remaining = _header(headers, 'x-ratelimit-remaining')
    reset = _unsigned(_header(headers, 'x-ratelimit-reset'))
    after = _retry_delay(_header(headers, 'retry-after'), current)
    if remaining == '0':
        wait = max(0, math.ceil(reset - current)) if reset is not None and current is not None else None
        # Honor both constraints when both are supplied.
        if after is not None:
            wait = max(wait, after) if wait is not None else after
        return (f'GitHub reports an exhausted request limit (HTTP {code} from {host}). ' + _wait_message(wait))
    if after is not None:
        return (f'GitHub requested a retry delay (HTTP {code} from {host}). ' + _wait_message(after))
    if code == 429:
        return (f'GitHub refused further requests (HTTP 429 from {host}); retry timing is unavailable. '
                'Wait at least 60 s before rebuilding.')
    return None


def tls_reason(error):
    """Only vetted static classes and numeric OpenSSL verification status."""
    cause = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(cause, ssl.SSLCertVerificationError):
        code = getattr(cause, 'verify_code', None)
        if type(code) is int and 0 <= code <= 65535:
            return f'certificate verification code {code}'
        return 'certificate verification status unavailable'
    return 'TLS protocol failure' if isinstance(cause, ssl.SSLError) else 'TLS status unavailable'


def _network_reason(cause):
    for cls, label in ((socket.gaierror, 'DNS resolution failure'), (socket.timeout, 'connection timeout'),
                       (ConnectionRefusedError, 'connection refused'), (ConnectionError, 'connection failure')):
        if isinstance(cause, cls):
            return label
    return 'network request failure'


def _with_previous(message, reasons):
    return ('Earlier endpoint failures: ' + '; then '.join(reasons) + '. ' if reasons else '') + message


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
    reasons = []
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
                if type(code) is not int or not 100 <= code <= 599:
                    error.close()
                    raise DownloadError(_with_previous('Dependency server returned an invalid HTTP status.', reasons)) from None
                try:
                    limited = github_rate_limit(request_host, code, error.headers or {})
                    after = _retry_delay(_header(error.headers or {}, 'retry-after'), _now(None))
                finally:
                    error.close()
                if limited:
                    raise DownloadError(_with_previous(limited, reasons)) from None
                if code in (429, 503) and after is not None:
                    message = f'Dependency request to {request_host} returned HTTP {code}. ' + _wait_message(after)
                    raise DownloadError(_with_previous(message, reasons)) from None
                if code == 429:
                    message = (f'Dependency request to {request_host} returned HTTP 429. '
                               'Retry timing is unavailable; wait before rebuilding.')
                    raise DownloadError(_with_previous(message, reasons)) from None
                if code not in (408, 500, 502, 503, 504):
                    message = (f'Dependency request to {request_host} returned HTTP {code}. '
                               'Access or dependency availability must be checked before rebuilding.')
                    raise DownloadError(_with_previous(message, reasons)) from None
                reason = f'HTTP {code}'
            except (ssl.SSLError, urllib.error.URLError, OSError) as error:
                cause = error.reason if isinstance(error, urllib.error.URLError) else error
                if isinstance(cause, ssl.SSLError):
                    message = (f'Dependency TLS verification failed for {request_host} ({tls_reason(error)}). '
                               'Check the system clock, trusted certificates and HTTPS proxy configuration.')
                    raise DownloadError(_with_previous(message, reasons)) from None
                if not isinstance(error, (urllib.error.URLError, socket.timeout, ConnectionError, socket.gaierror)):
                    raise
                reason = _network_reason(cause)
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
        reasons.append(f'{request_host}: {reason}')
    raise DownloadError(f'Could not download from {"; then ".join(reasons)}. '
                        'Check the network or Windows proxy settings, then rebuild.')


def verified_context(self):
    from . import tls
    return tls.context()
