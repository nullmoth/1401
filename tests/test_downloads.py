import hashlib
import io
import os
import plistlib
import ssl
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch
from p1401 import downloads, engine

sys.path.insert(0, engine.UPSTREAM)
from Scripts.resource_fetcher import ResourceFetcher
RAW = 'https://raw.githubusercontent.com/dortania/build-repo/builds/latest.json'

class Response(io.BytesIO):
    def getcode(self): return 200
    def info(self): return {}
    def getheader(self, name): return None

class Downloads(unittest.TestCase):
    def setUp(self):
        engine._patient_downloads()
        self.fetcher = ResourceFetcher({'Authorization': 'private', 'Cookie': 'private', 'User-Agent': '1401'})

    def test_official_fallback_preserves_json(self):
        with patch('urllib.request.urlopen', side_effect=[urllib.error.URLError('reset'), Response(b'{"kexts": [1]}')]) as op:
            self.assertEqual(self.fetcher.fetch_and_parse_content(RAW, 'json'), {'kexts': [1]})
        fallback = op.call_args.args[0]
        self.assertEqual(fallback.full_url, 'https://api.github.com/repos/dortania/build-repo/contents/latest.json?ref=builds')
        self.assertEqual(fallback.get_header('Accept'), 'application/vnd.github.raw+json')
        self.assertIsNone(fallback.get_header('Authorization'))
        self.assertIsNone(fallback.get_header('Cookie'))

    def test_refs_heads_plist(self):
        url = 'https://raw.githubusercontent.com/example/repo/refs/heads/master/patches.plist'
        self.assertEqual(downloads.github_contents_url(url), 'https://api.github.com/repos/example/repo/contents/patches.plist?ref=master')
        with patch('urllib.request.urlopen', side_effect=[urllib.error.URLError('DNS'), Response(plistlib.dumps({'Patches': []}))]):
            self.assertEqual(self.fetcher.fetch_and_parse_content(url, 'plist'), {'Patches': []})

    def test_fallback_failure_identifies_actual_host(self):
        fallback = downloads.github_contents_url(RAW)
        with patch('urllib.request.urlopen', side_effect=[urllib.error.URLError('reset'),
                   urllib.error.HTTPError(fallback, 403, 'rate limited', {}, None)]) as op:
            with self.assertRaisesRegex(downloads.DownloadError, r'api\.github\.com returned HTTP 403'):
                self.fetcher.fetch_and_parse_content(RAW, 'json')
            self.assertEqual(op.call_count, 2)

    def test_missing_release_is_terminal(self):
        for code in (403, 404):
            with self.subTest(code=code), patch('urllib.request.urlopen', side_effect=urllib.error.HTTPError(RAW, code, 'missing', {}, None)) as op:
                with self.assertRaisesRegex(downloads.DownloadError, f'HTTP {code}'):
                    self.fetcher.fetch_and_parse_content(RAW, 'json')
                self.assertEqual(op.call_count, 1)

    def test_bounded_retry_budget(self):
        for url, count in ((RAW, 4), ('https://github.com/example/repo/releases/file.zip', 3)):
            with self.subTest(url=url), patch('urllib.request.urlopen', side_effect=urllib.error.URLError('reset')) as op, patch('time.sleep'):
                with self.assertRaises(downloads.DownloadError): self.fetcher.fetch_and_parse_content(url)
                self.assertEqual(op.call_count, count)

    def test_transient_http_retries(self):
        url = 'https://github.com/example/repo/releases/file.zip'
        with patch('urllib.request.urlopen', side_effect=[urllib.error.HTTPError(url, 503, 'busy', {}, None), Response(b'ok')]) as op, patch('time.sleep'):
            self.assertEqual(self.fetcher.fetch_and_parse_content(url), 'ok')
            self.assertEqual(op.call_count, 2)

    def test_certificate_failure_no_fallback(self):
        self.assertEqual(self.fetcher.ssl_context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(self.fetcher.ssl_context.check_hostname)
        with patch('urllib.request.urlopen', side_effect=urllib.error.URLError(ssl.SSLCertVerificationError('untrusted'))) as op:
            with self.assertRaisesRegex(downloads.DownloadError, 'TLS verification'): self.fetcher.fetch_and_parse_content(RAW)
            self.assertEqual(op.call_count, 1)

    def test_checksum_still_required(self):
        payload = b'dependency contents'
        with tempfile.TemporaryDirectory() as temp, patch('urllib.request.urlopen', side_effect=lambda *a, **k: Response(payload)):
            dest = os.path.join(temp, 'dependency.zip')
            self.assertTrue(self.fetcher.download_and_save_file('https://github.com/example/file.zip', dest, hashlib.sha256(payload).hexdigest()))
            with open(dest, 'rb') as stream: self.assertEqual(stream.read(), payload)
            self.assertFalse(self.fetcher.download_and_save_file('https://github.com/example/file.zip', dest, '0' * 64))
            self.assertFalse(os.path.exists(dest))

    def test_rejects_credentials_and_http(self):
        with patch('urllib.request.urlopen') as op:
            for url in ('http://github.com/file', 'https://private@github.com/file'):
                with self.assertRaises(downloads.DownloadError): downloads.make_request(self.fetcher, url)
            op.assert_not_called()

if __name__ == '__main__': unittest.main()
