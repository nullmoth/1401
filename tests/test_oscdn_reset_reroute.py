"""oscdn reset the chunklist request on every try on three PCs (2.0.2 write logs 10-15, WinError 10054). A reset that
already goes to the DNS-over-HTTPS edge (guarded here); the fix is that a final stop says what to change on the network."""
import unittest
import urllib.error
from unittest import mock

from p1401 import apple

URL = "http://oscdn.apple.com/content/downloads/31/41/140-93589/x/RecoveryImage/BaseSystem.chunklist"


class Resp:
    status = 200

    def read(self, n=-1):
        return b"ok"

    def close(self):
        pass


def reset(req):
    return urllib.error.URLError(ConnectionResetError(10054, "An existing connection was forcibly closed"))


class OscdnReset(unittest.TestCase):
    def setUp(self):
        apple._doh_cache.clear()

    def test_repeated_resets_move_to_another_edge(self):
        seen = []

        def urlopen(req, timeout=0):
            seen.append((req.full_url, req.get_header("Host")))
            if "oscdn.apple.com" in req.full_url:
                raise reset(req)
            return Resp()
        with mock.patch("urllib.request.urlopen", urlopen):
            apple._open(URL, {"Host": "oscdn.apple.com"}, sleep=lambda s: None, doh=lambda h: "17.253.9.9")
        self.assertEqual(seen[-1][1], "oscdn.apple.com")
        self.assertTrue(seen[-1][0].startswith("http://17.253.9.9/"))

    def test_resets_everywhere_end_with_network_advice(self):
        def urlopen(req, timeout=0):
            raise reset(req)
        with mock.patch("urllib.request.urlopen", urlopen):
            with self.assertRaises(apple.AppleError) as cm:
                apple._open(URL, {"Host": "oscdn.apple.com"}, sleep=lambda s: None, doh=lambda h: "17.253.9.9")
        self.assertIn("phone hotspot", str(cm.exception))

    def test_a_refused_token_is_still_not_rerouted(self):
        calls = []

        def urlopen(req, timeout=0):
            calls.append(req.full_url)
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
        with mock.patch("urllib.request.urlopen", urlopen):
            with self.assertRaises(apple.AppleError):
                apple._open(URL, {}, sleep=lambda s: None, doh=lambda h: "17.253.9.9")
        self.assertTrue(all("oscdn.apple.com" in u for u in calls))


if __name__ == "__main__":
    unittest.main()
