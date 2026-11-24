"""The GitHub -> verified mirror fallback in downloads.make_request. No network: urlopen is a stand-in."""
import hashlib, io, json, os, socket, tempfile, unittest, urllib.error
from types import SimpleNamespace
from unittest.mock import patch

from p1401 import downloads, mirror

URL = 'https://github.com/acidanthera/Lilu/releases/download/1.0.0/Lilu-1.0.0-RELEASE.zip'
OTHER = 'https://raw.githubusercontent.com/dortania/build-repo/builds/other.json'
BODY = b'recorded Lilu zip'
SHA = hashlib.sha256(BODY).hexdigest()


class Served(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class Fallback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self.tmp.name, 'mirror.json')
        with open(path, 'w') as fh:
            json.dump({'schema': 1, 'entries': {URL: {'sha256': SHA, 'size': len(BODY)}}}, fh)
        mirror.entries(path)
        mirror._state['preferred'] = False
        self.fetcher = SimpleNamespace(request_headers={'User-Agent': '1401'}, ssl_context=None)
        self.asked, self.mirror_body = [], BODY

    def tearDown(self):
        mirror._state.update(entries=None, preferred=False)
        self.tmp.cleanup()

    def urlopen(self, request, timeout=None, context=None):
        self.asked.append(request.full_url)
        if request.full_url.startswith(mirror.BASE):
            return Served(self.mirror_body)
        raise urllib.error.URLError(ConnectionResetError(10054, 'reset'))

    def run_request(self, url):
        with patch('urllib.request.urlopen', self.urlopen), patch.object(downloads.time, 'sleep', lambda s: None):
            return downloads.make_request(self.fetcher, url)

    def test_blocked_github_gets_the_recorded_bytes_from_the_mirror(self):
        got = self.run_request(URL)
        self.assertEqual(got.read(), BODY)
        self.assertEqual(self.asked[-1], mirror.BASE + SHA)
        self.assertTrue(any('github.com' in a for a in self.asked[:-1]))

    def test_after_one_mirror_rescue_the_mirror_is_asked_first(self):
        self.run_request(URL)
        self.asked.clear()
        self.run_request(URL)
        self.assertEqual(self.asked, [mirror.BASE + SHA])

    def test_negative_control_a_url_outside_the_manifest_keeps_the_github_error(self):
        with self.assertRaisesRegex(downloads.DownloadError, 'Could not download from'):
            self.run_request(OTHER)
        self.assertFalse(any(a.startswith(mirror.BASE) for a in self.asked))

    def test_a_tampered_mirror_file_is_refused_and_both_failures_are_named(self):
        self.mirror_body = BODY[:-1] + b'X'
        with self.assertRaises(downloads.DownloadError) as caught:
            self.run_request(URL)
        self.assertIn('Could not download from', str(caught.exception))
        self.assertIn('refused', str(caught.exception))
        self.assertFalse(mirror.preferred())

    def test_working_github_never_touches_the_mirror(self):
        def ok(request, timeout=None, context=None):
            self.asked.append(request.full_url)
            return Served(b'live')
        with patch('urllib.request.urlopen', ok):
            self.assertEqual(downloads.make_request(self.fetcher, URL).read(), b'live')
        self.assertEqual(self.asked, [URL])


LISTING = 'https://raw.githubusercontent.com/dortania/build-repo/builds/latest.json'
PAGE = 'https://github.com/Mieze/RTL812xLucy/releases'
RECORDED = b'{"Lilu": "the recorded index"}'


class PinnedListings(unittest.TestCase):
    """A listing the release recorded is read from the mirror even while GitHub works, so the build asks for the
    versions the mirror holds; binaries and unrecorded listings still come from GitHub first."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self.tmp.name, 'mirror.json')
        sha = hashlib.sha256(RECORDED).hexdigest()
        with open(path, 'w') as fh:
            json.dump({'schema': 1, 'entries': {
                LISTING: {'sha256': sha, 'size': len(RECORDED)},
                PAGE: {'sha256': sha, 'size': len(RECORDED), 'metadata_kind': 'release-tag', 'source_sha256': sha},
                URL: {'sha256': SHA, 'size': len(BODY)}}}, fh)
        mirror.entries(path)
        mirror._state['preferred'] = False
        self.fetcher = SimpleNamespace(request_headers={'User-Agent': '1401'}, ssl_context=None)
        self.asked = []

    def tearDown(self):
        mirror._state.update(entries=None, preferred=False)
        self.tmp.cleanup()

    def live(self, request, timeout=None, context=None):
        self.asked.append(request.full_url)
        if request.full_url.startswith(mirror.BASE):
            return Served(RECORDED)
        return Served(b'live and newer')

    def get(self, url):
        with patch('urllib.request.urlopen', self.live):
            return downloads.make_request(self.fetcher, url).read()

    def test_the_recorded_dependency_index_wins_over_a_newer_live_one(self):
        self.assertEqual(self.get(LISTING), RECORDED)
        self.assertTrue(self.asked[0].startswith(mirror.BASE))

    def test_a_recorded_release_page_is_read_from_the_mirror(self):
        self.assertEqual(self.get(PAGE), RECORDED)

    def test_negative_control_a_recorded_binary_still_comes_from_github_first(self):
        self.assertEqual(self.get(URL), b'live and newer')
        self.assertEqual(self.asked, [URL])

    def test_negative_control_an_unrecorded_listing_is_read_live(self):
        self.assertEqual(self.get(OTHER), b'live and newer')
        self.assertEqual(self.asked, [OTHER])

    def test_pinning_does_not_switch_the_whole_build_to_the_mirror(self):
        self.get(LISTING)
        self.assertFalse(mirror.preferred())


class Selftest(unittest.TestCase):
    def test_module_selftest(self):
        self.assertTrue(mirror.selftest())


if __name__ == '__main__':
    unittest.main()
