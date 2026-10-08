import contextlib,hashlib,importlib.util,io,pathlib,tempfile,unittest,zipfile,sys
from unittest import mock
from p1401 import archive_download
from p1401.downloads import DownloadError

class ArchiveDownload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=pathlib.Path(__file__).parents[1]/'upstream/OpCore-Simplify/Scripts/resource_fetcher.py'
        spec=importlib.util.spec_from_file_location('archive_actual_fetcher',path)
        sys.path.insert(0,str(path.parent.parent))
        try:
            mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        finally:sys.path.pop(0)
        cls.Fetcher=mod.ResourceFetcher;cls.raw=staticmethod(cls.Fetcher.download_and_save_file)
    def fetcher(self,body):
        fetcher=object.__new__(self.Fetcher);fetcher.buffer_size=1024
        class Response(io.BytesIO):
            def getheader(self,name,default=None):return str(len(body)+500) if name=='Content-Length' else default
        fetcher._make_request=lambda url:Response(body);return fetcher
    def valid(self):
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as archive:archive.writestr('test.txt','fixture')
        return data.getvalue()
    def test_production_accepts_premature_eof_then_guard_preserves_archive(self):
        truncated=self.valid()[:-40]
        with tempfile.TemporaryDirectory() as temp,contextlib.redirect_stdout(io.StringIO()),mock.patch.object(archive_download.time,'sleep'):
            dest=pathlib.Path(temp)/'OpenCore.zip'
            self.assertTrue(self.raw(self.fetcher(truncated),'https://github.com/a/b/truncated.zip',dest));self.assertFalse(zipfile.is_zipfile(dest))
            dest.write_bytes(b'prior bytes')
            with self.assertRaisesRegex(DownloadError,'No dependency archive was replaced'):archive_download.harden(self.raw)(self.fetcher(truncated),'https://github.com/a/b/truncated.zip',dest)
            self.assertEqual(dest.read_bytes(),b'prior bytes');self.assertFalse(list(pathlib.Path(temp).glob('*.partial')))
    def test_html_keeps_hash_but_not_raw_response(self):
        body=b'<html>private account upstream error</html>'
        with tempfile.TemporaryDirectory() as temp,contextlib.redirect_stdout(io.StringIO()),mock.patch.object(archive_download.time,'sleep'):
            with self.assertRaises(DownloadError) as caught:archive_download.harden(self.raw)(self.fetcher(body),'https://github.com/a/b/sample.zip',pathlib.Path(temp)/'sample.zip')
            self.assertIn(hashlib.sha256(body).hexdigest(),str(caught.exception));self.assertNotIn('private account',str(caught.exception))
    def test_retry_valid_archive_and_preserved_checksum_policy(self):
        data=self.valid()
        with tempfile.TemporaryDirectory() as temp,contextlib.redirect_stdout(io.StringIO()),mock.patch.object(archive_download.time,'sleep'):
            dest=pathlib.Path(temp)/'dep.zip';bodies=iter([b'invalid',data]);fetcher=self.fetcher(b'')
            fetcher._make_request=lambda url:self.fetcher(next(bodies))._make_request(url)
            self.assertTrue(archive_download.harden(self.raw)(fetcher,'https://github.com/a/b/dep.zip',dest));self.assertEqual(dest.read_bytes(),data)
            pins=[]
            def original(self,url,path,pin):pins.append(pin);pathlib.Path(path).write_bytes(data);return True
            self.assertTrue(archive_download.harden(original)(None,'https://github.com/a/b/dep.zip',dest,'a'*64));self.assertEqual(pins,['a'*64])
    def test_failed_downloader_or_exception_preserves_prior_bytes(self):
        for failure in [False,OSError('fixture')]:
            with self.subTest(failure=type(failure).__name__),tempfile.TemporaryDirectory() as temp:
                dest=pathlib.Path(temp)/'dep.zip';dest.write_bytes(b'old')
                def original(self,url,path,pin):
                    pathlib.Path(path).write_bytes(b'partial')
                    if isinstance(failure,Exception):raise failure
                    return failure
                if isinstance(failure,Exception):
                    with self.assertRaises(OSError):archive_download.harden(original)(None,'https://github.com/a/b/dep.zip',dest)
                else:self.assertFalse(archive_download.harden(original)(None,'https://github.com/a/b/dep.zip',dest))
                self.assertEqual(dest.read_bytes(),b'old');self.assertFalse(list(pathlib.Path(temp).glob('*.partial')))
