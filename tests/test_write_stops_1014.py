"""Four write stops from 1.15 logs that told the user nothing they could act on. No hardware, no network.

- oscdn through the DNS-over-HTTPS address answered HTTP 400 on the user's network (3 logs, 1.13 and 1.15); the same
  edges serve the file from elsewhere. The name is asked again once, then the stop names the network.
- PowerShell exited non-zero with no output and the STOP read "UsbError:" with nothing after it.
- The stick dropped off the bus mid-copy (WinError 433) and the STOP was shutil's whole per-file list.
- The driver package read back wrong from the stick and the write stopped without trying again or saying why."""
import hashlib
import os
import shutil
import socket
import subprocess
import tempfile
import unittest
import urllib.error
from unittest import mock

from p1401 import apple, nullmoth, usbwriter

CDN = "http://oscdn.apple.com/content/downloads/x/RecoveryImage/BaseSystem.dmg"


class Resp:
    status = 200

    def read(self, n=-1):
        return b"ok"

    def close(self):
        pass


def dns_fail():
    return urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))


class DohRefused(unittest.TestCase):
    def setUp(self):
        apple._doh_cache.clear()

    def run_open(self, by_name_results):
        seen, names = [], list(by_name_results)

        def urlopen(req, timeout=0):
            seen.append(req.full_url)
            if "17.253.1.2" in req.full_url:
                raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, None)
            r = names.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        with mock.patch("urllib.request.urlopen", urlopen):
            out = apple._open(CDN, {"Host": "oscdn.apple.com"}, sleep=lambda s: None, doh=lambda h: "17.253.1.2")
        return out, seen

    def test_a_400_at_the_doh_address_asks_by_name_again_and_succeeds(self):
        out, seen = self.run_open([dns_fail(), Resp()])
        self.assertIsInstance(out, Resp)
        self.assertEqual([("17.253.1.2" in u) for u in seen], [False, True, False])

    def test_a_400_at_the_doh_address_then_dns_failing_again_names_the_network(self):
        with self.assertRaises(apple.AppleError) as cm:
            self.run_open([dns_fail()] + [dns_fail()] * 20)
        self.assertIn("another network or a VPN", str(cm.exception))

    def test_negative_control_a_400_by_name_is_not_retried(self):
        seen = []

        def urlopen(req, timeout=0):
            seen.append(req.full_url)
            raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, None)
        with mock.patch("urllib.request.urlopen", urlopen), self.assertRaises(apple.AppleError) as cm:
            apple._open(CDN, {}, sleep=lambda s: None, doh=lambda h: "17.253.1.2")
        self.assertEqual(len(seen), 1)
        self.assertNotIn("VPN", str(cm.exception))


class SilentPowerShell(unittest.TestCase):
    def ps(self, rc, out="", err=""):
        done = subprocess.CompletedProcess([], rc, stdout=out, stderr=err)
        with mock.patch.object(usbwriter.platform, "system", return_value="Windows"), \
                mock.patch.object(usbwriter, "_system_tool", return_value="powershell.exe"), \
                mock.patch.object(usbwriter.subprocess, "run", return_value=done):
            return usbwriter._ps("Get-Disk")

    def test_a_silent_failure_names_the_exit_code(self):
        with self.assertRaises(usbwriter.UsbError) as cm:
            self.ps(-1073741502)
        self.assertIn("exit code -1073741502 (0xC0000142)", str(cm.exception))

    def test_negative_control_powershell_own_error_text_is_kept(self):
        with self.assertRaises(usbwriter.UsbError) as cm:
            self.ps(1, err="1401: disk 3 is not the USB stick you picked any more. Nothing was erased.\n")
        self.assertEqual(str(cm.exception), "1401: disk 3 is not the USB stick you picked any more. Nothing was erased.")


class StickGoneMidCopy(unittest.TestCase):
    def test_a_copy_that_lost_the_stick_stops_on_one_line_with_the_advice(self):
        err = shutil.Error([(r"C:\Users\someone\AppData\Local\NullMoth\1401\efi\EFI\OC\Kexts\BlueToolFixup.kext\Contents\Info.plist",
                             r"F:\EFI\OC\Kexts\BlueToolFixup.kext\Contents\Info.plist",
                             "[WinError 433] A device which does not exist was specified")] * 3)
        with mock.patch.object(usbwriter.shutil, "copytree", side_effect=err), self.assertRaises(usbwriter.UsbError) as cm:
            usbwriter._copy_settled("src", "dst", "F:\\", tries=2, sleep=lambda s: None)
        msg = str(cm.exception)
        self.assertIn("failed for 3 file(s): [WinError 433]", msg)
        self.assertNotIn("someone", msg)
        self.assertEqual(usbwriter.stick_hint(cm.exception), usbwriter.STICK_ADVICE)

    def test_negative_control_a_plain_oserror_is_raised_unchanged(self):
        err = OSError(2, "No such file or directory")
        with mock.patch.object(usbwriter.shutil, "copytree", side_effect=err), self.assertRaises(OSError) as cm:
            usbwriter._copy_settled("src", "dst", "F:\\", tries=2, sleep=lambda s: None)
        self.assertIs(cm.exception, err)
        self.assertEqual(usbwriter.stick_hint(cm.exception), "")


class DriverPackageReadBack(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.t)
        self.cache, self.usb = os.path.join(self.t, "cache"), os.path.join(self.t, "usb")
        os.makedirs(self.cache); os.makedirs(self.usb)
        body = b"driver package bytes"
        with open(os.path.join(self.cache, "pkg.tar.gz"), "wb") as fh:
            fh.write(body)
        self.pkg = {"name": "pkg.tar.gz", "url": "unused", "sha256": hashlib.sha256(body).hexdigest()}

    def stage(self, bad_copies):
        real, n = shutil.copyfile, [0]

        def copyfile(src, dst):
            real(src, dst)
            n[0] += 1
            if n[0] <= bad_copies:
                with open(dst, "r+b") as fh:
                    fh.write(b"X")
        with mock.patch.dict(nullmoth.PACKAGE, self.pkg), mock.patch("shutil.copyfile", copyfile):
            return nullmoth.stage(self.usb, self.cache), n[0]

    def test_one_bad_read_back_is_copied_again(self):
        dst, copies = self.stage(1)
        self.assertEqual(copies, 2)
        with open(dst, "rb") as fh:
            self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), self.pkg["sha256"])

    def test_two_bad_read_backs_stop_with_the_stick_advice(self):
        with self.assertRaises(RuntimeError) as cm:
            self.stage(5)
        self.assertEqual(usbwriter.stick_hint(cm.exception), usbwriter.STICK_ADVICE)
        self.assertFalse(os.path.exists(os.path.join(self.usb, "NullMoth", "pkg.tar.gz.part")))

    def test_negative_control_a_good_copy_is_copied_once(self):
        _, copies = self.stage(0)
        self.assertEqual(copies, 1)


if __name__ == "__main__":
    unittest.main()
