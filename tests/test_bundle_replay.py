"""tools/machine_bundle_replay.py: config read-back and the comparison with stick-log evidence."""
import os
import plistlib
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import machine_bundle_replay as R  # noqa: E402

Q = {"VirtualMap": True}


_n = iter(range(10**6))


def rec(cpu, quirks, passed):
    return {"batch": f"{cpu}-{next(_n)}", "cpu": cpu, "quirks": quirks, "passed": passed, "failed": not passed}


class Replay(unittest.TestCase):
    def test_config_facts_read_back_the_settings_a_boot_is_traced_to(self):
        cfg = {"Booter": {"Quirks": {"SetupVirtualMap": True}}, "Kernel": {"Quirks": {"AppleXcpmCfgLock": True},
               "Add": [{"BundlePath": "Lilu.kext", "Enabled": True}, {"BundlePath": "Off.kext", "Enabled": False}]},
               "UEFI": {"Quirks": {}}, "ACPI": {"Add": [{"Path": "SSDT-EC.aml", "Enabled": True}]},
               "NVRAM": {"Add": {"7C436110-AB2A-4BBB-A880-FE41995C9F82": {"boot-args": "-v"}}},
               "PlatformInfo": {"Generic": {"SystemProductName": "MacPro7,1"}}}
        path = os.path.join(tempfile.mkdtemp(), "config.plist")
        with open(path, "wb") as fh:
            plistlib.dump(cfg, fh)
        f = R.config_facts(path)
        self.assertEqual(f["kexts"], ["Lilu.kext"])
        self.assertEqual((f["boot_args"], f["acpi"], f["smbios"]), ("-v", ["SSDT-EC.aml"], "MacPro7,1"))

    def test_a_quirk_set_that_failed_on_this_cpu_while_another_passed_is_flagged_known_bad(self):
        bad = {"SetupVirtualMap": True, "DevirtualiseMmio": True}
        good = {"SetupVirtualMap": False, "DevirtualiseMmio": True}
        records = [rec("12600KF", bad, False) for _ in range(5)] + [rec("12600KF", bad, True)] + \
                  [rec("12600KF", good, True) for _ in range(6)]
        build = {"bundle": "b1", "cpu": "12th Gen Intel(R) Core(TM) i5-12600KF", "config": {"booter": bad}}
        out = R.compare_to_stick_logs([build], records)
        self.assertEqual(out["known-bad"], ["b1"])
        build["config"] = {"booter": good}
        self.assertEqual(R.compare_to_stick_logs([build], records)["matches"], 1)

    def test_a_cpu_with_no_stick_logs_is_counted_not_passed(self):
        out = R.compare_to_stick_logs([{"bundle": "b", "cpu": "Intel(R) Core(TM) i7-9700K", "config": {"booter": {}}}], [])
        self.assertEqual(out["no-evidence"], 1)


if __name__ == "__main__":
    unittest.main()
