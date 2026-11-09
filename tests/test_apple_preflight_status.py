"""Apple recovery download: the statuses Apple's servers actually answered, and proving Apple will serve the
download before the stick is erased. No network.

WHY THESE EXIST, measured 2026-11-02 over the raw write logs users sent on 10-31..11-02 (780 write logs):

  HTTP 406 from oscdn    328 logs    323 of them AFTER the stick was already erased
  HTTP 405 from osrecovery 11 logs
  HTTP 503                 10 logs
  HTTP 416 on a resume      1 log     20 resumes over 15 minutes that could never succeed
  HTTP 403                  5 logs
  HTTP 400                  2 logs
  HTTP 408                  1 log

333 of the 339 406/405 stops fell inside ONE UTC hour (2026-11-01 09:00-09:59), across six app versions
back to 1.10.0, with zero in the other 61 hours of the window: Apple's side, for an hour. 406, 405, 408
and 429 were all outside _transient, so each got one request, no back-off, no reroute and no advice.
"""
import email.message
import hashlib
import io
import os
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from p1401 import apple
from p1401 import usbwriter

CHUNKS = [os.urandom(3000), os.urandom(3000), os.urandom(1234)]
IMAGE = b"".join(CHUNKS)
LIST = [(len(c), hashlib.sha256(c).digest()) for c in CHUNKS]


def info():
    """A fresh dict every time: preflight() caches the chunklist INTO it, so a shared one would leak
    between tests and make a later arm pass on an earlier arm's cache."""
    return {"image_url": "http://oscdn.apple.com/x/BaseSystem.dmg", "image_token": "t",
            "chunklist_url": "http://oscdn.apple.com/x/BaseSystem.chunklist", "chunklist_token": "t",
            "product": "test", "name": "macOS test", "board": "Mac-TEST"}


class Stream(io.BytesIO):
    def __init__(self, data, status=200, content_range=None):
        super().__init__(data)
        self.status = status
        self.headers = email.message.Message()
        if content_range:
            self.headers["Content-Range"] = content_range

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def http_error(code, reason="x"):
    return urllib.error.HTTPError("http://oscdn.apple.com/x", code, reason, email.message.Message(), None)


class RetryClassification(unittest.TestCase):
    def test_every_status_apples_servers_answered_for_an_hour_is_retried(self):
        # 405, 406 and 408 were measured coming out of Apple's own hosts. 429 is in for the same reason a
        # 503 is: it is a "later" answer, not a refusal of this PC.
        for code in (405, 406, 408, 425, 429, 500, 502, 503, 504):
            self.assertTrue(apple._transient(http_error(code)), code)

    def test_NEGATIVE_CONTROL_a_real_refusal_is_still_not_retried(self):
        # This arm is the one that fails if someone ever widens _transient to "any HTTPError". A 404 or a
        # 403 must not be retried: 403 has its own fresh-token path and 404/410 mean the asset is gone, so
        # retrying is a minute of the user's time spent proving nothing.
        for code in (400, 401, 403, 404, 410, 416, 451):
            self.assertFalse(apple._transient(http_error(code)), code)

    def test_a_connection_error_is_still_transient(self):
        self.assertTrue(apple._transient(ConnectionResetError(10054, "reset")))
        self.assertTrue(apple._transient(urllib.error.URLError("boom")))
        self.assertFalse(apple._transient(ValueError("not a network error")))


class AdviceForAStatus(unittest.TestCase):
    """The 328 "HTTP Error 406: Not Acceptable" stops carried a raw CDN URL and nothing else: no sign that
    1401 had retried, no statement that the stick was untouched, and no idea what to do."""

    def open_with(self, code, url="http://oscdn.apple.com/x/BaseSystem.chunklist"):
        tries = []

        def urlopen(req, timeout=None):
            tries.append(req.full_url)
            raise http_error(code)

        with patch.object(apple.urllib.request, "urlopen", urlopen):
            try:
                apple._open(url, {}, sleep=lambda s: None, doh=lambda h: None)
                return tries, None
            except apple.AppleError as e:
                return tries, str(e)

    def test_a_406_is_retried_and_then_says_it_is_apples_side_and_the_stick_is_untouched(self):
        tries, message = self.open_with(406)
        self.assertIsNotNone(message)
        # it did not give up after one request
        self.assertGreaterEqual(len(tries), apple.OPEN_TRIES, tries)
        self.assertIn("406", message)
        self.assertIn("usually Apple's side", message)
        self.assertIn("wait a few minutes", message)
        self.assertIn("nothing on the USB stick was changed", message)
        # and it does NOT blame the network for cutting a connection that was never cut
        self.assertNotIn("keeps cutting the connection", message)

    def test_a_405_on_osrecovery_gets_the_same_honest_wording_not_the_cut_connection_one(self):
        tries, message = self.open_with(405, apple.OSRECOVERY_HTTP + "InstallationPayload/RecoveryImage")
        self.assertIsNotNone(message)
        self.assertIn("405", message)
        self.assertIn("usually Apple's side", message)
        self.assertNotIn("cuts the connection to Apple's recovery server", message)
        # osrecovery speaks HTTPS, which a proxy rewriting plain HTTP cannot touch: that route was tried
        self.assertTrue(any(u.startswith("https://") for u in tries), tries)

    def test_NEGATIVE_CONTROL_a_404_is_not_dressed_up_as_an_apple_outage(self):
        tries, message = self.open_with(404)
        self.assertIsNotNone(message)
        self.assertNotIn("usually Apple's side", message)
        self.assertEqual(len(tries), 1, tries)   # one request, no back-off

    def test_a_dropped_connection_still_gets_the_network_wording(self):
        def urlopen(req, timeout=None):
            raise ConnectionResetError(10054, "reset")

        with patch.object(apple.urllib.request, "urlopen", urlopen):
            with self.assertRaises(apple.AppleError) as caught:
                apple._open("http://oscdn.apple.com/x", {}, sleep=lambda s: None, doh=lambda h: None)
        self.assertIn("keeps cutting the connection", str(caught.exception))


class Preflight(unittest.TestCase):
    def test_it_verifies_the_signed_chunklist_and_samples_the_image_before_anything_is_erased(self):
        asked = []

        def asset(url, token, extra=None):
            asked.append((url.rsplit("/", 1)[-1], (extra or {}).get("Range")))
            return Stream(IMAGE[:apple.PREFLIGHT_BYTES])

        where = info()
        with patch.object(apple, "fetch_chunklist", lambda i: b"signed-bytes"), \
                patch.object(apple, "parse_chunklist", lambda d: LIST), \
                patch.object(apple, "_asset", asset):
            got = apple.preflight(where)
        self.assertEqual(got["chunks"], len(LIST))
        self.assertEqual(got["bytes"], sum(s for s, _ in LIST))
        # it asked for a SMALL range, not the image: the whole point is that it costs the user nothing
        self.assertEqual(len(asked), 1, asked)
        self.assertEqual(asked[0][0], "BaseSystem.dmg")
        self.assertTrue(asked[0][1].startswith("bytes=0-"), asked)
        self.assertLessEqual(int(asked[0][1].split("-")[1]) + 1, apple.PREFLIGHT_BYTES)
        # and it left the verified chunklist behind for the download to reuse
        self.assertEqual(where["chunklist_bytes"], b"signed-bytes")

    def test_an_unsigned_chunklist_is_refused_here_rather_than_after_the_erase(self):
        # parse_chunklist is the real one: these bytes are not Apple's, so preflight must raise.
        with patch.object(apple, "fetch_chunklist", lambda i: b"CNKL" + b"\x00" * 60):
            with self.assertRaises(apple.AppleError):
                apple.preflight(info())

    def test_the_download_reuses_the_preflighted_chunklist_and_does_not_ask_oscdn_twice(self):
        fetched = []
        where = info()
        where["chunklist_bytes"] = b"already-verified"

        def asset(url, token, extra=None):
            return Stream(IMAGE)

        with tempfile.TemporaryDirectory() as root, \
                patch.object(apple, "fetch_chunklist", lambda i: fetched.append(1) or b"cl"), \
                patch.object(apple, "parse_chunklist", lambda d: LIST), \
                patch.object(apple, "_asset", asset):
            out = apple.download(where, root)
            # read inside the block: TemporaryDirectory deletes the image on the way out
            self.assertEqual(open(out["image"], "rb").read(), IMAGE)
            self.assertEqual(fetched, [], "the chunklist was fetched a second time, after the stick was erased")
            # the chunklist file written beside the image is the bytes that were verified before the erase
            self.assertEqual(open(out["chunklist"], "rb").read(), b"already-verified")

    def test_without_a_preflight_the_download_still_fetches_its_own_chunklist(self):
        # strictly additive: the old path must still work, or copy_local and the selftest break
        fetched = []
        with tempfile.TemporaryDirectory() as root, \
                patch.object(apple, "fetch_chunklist", lambda i: fetched.append(1) or b"cl"), \
                patch.object(apple, "parse_chunklist", lambda d: LIST), \
                patch.object(apple, "_asset", lambda u, t, extra=None: Stream(IMAGE)):
            apple.download(info(), root)
        self.assertEqual(fetched, [1])


class NothingIsErasedWhenAppleRefuses(unittest.TestCase):
    """The whole point of the preflight: 323 of the 328 406 stops came after "OK erased the stick"."""

    def run_cli(self, preflight):
        printed = []
        erased = []
        disk = {"Number": 1, "FriendlyName": "Kingston DataTraveler 3.0", "SerialNumber": "s", "BusType": "USB",
                "Size": 31 * 10 ** 9, "IsBoot": False, "IsSystem": False, "IsOffline": False,
                "IsReadOnly": False, "PartitionStyle": "MBR"}
        from p1401 import machine_handoff, netsupport
        with patch.object(usbwriter, "list_disks", lambda: [disk]), \
                patch.object(usbwriter, "write", lambda *a, **k: erased.append(1) or {"root": "Z:\\"}), \
                patch.object(machine_handoff, "verified", lambda *a, **k: None), \
                patch.object(netsupport, "needs_local_image", lambda e: False), \
                patch.object(apple, "local_image", lambda d: None), \
                patch.object(apple, "image_info", lambda d: info()), \
                patch.object(apple, "preflight", preflight), \
                patch("builtins.print", lambda *a, **k: printed.append(" ".join(str(x) for x in a))):
            rc = usbwriter.cli_write(["1", "C:\\efi", "24"])
        return rc, "\n".join(printed), erased

    def test_a_406_before_the_erase_stops_with_the_stick_untouched(self):
        def refuse(i):
            raise apple.AppleError("http://oscdn.apple.com/x/BaseSystem.chunklist: HTTPError: HTTP Error 406: "
                                   "Not Acceptable - Apple's download server answered 406 to every try")

        rc, out, erased = self.run_cli(refuse)
        self.assertEqual(rc, 1)
        self.assertEqual(erased, [], "the stick was erased even though Apple had already refused")
        self.assertIn("1401-APPLE-REFUSED", out)
        self.assertIn("was not touched", out)
        self.assertIn("406", out)
        # the check ran BEFORE the erase step was even announced
        self.assertIn("nothing is erased yet", out)
        self.assertNotIn("STEP erasing", out)

    def test_NEGATIVE_CONTROL_when_apple_serves_it_the_write_still_runs(self):
        # Without this arm the one above would pass just as well if the preflight blocked every write.
        rc, out, erased = self.run_cli(lambda i: {"chunks": 92, "bytes": 2 * (1 << 30), "sampled": 65536})
        self.assertEqual(rc, 0)
        self.assertEqual(erased, [1], "the write never ran on a download Apple was serving")
        self.assertIn("Apple is serving", out)
        self.assertIn("STEP erasing", out)


class RangeRefusedForever(unittest.TestCase):
    def test_a_416_on_a_resume_stops_at_once_instead_of_twenty_doomed_retries(self):
        # One 2.6.6 write log: "connection at 0 gave 1048576 B", then HTTP 416 to every bytes=1048576-
        # request, 20 times over 15 minutes. 416 means the server's object ends before the byte we need,
        # and Apple's SIGNED chunklist says the image is longer - so no retry can ever satisfy it.
        opened = []

        # urlopen, not _asset: the 416 has to travel the real path through _open so that it is wrapped
        # exactly as it is in production. Patching _asset instead handed the download a bare HTTPError,
        # which is how the first version of this fix came to be guarded on the wrong type and do nothing.
        def urlopen(req, timeout=None):
            rng = req.headers.get("Range")
            opened.append(rng)
            if rng is None:
                return Stream(IMAGE[:1500])          # first connection delivers part of chunk 1, then ends
            raise http_error(416, "Requested Range Not Satisfiable")

        with tempfile.TemporaryDirectory() as root, \
                patch.object(apple, "parse_chunklist", lambda d: LIST), \
                patch.object(apple.urllib.request, "urlopen", urlopen), \
                patch.object(apple.time, "sleep", lambda s: None):
            where = info()
            where["chunklist_bytes"] = b"cl"
            with self.assertRaises(apple.AppleError) as caught:
                apple.download(where, root)
        message = str(caught.exception)
        self.assertIn("HTTP 416", message)
        self.assertIn("serving its own short file", message)
        self.assertIn(str(sum(s for s, _ in LIST)), message)   # what Apple's signed list says the size is
        # the resume was tried once and refused once: not twenty times
        self.assertLessEqual(len([r for r in opened if r]), 2, opened)


class GaveUpAfterResumes(unittest.TestCase):
    """Measured 11-02 over the 100 resume give-ups in the raw write logs of 10-31..11-02:

      stalled-in-a-row at give-up      20 on ALL 100 (the RESUMES_WINDOWED cap)
      total resumes at give-up         20 on 87, then 21..60
      never printed a PROGRESS line    83 of 100
      span of the recorded connections min 968 s, median 1084 s, max 3935 s
      the empty answers                343 of them, every one HTTP 206 with Content-Length 524288
                                       and NO body; Server nginx on 48 machines, dlb/1.0.2 on 1,
                                       Via absent on all 343
      first full connection delivered  exactly 1048576 B on 89 of 100

    So the download server was not cutting the connection: it accepted the range, promised the exact
    window and sent nothing. The old stop asserted "Something on this network cuts Apple's download".
    """

    def message(self, got=0, total=1000, seconds=1084, resumes=20, stalled=20):
        return apple._gave_up(apple.AppleError("stream ended at 0/10485760 bytes of a chunk"),
                              resumes, stalled, got, total, seconds, ["18s connection at 0 gave 1048576 B"])

    def test_it_no_longer_asserts_the_network_was_the_cause(self):
        m = self.message()
        self.assertNotIn("Something on this network cuts", m)
        self.assertIn("either something between this PC and Apple, or Apple's own download server", m)
        self.assertIn("cannot tell which", m)

    def test_it_reports_what_was_actually_observed(self):
        m = self.message(got=210, total=1000, seconds=1084, resumes=26, stalled=20)
        self.assertIn("26 resumed connections", m)
        self.assertIn("20 in a row that delivered no data", m)
        self.assertIn("18 minutes", m)        # 1084 s, which is the measured median
        self.assertIn("21% of the download", m)
        self.assertIn("accepting the request and then sending nothing", m)
        self.assertIn("stream ended at 0/10485760", m)   # the original error is still carried
        self.assertIn("Last connections: 18s connection at 0 gave 1048576 B", m)

    def test_it_offers_the_three_routes_cheapest_first_and_names_the_sticks_state(self):
        m = self.message()
        self.assertLess(m.index("antivirus"), m.index("hotspot or a VPN"))
        self.assertLess(m.index("hotspot or a VPN"), m.index("wait an hour"))
        # the stick IS erased by the time the image is being fetched: say so rather than implying it is fine
        self.assertIn("was erased and is not a working installer", m)
        self.assertIn("Nothing else on this PC was changed", m)

    def test_NEGATIVE_CONTROL_the_thresholds_were_not_quietly_loosened(self):
        # All 100 give-ups stopped at 20, but all 100 are FAILURES and so cannot show how often 20 would
        # have recovered; the code's own history records a write that reached 8 MiB after 19 resumes.
        # If a later change raises these, this arm is where it has to be argued for.
        self.assertEqual(apple.RESUMES_WINDOWED, 20)
        self.assertEqual(apple.RESUMES, 8)
        self.assertEqual(apple.RESUMES_TOTAL, 400)      # never approached: max observed was 60
        self.assertEqual(apple.WINDOW_MAX_DELAY, 60)

    def test_a_stalled_connection_prints_a_line_instead_of_going_silent_for_eighteen_minutes(self):
        said = []
        # one chunk, a first connection that delivers nothing, then every resume refused: the stall path
        def urlopen(req, timeout=None):
            if req.headers.get("Range") is None:
                return Stream(b"")
            raise ConnectionResetError(10054, "reset")

        with tempfile.TemporaryDirectory() as root, \
                patch.object(apple, "parse_chunklist", lambda d: LIST), \
                patch.object(apple.urllib.request, "urlopen", urlopen), \
                patch.object(apple.time, "sleep", lambda s: None), \
                patch("builtins.print", lambda *a, **k: said.append(" ".join(str(x) for x in a))):
            where = info()
            where["chunklist_bytes"] = b"cl"
            with self.assertRaises(apple.AppleError):
                apple.download(where, root)
        stall_lines = [s for s in said if "no data from the download server on" in s]
        self.assertTrue(stall_lines, said[:6])
        # one line per stalled connection, so the window is never silent, and it says what it is waiting for
        self.assertGreaterEqual(len(stall_lines), 8)
        self.assertIn("before stopping", stall_lines[0])
        self.assertIn("still trying", stall_lines[0])

    def test_the_server_that_answered_a_working_connection_is_recorded(self):
        # No log, failed or successful, had ever recorded who answers a download that works - which is
        # exactly why nginx-vs-Apple cannot be settled from the 10-31..11-02 logs.
        r = Stream(IMAGE)
        r.headers["Server"] = "nginx"
        r.headers["Via"] = "1.1 something"
        line = apple._answered_by(r)
        self.assertIn("Server=nginx", line)
        self.assertIn("Via=1.1 something", line)
        # it must NOT call it Apple's server: that is the open question, not a finding
        self.assertNotIn("Apple's download server answered", line)

    def test_the_server_line_never_raises_and_never_leaks_a_token(self):
        self.assertIn("no headers", apple._answered_by(object()))
        r = Stream(b"")
        r.headers["Set-Cookie"] = "AssetToken=SECRET"
        line = apple._answered_by(r)
        self.assertNotIn("SECRET", line)
        self.assertNotIn("AssetToken", line)


class ReadbackNamesTheStick(unittest.TestCase):
    def test_the_stick_is_named_by_model_and_claimed_size_and_never_by_serial(self):
        got = usbwriter.stick_name({"FriendlyName": "General UDisk", "Size": 31 * 10 ** 9,
                                    "SerialNumber": "E0D55EA574B315C108820075"})
        self.assertEqual(got, "General UDisk 29 GiB")
        self.assertNotIn("E0D55EA", got)

    def test_a_stick_that_reports_no_name_still_gets_a_sentence_that_reads(self):
        self.assertEqual(usbwriter.stick_name({}), "the USB stick")
        self.assertEqual(usbwriter.stick_name({"FriendlyName": "", "Size": "not a number"}), "the USB stick")

    def payload(self, changed, chunks, stick):
        """_write_payload's readback branch, with the download and the verify stubbed: this exercises the
        message, which is the part that reaches the user."""
        from p1401 import machine_handoff
        got = {"image": "Z:\\i.dmg", "chunklist": os.devnull, "chunks": chunks}
        with patch.object(apple, "download", lambda *a, **k: got), \
                patch.object(apple, "parse_chunklist", lambda d: [(1, b"")] * chunks), \
                patch.object(apple, "verify_written", lambda *a, **k: list(changed)), \
                patch.object(apple, "repair_written", lambda *a, **k: list(changed)), \
                patch.object(machine_handoff, "copy_to_installer", lambda *a: None), \
                patch("builtins.print", lambda *a, **k: None):
            with self.assertRaises(usbwriter.UsbError) as caught:
                usbwriter._write_payload("Z:\\", "C:\\efi", info(), None, None, stick)
        return str(caught.exception)

    def test_a_stick_that_lost_most_parts_is_called_a_wrong_size_stick_and_is_named(self):
        # 16 of the 32 readback stops looked like this: 37 to 82 of 85-92 parts different.
        message = self.payload(range(1, 76), 85, "General UDisk 8 GiB")
        self.assertIn("General UDisk 8 GiB", message)
        self.assertIn("reporting a size it does not have", message)
        self.assertIn("Use a different USB stick", message)
        self.assertIn("Nothing on this PC was changed", message)

    def test_a_stick_that_lost_a_few_parts_is_called_failing_and_offered_another_port(self):
        # the other 16: one to nineteen parts, rewritten once, still wrong
        message = self.payload([2], 92, "Kingston DataTraveler 3.0 29 GiB")
        self.assertIn("Kingston DataTraveler 3.0 29 GiB", message)
        self.assertIn("written a second time", message)
        self.assertIn("another USB port", message)
        self.assertNotIn("reporting a size it does not have", message)

    def test_NEGATIVE_CONTROL_a_clean_readback_raises_nothing_at_all(self):
        # Without this, both arms above would pass if _write_payload simply always raised.
        from p1401 import machine_handoff
        got = {"image": "Z:\\i.dmg", "chunklist": os.devnull, "chunks": 85}
        with patch.object(apple, "download", lambda *a, **k: got), \
                patch.object(apple, "parse_chunklist", lambda d: [(1, b"")] * 85), \
                patch.object(apple, "verify_written", lambda *a, **k: []), \
                patch.object(usbwriter, "_copy_settled", lambda *a: None), \
                patch.object(usbwriter, "verify_efi_copy", lambda *a, **k: None), \
                patch.object(usbwriter, "needs_nullmoth", lambda d: False), \
                patch.object(usbwriter, "copy_finish_setup", lambda root: None), \
                patch("builtins.print", lambda *a, **k: None):
            out = usbwriter._write_payload("Z:\\", "C:\\efi", info(), None, None, "General UDisk 8 GiB")
        self.assertEqual(out["root"], "Z:\\")


if __name__ == "__main__":
    unittest.main(verbosity=2)
