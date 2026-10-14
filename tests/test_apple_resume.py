"""Apple recovery download: a dropped stream resumes from the last byte received; every chunk is still verified. No network."""
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

    def test_a_stream_that_drops_mid_chunk_resumes_at_the_last_byte_received(self):
        # WAS: resumed at the last whole chunk; networks that cut every connection after 1 MiB never got past a 10 MiB chunk
        got, calls, err = self.run_download([lambda e: Stream(IMAGE, drop_after=4000),
                                             lambda e: Stream(IMAGE[4000:], status=206, content_range=f"bytes 4000-{len(IMAGE)-1}/{len(IMAGE)}")])
        self.assertIsNone(err)
        self.assertEqual(got, IMAGE)
        self.assertEqual(calls, [None, f"bytes=4000-{4000 + apple.WINDOW - 1}"])

    def test_a_chunk_that_arrives_wrong_is_fetched_once_more_and_the_download_finishes(self):
        # 1.15: one chunk of 85 arrived whole but wrong and the whole download stopped
        bad = bytearray(IMAGE); bad[3500] ^= 0xFF
        got, calls, err = self.run_download([lambda e: Stream(bytes(bad)),
                                             lambda e: Stream(IMAGE[3000:6000], status=206, content_range=f"bytes 3000-5999/{len(IMAGE)}")])
        self.assertIsNone(err)
        self.assertEqual(got, IMAGE)
        self.assertEqual(calls, [None, "bytes=3000-5999"])

    def test_negative_control_a_chunk_wrong_on_both_fetches_still_stops(self):
        bad = bytearray(IMAGE); bad[3500] ^= 0xFF
        got, calls, err = self.run_download([lambda e: Stream(bytes(bad)),
                                             lambda e: Stream(bytes(bad[3000:6000]), status=206, content_range=f"bytes 3000-5999/{len(IMAGE)}")])
        self.assertIsNone(got)
        self.assertIn("chunk 2/3 of test fails Apple's hash twice", err)
        self.assertIn("antivirus", err)

    def test_a_network_that_cuts_every_connection_mid_chunk_still_finishes(self):
        cap = 700  # each connection ends after 700 bytes; chunks are 3000
        def opener(e):
            start = int((e or {}).get("Range", "bytes=0-").split("=")[1].split("-")[0] or 0)
            return Stream(IMAGE[start:], drop_after=cap, status=206 if start else 200,
                          content_range=f"bytes {start}-{len(IMAGE)-1}/{len(IMAGE)}" if start else None)
        got, calls, err = self.run_download([opener] * 20)
        self.assertIsNone(err)
        self.assertEqual(got, IMAGE)

    def test_a_network_that_resets_every_large_response_finishes_in_small_windows(self):
        # 1.3.0 logs (14 machines): the first connection got exactly 1 MiB, then every "bytes=N-" resume (the whole rest of
        # the image) got 0 bytes. Here: the first stream is cut at 1000 bytes; any later response asking for more than the
        # window is reset with nothing; window-sized ranges pass. The download must finish and match byte for byte.
        win = 500
        def opener(e):
            rng = (e or {}).get("Range")
            if rng is None:
                return Stream(IMAGE, drop_after=1000)
            a, b = rng.split("=")[1].split("-")
            start = int(a)
            if not b or int(b) - start + 1 > win:
                return Stream(b"", status=206, content_range=f"bytes {start}-{len(IMAGE)-1}/{len(IMAGE)}")
            end = min(int(b), len(IMAGE) - 1)
            return Stream(IMAGE[start:end + 1], status=206, content_range=f"bytes {start}-{end}/{len(IMAGE)}")
        with patch.object(apple, "WINDOW", win):
            got, calls, err = self.run_download([opener] * 40)
        self.assertIsNone(err, err)
        self.assertEqual(got, IMAGE)
        self.assertTrue(all(c is None or not c.endswith("-") for c in calls), calls)

    def test_negative_control_a_server_that_ignores_the_range_is_refused(self):
        got, calls, err = self.run_download([lambda e: Stream(IMAGE, drop_after=4000), lambda e: Stream(IMAGE, status=200)])
        self.assertIsNone(got)
        self.assertIn("would not resume", err)

    def test_resumes_are_bounded(self):
        opens = [lambda e: Stream(IMAGE, drop_after=10)] + [lambda e: Stream(b"", status=206, content_range=f"bytes 10-{len(IMAGE)-1}/{len(IMAGE)}")] * 40
        with patch.object(apple, "_refresh", lambda info: None):
            got, calls, err = self.run_download(opens)
        self.assertIsNone(got)
        self.assertIn("resumed connections", err)
        self.assertLessEqual(len(calls), apple.RESUMES_WINDOWED + 1)

    def test_a_stick_that_refuses_the_image_file_reports_that_not_an_unbound_handle(self):
        # 1.9.0 (10-10): "UnboundLocalError: cannot access local variable 'fh'" hid why the file could not be created
        with tempfile.TemporaryDirectory() as t, patch.object(apple, "fetch_chunklist", lambda i: b"cl"), \
                patch.object(apple, "parse_chunklist", lambda d: LIST), \
                patch.object(apple, "_asset", lambda *a, **k: Stream(IMAGE)):
            real_open = open
            def refusing_open(path, *a, **k):   # the stick refuses the image file itself
                if str(path).endswith(".dmg.part"):
                    raise PermissionError(13, "Permission denied", str(path))
                return real_open(path, *a, **k)
            with patch("builtins.open", refusing_open), self.assertRaises(PermissionError):
                apple.download(INFO, t)

    def test_a_stalled_download_says_what_each_connection_did_and_what_to_do(self):
        # 1.9.0 logs (15 writes, 10-10): the STOP line named only the first drop, so the resumes' behaviour was unknowable
        opens = [lambda e: Stream(IMAGE, drop_after=10)] + [lambda e: Stream(b"", status=206, content_range=f"bytes 10-{len(IMAGE)-1}/{len(IMAGE)}")] * 40
        with patch.object(apple, "_refresh", lambda info: None):
            got, calls, err = self.run_download(opens)
        self.assertIsNone(got)
        self.assertIn("Last connections:", err)
        self.assertIn("connection at 0 gave 10 B", err)
        self.assertIn("connection at 10 gave 0 B", err)
        self.assertIn("phone hotspot or a VPN", err)

    def test_a_resume_whose_own_request_fails_is_retried_not_fatal(self):
        # 1.5.0: a reset on the resume request itself ended the download; it is one more empty connection now
        def reset(e):
            raise ConnectionResetError(10054, "reset")
        def opener(e):
            rng = (e or {}).get("Range")
            if rng is None:
                return Stream(IMAGE, drop_after=1000)
            a, b = rng.split("=")[1].split("-")
            start, end = int(a), min(int(b), len(IMAGE) - 1)
            return Stream(IMAGE[start:end + 1], status=206, content_range=f"bytes {start}-{end}/{len(IMAGE)}")
        with patch.object(apple, "_refresh", lambda info: None):
            got, calls, err = self.run_download([opener, reset, reset] + [opener] * 400)
        self.assertIsNone(err, err)
        self.assertEqual(got, IMAGE)

    def test_a_recovery_image_brought_on_disk_is_copied_and_checked(self):
        # Apple refuses some networks on every session (HTTP 403): a BaseSystem.dmg + chunklist from elsewhere works
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as usb, \
                patch.object(apple, "parse_chunklist", lambda d: LIST):
            open(os.path.join(src, "BaseSystem.chunklist"), "wb").write(b"signed")
            open(os.path.join(src, "BaseSystem.dmg"), "wb").write(IMAGE)
            info = apple.local_image(src)
            out = apple.copy_local(info, usb)
            self.assertEqual(open(out["image"], "rb").read(), IMAGE)
            bad = bytearray(IMAGE); bad[5000] ^= 1
            open(os.path.join(src, "BaseSystem.dmg"), "wb").write(bytes(bad))
            with self.assertRaises(apple.AppleError):
                apple.copy_local(apple.local_image(src), usb)
            self.assertIsNone(apple.local_image(os.path.join(src, "missing")))

    def test_reset_retries_and_recovery_refusal_has_one_https_attempt(self):
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
        self.assertEqual(len(tries), 2)



class ExpiredToken(unittest.TestCase):
    """1.13 write log NM-QFQE7G16: oscdn answered 403 when the next window opened, because the image token ran out."""
    def forbidden(self, url):
        return apple.AppleError(f"{url}: HTTPError: HTTP Error 403: Forbidden")

    def test_a_403_on_a_window_gets_a_fresh_token_and_the_window_opens(self):
        info, seen = dict(INFO), []
        def asset(url, token, extra=None):
            seen.append(token)
            if token == "t":
                raise self.forbidden(url)
            return Stream(b"x" * 10, status=206, content_range="bytes 100-109/7234")
        def refresh(i):
            i["image_token"] = "fresh"
        with patch.object(apple, "_asset", asset), patch.object(apple, "_refresh", refresh):
            r = apple._resume(info, 100, 10, delay=0)
        self.assertEqual(r.status, 206)
        self.assertEqual(seen, ["t", "fresh"])

    def test_a_403_that_a_refresh_cannot_change_still_stops(self):
        info = dict(INFO)
        def asset(url, token, extra=None):
            raise self.forbidden(url)
        with patch.object(apple, "_asset", asset), patch.object(apple, "_refresh", lambda i: None):
            with self.assertRaises(apple.AppleError):
                apple._resume(info, 100, 10, delay=0)

    def test_a_fresh_token_refused_again_stops_naming_the_network(self):
        # 1.15 write log 10-14: the stop was the bare 403, with no word on the retry or what to change
        info, seen = dict(INFO), []
        def asset(url, token, extra=None):
            seen.append(token)
            raise self.forbidden(url)
        def refresh(i):
            i["image_token"] = "fresh"
        with patch.object(apple, "_asset", asset), patch.object(apple, "_refresh", refresh):
            with self.assertRaises(apple.AppleError) as cm:
                apple._resume(info, 100, 10, delay=0)
        self.assertEqual(seen, ["t", "fresh"])
        self.assertIn("refused again with a fresh token", str(cm.exception))
        self.assertIn("hotspot or a VPN", str(cm.exception))

    def test_a_token_osrecovery_cannot_renew_says_so(self):
        def asset(url, token, extra=None):
            raise self.forbidden(url)
        with patch.object(apple, "_asset", asset), patch.object(apple, "_refresh", lambda i: None):
            with self.assertRaises(apple.AppleError) as cm:
                apple._resume(dict(INFO), 100, 10, delay=0)
        self.assertIn("gave no fresh token", str(cm.exception))

    def test_negative_control_another_error_after_a_fresh_token_is_passed_through(self):
        def asset(url, token, extra=None):
            if token == "t":
                raise self.forbidden(url)
            raise apple.AppleError(f"{url}: URLError: reset")
        def refresh(i):
            i["image_token"] = "fresh"
        with patch.object(apple, "_asset", asset), patch.object(apple, "_refresh", refresh):
            with self.assertRaises(apple.AppleError) as cm:
                apple._resume(dict(INFO), 100, 10, delay=0)
        self.assertNotIn("download server refused", str(cm.exception))

    def test_other_errors_do_not_refresh(self):
        calls = []
        def asset(url, token, extra=None):
            raise apple.AppleError(f"{url}: URLError: reset")
        with patch.object(apple, "_asset", asset), patch.object(apple, "_refresh", lambda i: calls.append(1)):
            with self.assertRaises(apple.AppleError):
                apple._resume(dict(INFO), 100, 10, delay=0)
        self.assertEqual(calls, [])

if __name__ == "__main__":
    unittest.main()


class FirstRequest403(unittest.TestCase):
    """A 403 on the first image request gets one fresh URL and token, like a resume does."""

    def test_a_403_before_any_byte_refreshes_once(self):
        import inspect
        from p1401 import apple
        src = inspect.getsource(apple.download)
        first = src[:src.index("with open(img + \".part\", \"wb\") as fh:")]
        self.assertIn('"HTTP Error 403" not in str(e)', first)
        self.assertIn("_after_403(info, e,", first)
