"""Production request diagnostics and retry-policy regressions; no network."""
import email.message
import io
import socket
import ssl
import traceback
import unittest
import urllib.error
from types import SimpleNamespace
from unittest.mock import patch
from p1401 import downloads as dl

RELEASE = 'https://github.com/example/repo/releases/download/v1.0/dependency.zip'
NOW = 1760000000


def http_error(code, headers=None):
    message = email.message.Message()
    for key, value in (headers or {}).items():
        message[key] = value
    return urllib.error.HTTPError(RELEASE, code, 'private response text', message, None)


class Response(io.BytesIO):
    def getheader(self, name):
        return None


class DownloadDiagnostics(unittest.TestCase):
    def setUp(self):
        self.fetcher = SimpleNamespace(request_headers={'User-Agent': '1401'}, ssl_context=ssl.create_default_context())

    def failure(self, errors, url=RELEASE):
        with patch('urllib.request.urlopen', side_effect=errors) as opened, patch.object(dl.time, 'sleep') as slept, patch.object(dl.time, 'time', return_value=NOW):
            with self.assertRaises(dl.DownloadError) as result:
                dl.make_request(self.fetcher, url)
        return result.exception, opened, slept

    def test_primary_limit_stops_before_retry_and_retains_first_failure(self):
        for code in (403, 429):
            with self.subTest(code=code):
                error, opened, slept = self.failure([urllib.error.URLError(socket.timeout('private timeout')),
                    http_error(code, {'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': str(NOW + 600)})])
                message = str(error)
                self.assertIn('github.com: connection timeout', message)
                self.assertIn('api.github.com', message)
                self.assertIn('exhausted request limit', message)
                self.assertIn('600 s', message)
                self.assertNotIn('nothing is wrong', message)
                self.assertNotIn('private', message)
                self.assertEqual(opened.call_count, 2)
                slept.assert_not_called()

    def test_exact_github_host_boundary(self):
        for host in ('evilgithub.com', 'github.com.example', '.github.com', 'x..github.com', '-x.github.com', 'x_.github.com'):
            with self.subTest(host=host):
                self.assertIsNone(dl.github_rate_limit(host, 403, {'x-ratelimit-remaining': '0'}, now=NOW))
        for host in ('github.com', 'api.github.com', 'API.GITHUB.COM'):
            self.assertIn('request limit', dl.github_rate_limit(host, 403, {'x-ratelimit-remaining': '0'}, now=NOW))

    def test_retry_after_seconds_and_http_date(self):
        for after in ('60', 'Thu, 09 Oct 2025 08:54:20 GMT'):
            with self.subTest(after=after):
                # The date is sixty seconds after the fixed clock.
                error, opened, slept = self.failure([http_error(403, {'Retry-After': after})])
                self.assertIn('Wait at least 60 s', str(error))
                self.assertIn('requested a retry delay', str(error))
                self.assertEqual(opened.call_count, 1)
                slept.assert_not_called()

    def test_honor_both_reset_and_retry_after(self):
        message = dl.github_rate_limit('api.github.com', 403,
            {'x-ratelimit-remaining': '0', 'x-ratelimit-reset': str(NOW + 120), 'retry-after': '300'}, now=NOW)
        self.assertIn('300 s', message)

    def test_missing_reset_does_not_claim_known_reset(self):
        message = dl.github_rate_limit('api.github.com', 403, {'x-ratelimit-remaining': '0'}, now=NOW)
        self.assertIn('retry time is unavailable', message)
        self.assertNotIn('0 s', message)

    def test_github_429_without_usable_headers_stops(self):
        for headers in ({}, {'retry-after': 'private invalid text'}, {'retry-after': '9' * 10000}):
            error, opened, slept = self.failure([http_error(429, headers)])
            self.assertIn('timing is unavailable', str(error))
            self.assertNotIn('private invalid', str(error))
            self.assertEqual(opened.call_count, 1)
            slept.assert_not_called()

    def test_header_integer_date_and_duplicate_bounds(self):
        for value in ('9' * 10000, '-1', '1e6', '\u0661', '60\r\nprivate', 'Thu, 09 Oct 2025 08:54:20'):
            with self.subTest(value=value[:30]):
                self.assertIsNone(dl._retry_delay(dl._header({'retry-after': value}, 'retry-after'), NOW))
        headers = email.message.Message()
        headers['Retry-After'] = '60'
        headers['Retry-After'] = '90'
        self.assertIsNone(dl._header(headers, 'retry-after'))
        for value in (float('inf'), float('nan'), -1, True, 'private', 10 ** 10000):
            self.assertIsNone(dl._now(value))
        message = dl.github_rate_limit('api.github.com', 403, {'retry-after': '9999999999'}, now=NOW)
        self.assertIn('exceeds the supported diagnostic window', message)
        self.assertNotIn('9999999999', message)

    def test_generic_403_is_access_refusal_not_bad_url_assertion(self):
        error, opened, slept = self.failure([http_error(403)])
        self.assertIn('returned HTTP 403', str(error))
        self.assertIn('Access or dependency availability', str(error))
        self.assertNotIn('file or release URL', str(error))
        self.assertNotIn('request limit', str(error))
        self.assertEqual(opened.call_count, 1)
        slept.assert_not_called()

    def test_tls_only_numeric_static_status_and_no_raw_chain(self):
        cause = ssl.SSLCertVerificationError(1, 'private certificate subject and home folder')
        cause.verify_code = 20
        cause.verify_message = 'private server certificate detail'
        cause.reason = 'private custom reason'
        error, opened, slept = self.failure([urllib.error.URLError(cause)])
        message = str(error)
        self.assertIn('certificate verification code 20', message)
        self.assertIn('github.com', message)
        self.assertNotIn('private', message)
        self.assertNotIn('private', ''.join(traceback.format_exception(error)))
        self.assertTrue(error.__suppress_context__)
        self.assertEqual(opened.call_count, 1)
        slept.assert_not_called()
        self.assertEqual(self.fetcher.ssl_context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(self.fetcher.ssl_context.check_hostname)

    def test_unknown_tls_fields_never_echo(self):
        for code in (-1, 65536, True, '20', None):
            cause = ssl.SSLCertVerificationError(1, 'private subject')
            cause.verify_code = code
            cause.verify_message = 'private verify message'
            self.assertEqual(dl.tls_reason(cause), 'certificate verification status unavailable')
        cause = ssl.SSLError(1, 'private protocol text')
        cause.reason = 'private custom code'
        self.assertEqual(dl.tls_reason(urllib.error.URLError(cause)), 'TLS protocol failure')

    def test_two_network_endpoints_keep_safe_causes_without_url_or_secrets(self):
        errors = [urllib.error.URLError(ConnectionRefusedError(10061, 'private proxy'))]
        errors += [urllib.error.URLError(socket.gaierror(11001, 'private host'))] * 3
        error, opened, slept = self.failure(errors)
        self.assertIn('github.com: connection refused', str(error))
        self.assertIn('api.github.com: DNS resolution failure', str(error))
        self.assertNotIn('private', str(error))
        self.assertNotIn('dependency.zip', str(error))
        self.assertEqual(opened.call_count, 4)
        self.assertEqual([call.args[0] for call in slept.call_args_list], [1, 2])

    def test_secondary_error_trace_does_not_echo_http_response(self):
        error, opened, slept = self.failure([urllib.error.URLError('private first cause'), http_error(403)])
        self.assertIn('Earlier endpoint failures', str(error))
        self.assertIn('api.github.com returned HTTP 403', str(error))
        self.assertNotIn('private', ''.join(traceback.format_exception(error)))

    def test_server_retry_after_503_stops_without_long_sleep(self):
        error, opened, slept = self.failure([http_error(503, {'Retry-After': '120'})], 'https://example.org/file')
        self.assertIn('Wait at least 120 s', str(error))
        self.assertEqual(opened.call_count, 1)
        slept.assert_not_called()

    def test_non_github_429_stops_without_asserting_github(self):
        error, opened, slept = self.failure([http_error(429)], 'https://evilgithub.com/file')
        self.assertIn('HTTP 429', str(error))
        self.assertNotIn('GitHub', str(error))
        self.assertEqual(opened.call_count, 1)
        slept.assert_not_called()

    def test_invalid_http_status_never_echoes(self):
        error, opened, slept = self.failure([http_error('private invalid code')])
        self.assertIn('invalid HTTP status', str(error))
        self.assertNotIn('private', str(error))
        self.assertEqual(opened.call_count, 1)
        slept.assert_not_called()

    def test_existing_transient_retry_can_succeed(self):
        response = Response(b'ok')
        with patch('urllib.request.urlopen', side_effect=[http_error(503), response]) as opened, patch.object(dl.time, 'sleep') as slept:
            self.assertIs(dl.make_request(self.fetcher, 'https://example.org/file'), response)
        self.assertEqual(opened.call_count, 2)
        slept.assert_called_once_with(1)


if __name__ == '__main__':
    unittest.main()
