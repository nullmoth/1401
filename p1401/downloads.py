"""Bounded, verified HTTPS requests for build dependencies."""
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request


class DownloadError(RuntimeError):
    pass


def github_contents_url(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'https' or parts.hostname != 'raw.githubusercontent.com' or parts.username or parts.password:
        return None
    fields = parts.path.lstrip('/').split('/')
    if len(fields) < 4:
        return None
    owner, repo = fields[:2]
    rest = fields[2:]
    if rest[:2] in (['refs', 'heads'], ['refs', 'tags']):
        rest = rest[2:]
    if len(rest) < 2 or not all((owner, repo, rest[0])):
        return None
    ref, path = rest[0], '/'.join(rest[1:])
    return ('https://api.github.com/repos/' + urllib.parse.quote(owner, safe='') + '/' +
            urllib.parse.quote(repo, safe='') + '/contents/' +
            urllib.parse.quote(urllib.parse.unquote(path), safe='/') + '?' +
            urllib.parse.urlencode({'ref': urllib.parse.unquote(ref)}))


def make_request(fetcher, url, timeout=20):
    """Use the official contents endpoint when the raw host is unreachable."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
        raise DownloadError('Build dependencies require an HTTPS URL without credentials.')
    fallback = github_contents_url(url)
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
