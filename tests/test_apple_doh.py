"""When the network's DNS cannot resolve Apple's recovery server (getaddrinfo 11001, refused, reset - 1.6-1.9 write logs),
the request goes to the address DNS-over-HTTPS gives, keeping the real Host header. Anything else is unchanged."""
import json
import socket
import ssl
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

    def test_a_502_from_osrecovery_over_http_is_asked_again_over_https_at_once(self):
        seen = []

        def urlopen(req, timeout=0):
            seen.append(req.full_url)
            if req.full_url.startswith("http://"):
                raise urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", {}, None)
            return Resp()
        slept = []
        with mock.patch("urllib.request.urlopen", urlopen):
            apple._open("http://osrecovery.apple.com/InstallationPayload/RecoveryImage", {}, b"x", sleep=slept.append)
        self.assertEqual(seen, ["http://osrecovery.apple.com/InstallationPayload/RecoveryImage",
                                "https://osrecovery.apple.com/InstallationPayload/RecoveryImage"])
        self.assertEqual(slept, [])

    def test_the_image_cdn_never_goes_to_https(self):
        seen = []

        def urlopen(req, timeout=0):
            seen.append(req.full_url)
            raise urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", {}, None)
        with mock.patch("urllib.request.urlopen", urlopen):
            with self.assertRaises(apple.AppleError):
                apple._open("http://oscdn.apple.com/content/x.dmg", {}, sleep=lambda s: None, doh=lambda h: "17.253.1.2")
        self.assertTrue(seen and all(u.startswith("http://") for u in seen))

    def test_http_recovery_403_gets_one_verified_https_attempt(self):
        seen = []

        def urlopen(req, timeout=0):
            seen.append((req.full_url, req.data, req.get_header("Cookie")))
            if req.full_url.startswith("http://"):
                raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
            return Resp()

        url = "http://osrecovery.apple.com/InstallationPayload/RecoveryImage"
        with mock.patch("urllib.request.urlopen", urlopen):
            result = apple._open(url, {"Cookie": "session=test"}, b"request", sleep=lambda s: None)
        self.assertIsInstance(result, Resp)
        self.assertEqual(seen, [(url, b"request", "session=test"),
                                (url.replace("http://", "https://", 1), b"request", "session=test")])

    def test_https_recovery_403_still_stops_without_an_ip_reroute(self):
        seen = []

        def urlopen(req, timeout=0):
            seen.append(req.full_url)
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

        with mock.patch("urllib.request.urlopen", urlopen), mock.patch.object(apple, "_doh") as resolver:
            with self.assertRaises(apple.AppleError):
                apple._open("http://osrecovery.apple.com/", {}, sleep=lambda s: None)
        self.assertEqual(seen, ["http://osrecovery.apple.com/", "https://osrecovery.apple.com/"])
        resolver.assert_not_called()

    def test_a_400_from_osrecovery_is_asked_over_https_and_then_says_what_to_change(self):
        seen = []

        def urlopen(req, timeout=0):
            seen.append(req.full_url)
            raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, None)

        with mock.patch("urllib.request.urlopen", urlopen), mock.patch.object(apple, "_doh") as resolver:
            with self.assertRaises(apple.AppleError) as cm:
                apple._open("http://osrecovery.apple.com/", {}, sleep=lambda s: None)
        self.assertEqual(seen, ["http://osrecovery.apple.com/", "https://osrecovery.apple.com/"])
        self.assertIn("phone hotspot or a VPN", str(cm.exception))
        resolver.assert_not_called()

    def test_cdn_403_is_not_sent_to_unverified_https(self):
        seen = []

        def urlopen(req, timeout=0):
            seen.append(req.full_url)
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

        with mock.patch("urllib.request.urlopen", urlopen):
            with self.assertRaises(apple.AppleError):
                apple._open("http://oscdn.apple.com/content/image.dmg", {}, sleep=lambda s: None)
        self.assertEqual(seen, ["http://oscdn.apple.com/content/image.dmg"])

    def test_a_dns_failure_on_osrecovery_still_takes_the_doh_route(self):
        seen = []

        def urlopen(req, timeout=0):
            seen.append(req.full_url)
            if "osrecovery.apple.com" in req.full_url:
                raise urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))
            return Resp()
        with mock.patch("urllib.request.urlopen", urlopen):
            apple._open("http://osrecovery.apple.com/", {}, sleep=lambda s: None, doh=lambda h: "17.253.1.2")
        self.assertEqual(seen, ["http://osrecovery.apple.com/", "http://17.253.1.2/"])

    def test_https_failing_too_still_reports_the_error(self):
        def urlopen(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", {}, None)
        with mock.patch("urllib.request.urlopen", urlopen):
            with self.assertRaises(apple.AppleError) as cm:
                apple._open("http://osrecovery.apple.com/", {}, sleep=lambda s: None)
        self.assertIn("502", str(cm.exception))

    def test_a_reroute_on_the_last_try_still_gets_its_own_try(self):
        # 1.13 write log NM-SMXYWG2M: timeouts used up every try, the DNS failure on the last one rerouted to DoH and the
        # loop ended there - _open returned None and the write stopped with "'NoneType' object has no attribute 'headers'"
        seen = []

        def urlopen(req, timeout=0):
            seen.append(req.full_url)
            if "17.253.1.2" in req.full_url:
                return Resp()
            if len(seen) < apple.OPEN_TRIES:
                raise urllib.error.URLError(TimeoutError("timed out"))
            raise urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))
        with mock.patch("urllib.request.urlopen", urlopen):
            r = apple._open("http://oscdn.apple.com/x.dmg", {}, sleep=lambda s: None, doh=lambda h: "17.253.1.2")
        self.assertIsNotNone(r)
        self.assertEqual(seen[-1], "http://17.253.1.2/x.dmg")

    def test_open_never_returns_none(self):
        def urlopen(req, timeout=0):
            raise urllib.error.URLError(TimeoutError("timed out"))
        with mock.patch("urllib.request.urlopen", urlopen):
            with self.assertRaises(apple.AppleError):
                apple._open("http://oscdn.apple.com/x.dmg", {}, sleep=lambda s: None, doh=lambda h: "17.253.1.2")

    def test_a_cdn_that_keeps_answering_502_is_asked_at_another_edge(self):
        # 1.14.2 write logs: oscdn 502 on every try; the DoH address is a different edge
        seen = []

        def urlopen(req, timeout=0):
            seen.append(req.full_url)
            if "oscdn.apple.com" in req.full_url:
                raise urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", {}, None)
            return Resp()
        with mock.patch("urllib.request.urlopen", urlopen):
            r = apple._open("http://oscdn.apple.com/x.chunklist", {}, sleep=lambda s: None, doh=lambda h: "17.253.1.2")
        self.assertIsNotNone(r)
        self.assertEqual(seen, ["http://oscdn.apple.com/x.chunklist", "http://oscdn.apple.com/x.chunklist",
                                "http://17.253.1.2/x.chunklist"])

    def test_one_502_is_just_retried_where_it_was(self):
        seen = []

        def urlopen(req, timeout=0):
            seen.append(req.full_url)
            if len(seen) == 1:
                raise urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", {}, None)
            return Resp()
        with mock.patch("urllib.request.urlopen", urlopen):
            apple._open("http://oscdn.apple.com/x.chunklist", {}, sleep=lambda s: None, doh=lambda h: "17.253.1.2")
        self.assertEqual(seen, ["http://oscdn.apple.com/x.chunklist"] * 2)

    def test_doh_answer_parsing_takes_the_first_ipv4_a_record(self):
        body = json.dumps({"Answer": [{"type": 5, "data": "cdn.apple.com."}, {"type": 1, "data": "17.253.1.2"}]}).encode()
        self.assertEqual(apple._doh("osrecovery.apple.com", fetch=lambda url: body), "17.253.1.2")

    def test_no_resolver_answers_gives_none(self):
        def fetch(url):
            raise OSError("blocked")
        self.assertIsNone(apple._doh("osrecovery.apple.com", fetch=fetch))

    def test_osrecovery_cut_off_over_http_and_https_names_what_to_do(self):
        seen = []

        def urlopen(req, timeout=0):
            seen.append(req.full_url)
            raise urllib.error.URLError(ssl.SSLEOFError(8, "EOF occurred in violation of protocol"))
        with mock.patch("urllib.request.urlopen", urlopen):
            with self.assertRaises(apple.AppleError) as cm:
                apple._open("http://osrecovery.apple.com/", {}, sleep=lambda s: None)
        self.assertIn("https://osrecovery.apple.com/", seen)
        self.assertIn("EOF occurred", str(cm.exception))
        self.assertIn("hotspot or a VPN", str(cm.exception))

    def test_negative_control_a_refusal_from_osrecovery_gets_no_network_advice(self):
        def urlopen(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
        with mock.patch("urllib.request.urlopen", urlopen):
            with self.assertRaises(apple.AppleError) as cm:
                apple._open("http://osrecovery.apple.com/", {}, sleep=lambda s: None)
        self.assertNotIn("hotspot", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
