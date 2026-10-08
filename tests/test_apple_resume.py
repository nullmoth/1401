"""Apple recovery download: a dropped stream resumes from the last verified chunk. No network."""
import email.message, hashlib, io, os, tempfile, unittest, urllib.error
from unittest.mock import patch

from p1401 import apple

CHUNKS = [os.urandom(3000), os.urandom(3000), os.urandom(1234)]
IMAGE = b"".join(CHUNKS)
LIST = [(len(c), hashlib.sha256(c).digest()) for c in CHUNKS]
INFO = {"image_url": "http://oscdn.apple.com/x/BaseSystem.dmg", "image_token": "t", "chunklist_url": "http://oscdn.apple.com/x/BaseSystem.chunklist",
        "chunklist_token": "t", "product": "test"}


class Stream(io.BytesIO):
    def __init__(self, data, drop_after=None, status=200, content_range=None):
        super().__init__(data); self.drop_after = drop_after; self.status = status
        self.headers = email.message.Message()
        if content_range: self.headers["Content-Range"] = content_range
    def read(self, n=-1):
        if self.drop_after is not None and self.tell() >= self.drop_after:
            return b""
        if self.drop_after is not None and n > 0:
            n = min(n, self.drop_after - self.tell())
        return super().read(n)
    def __enter__(self): return self
    def __exit__(self, *a): self.close()


class Resume(unittest.TestCase):
    def run_download(self, opens):
        calls = []
        def asset(url, token, extra=None):
            calls.append((extra or {}).get("Range"))
            return opens.pop(0)(extra)
        with tempfile.TemporaryDirectory() as t, patch.object(apple, "fetch_chunklist", lambda i: b"cl"), \
                patch.object(apple, "parse_chunklist", lambda d: LIST), patch.object(apple, "_asset", asset), \
                patch.object(apple.time, "sleep", lambda s: None):
            try:
                out = apple.download(INFO, t)
                return open(out["image"], "rb").read(), calls, None
            except apple.AppleError as e:
                return None, calls, str(e)

    def test_a_stream_that_drops_mid_chunk_resumes_at_the_last_verified_chunk(self):
        got, calls, err = self.run_download([lambda e: Stream(IMAGE, drop_after=4000),
                                             lambda e: Stream(IMAGE[3000:], status=206, content_range=f"bytes 3000-{len(IMAGE)-1}/{len(IMAGE)}")])
        self.assertIsNone(err)
        self.assertEqual(got, IMAGE)
        self.assertEqual(calls, [None, "bytes=3000-"])

    def test_negative_control_a_server_that_ignores_the_range_is_refused(self):
        got, calls, err = self.run_download([lambda e: Stream(IMAGE, drop_after=4000), lambda e: Stream(IMAGE, status=200)])
        self.assertIsNone(got)
        self.assertIn("would not resume", err)

    def test_resumes_are_bounded(self):
        opens = [lambda e: Stream(IMAGE, drop_after=10)] + [lambda e: Stream(b"", status=206, content_range="bytes 0-0/1")] * 20
        got, calls, err = self.run_download(opens)
        self.assertIsNone(got)
        self.assertIn("resumed connections", err)
        self.assertLessEqual(len(calls), apple.RESUMES + 1)

    def test_a_reset_while_opening_is_retried_but_an_http_refusal_is_not(self):
        tries = []
        def urlopen(req, timeout=None):
            tries.append(1)
            if len(tries) < 3: raise urllib.error.URLError(ConnectionResetError(10054, "reset"))
            return Stream(b"ok")
        with patch("urllib.request.urlopen", urlopen):
            self.assertEqual(apple._open("http://osrecovery.apple.com/", {}, sleep=lambda s: None).read(), b"ok")
        tries.clear()
        def refuse(req, timeout=None):
            tries.append(1); raise urllib.error.HTTPError(req.full_url, 403, "no", email.message.Message(), None)
        with patch("urllib.request.urlopen", refuse), self.assertRaises(apple.AppleError):
            apple._open("http://osrecovery.apple.com/", {}, sleep=lambda s: None)
        self.assertEqual(len(tries), 1)


if __name__ == "__main__":
    unittest.main()
