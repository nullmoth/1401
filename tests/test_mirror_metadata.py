import unittest
from p1401.mirror_metadata import release_index

class MirrorMetadata(unittest.TestCase):
    def test_first_tag_kept_frontend_omitted(self):
        data=b'<script>frontend</script>\n<a href="/vendor/driver/releases/tag/v2.0">new</a>\n<a href="/vendor/driver/releases/tag/v1.0">old</a>'
        result=release_index('https://github.com/vendor/driver/releases',data)
        self.assertEqual(result,b'<a href="/vendor/driver/releases/tag/v2.0">release</a>\n')
    def test_driver_bytes_unchanged(self):
        data=b'PK\x03\x04binary driver payload'
        self.assertIs(release_index('https://github.com/vendor/driver/releases/download/v2/a.zip',data),data)
    def test_unknown_index_refused(self):
        with self.assertRaises(ValueError):release_index('https://github.com/vendor/driver/releases',b'<html>blocked</html>')
    def test_invalid_tag_refused(self):
        with self.assertRaises(ValueError):release_index('https://github.com/vendor/driver/releases',b'<a href="/vendor/driver/releases/tag/v2 bad">x</a>')
