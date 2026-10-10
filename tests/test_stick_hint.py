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

    def test_negative_control_other_failures_get_no_stick_advice(self):
        for e in [RuntimeError("The scan changed after the EFI was built."), OSError(2, "No such file or directory"),
                  ValueError("bad plist")]:
            self.assertEqual(usbwriter.stick_hint(e), "", repr(e))


if __name__ == "__main__":
    unittest.main()
