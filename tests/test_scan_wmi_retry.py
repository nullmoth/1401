import unittest
import unittest.mock

from p1401 import scan


class ComError(Exception):
    """Shaped like wmi.x_wmi: the COM error rides on .com_error."""
    def __init__(self, code):
        super().__init__("Unexpected COM Error")
        self.com_error = (code, "OLE error 0x%08x" % (code & 0xFFFFFFFF), None, None)


class Collector:
    def __init__(self, fails, code=-2147217389):
        self.fails, self.code, self.calls = fails, code, 0

    def pnp_devices(self):
        self.calls += 1
        if self.calls <= self.fails:
            raise ComError(self.code)
        return "devices"


class WmiRetryTest(unittest.TestCase):
    def test_a_provider_that_loads_on_the_second_try_finishes_the_step(self):
        c, waits = Collector(fails=1), []
        scan.retry_wmi(c, ["pnp_devices", "not_on_this_platform"], sleep=waits.append)
        self.assertEqual(c.pnp_devices(), "devices")
        self.assertEqual((c.calls, waits), (2, [5]))

    def test_a_provider_that_never_loads_stops_with_the_repair_steps(self):
        c = Collector(fails=99)
        scan.retry_wmi(c, ["pnp_devices"], sleep=lambda s: None)
        with self.assertRaises(scan.ScanError) as cm:
            c.pnp_devices()
        self.assertIn("winmgmt /verifyrepository", str(cm.exception))
        self.assertEqual(c.calls, scan.WMI_TRIES)

    def test_a_class_whose_path_cannot_be_read_gets_the_same_retry_and_repair(self):
        # 1.15 scan: DISP_E_EXCEPTION wrapping 0x80004001 while reading Win32_PnPEntity's own path
        c = Collector(fails=99, code=-2147352567)
        orig = ComError.__init__

        def init(self, code):
            orig(self, code)
            self.com_error = (code, "DISP_E_EXCEPTION", (0, None, None, None, 0, -2147467263), None)
        with unittest.mock.patch.object(ComError, "__init__", init):
            scan.retry_wmi(c, ["pnp_devices"], sleep=lambda s: None)
            with self.assertRaises(scan.ScanError) as cm:
                c.pnp_devices()
        self.assertIn("winmgmt /verifyrepository", str(cm.exception))
        self.assertEqual(c.calls, scan.WMI_TRIES)

    def test_negative_control_any_other_com_error_is_not_retried(self):
        c = Collector(fails=1, code=-2147217392)   # WBEM_E_INVALID_CLASS
        scan.retry_wmi(c, ["pnp_devices"], sleep=lambda s: self.fail("slept on an error that is not retried"))
        with self.assertRaises(ComError):
            c.pnp_devices()
        self.assertEqual(c.calls, 1)

    def test_every_wrapped_name_is_a_step_of_the_sniffer(self):
        with open(scan.os.path.join(scan.SNIFFER, "Scripts", "platforms", "windows.py")) as fh:
            src = fh.read()
        for name in scan.WMI_COLLECTORS:
            self.assertIn("self.%s," % name, src)


if __name__ == "__main__":
    unittest.main()
