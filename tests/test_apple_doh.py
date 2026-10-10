"""When the network's DNS cannot resolve Apple's recovery server (getaddrinfo 11001, refused, reset - 1.6-1.9 write logs),
the request goes to the address DNS-over-HTTPS gives, keeping the real Host header. Anything else is unchanged."""
import json
import socket
import unittest
import urllib.error
from unittest import mock

from p1401 import apple


class Resp:
    status = 200

    def read(self, n=-1):
        return b"ok"

    def close(self):
        pass


class DohFallback(unittest.TestCase):
    def setUp(self):
        apple._doh_cache.clear()

    def test_a_dns_failure_is_retried_at_the_doh_address_with_the_real_host(self):
        seen = []

        def urlopen(req, timeout=0):
            seen.append((req.full_url, req.get_header("Host")))
            if "osrecovery.apple.com" in req.full_url:
                raise urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))
            return Resp()
        doh = lambda host: "17.253.1.2"
        with mock.patch("urllib.request.urlopen", urlopen):
            apple._open("http://osrecovery.apple.com/", {"Host": "osrecovery.apple.com"}, sleep=lambda s: None, doh=doh)
        self.assertEqual(seen[-1], ("http://17.253.1.2/", "osrecovery.apple.com"))

    def test_an_http_error_is_not_rerouted(self):
        calls = []

        def urlopen(req, timeout=0):
            calls.append(req.full_url)
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
        with mock.patch("urllib.request.urlopen", urlopen):
            with self.assertRaises(apple.AppleError):
                apple._open("http://osrecovery.apple.com/", {}, sleep=lambda s: None, doh=lambda h: "17.0.0.1")
        self.assertTrue(all("osrecovery.apple.com" in u for u in calls))

    def test_doh_answer_parsing_takes_the_first_ipv4_a_record(self):
        body = json.dumps({"Answer": [{"type": 5, "data": "cdn.apple.com."}, {"type": 1, "data": "17.253.1.2"}]}).encode()
        self.assertEqual(apple._doh("osrecovery.apple.com", fetch=lambda url: body), "17.253.1.2")

    def test_no_resolver_answers_gives_none(self):
        def fetch(url):
            raise OSError("blocked")
        self.assertIsNone(apple._doh("osrecovery.apple.com", fetch=fetch))


if __name__ == "__main__":
    unittest.main()
