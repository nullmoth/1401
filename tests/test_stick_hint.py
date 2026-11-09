"""A write that dies because the USB stick did says so and says what to do (1.9.0 logs, 10-10). No hardware."""
import unittest

from p1401 import usbwriter


class StickHint(unittest.TestCase):
    def test_each_stick_failure_from_the_logs_gets_the_advice(self):
        cases = [
            OSError(22, "Invalid argument"),                     # EINVAL copying the driver package (SanDisk Cruzer Blade)
            OSError(5, "Input/output error"),
            OSError("the stick's file could not be reopened"),   # Toshiba TransMemory-Mx at 29 %
            usbwriter.UsbError("Format-Volume: Invalid Parameter; format.com: Invalid media or Track 0 bad - disk unusable."),
        ]
        for e in cases:
            self.assertEqual(usbwriter.stick_hint(e), usbwriter.STICK_ADVICE, repr(e))

    def test_access_denied_names_windows_security_not_the_stick(self):
        # Python on Windows raises WinError 5 as PermissionError with errno 13 and winerror 5; build it the same way
        e = PermissionError(13, "Access is denied", r"X:\com.apple.recovery.boot\BaseSystem.dmg")
        e.winerror = 5
        for err in (e, OSError("[WinError 5] Access is denied: 'X:\\com.apple.recovery.boot'")):
            hint = usbwriter.stick_hint(err)
            self.assertEqual(hint, usbwriter.ACCESS_ADVICE, repr(err))
            self.assertIn("Controlled folder access", hint)
            self.assertNotIn("rear USB port", hint)

    def test_files_gone_from_the_build_name_antivirus_quarantine(self):
        for reasons in (["kext missing on disk: WhateverGreen.kext"], ["UEFI driver missing on disk: apfs_aligned.efi (EFI/OC/Drivers holds: nothing)"],
                        ["kext executable missing: Lilu.kext/Contents/MacOS/Lilu"]):
            self.assertEqual(usbwriter.gone_hint(reasons), usbwriter.GONE_ADVICE, reasons)
            self.assertIn("quarantine", usbwriter.gone_hint(reasons))
        self.assertEqual(usbwriter.gone_hint(["PlatformInfo.Generic.MLB is empty", "Lilu.kext loads before Lilu"]), "")
        src = (__import__("pathlib").Path(usbwriter.__file__)).read_text()
        self.assertIn("'; '.join(reasons) + gone_hint(reasons))", src)

    def test_negative_control_other_failures_get_no_stick_advice(self):
        for e in [RuntimeError("The scan changed after the EFI was built."), OSError(2, "No such file or directory"),
                  PermissionError(13, "Permission denied"),
                  ValueError("bad plist")]:
            self.assertEqual(usbwriter.stick_hint(e), "", repr(e))


if __name__ == "__main__":
    unittest.main()
