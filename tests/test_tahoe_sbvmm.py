"""Tahoe (macOS 26) stops at the prohibited sign on a Mac model Apple did not ship it for, both on a fresh boot and
when finishing an update from Sequoia. macOS 26's secure-boot model-version check is answered by RestrictEvents'
revpatch=sbvmm. The build adds that boot argument for a Tahoe build that carries RestrictEvents, merging it with any
revpatch already present, and leaves Sequoia builds alone."""
import os
import plistlib
import tempfile
import unittest

from p1401 import engine, policy
from p1401.policy import BOOT


def build(darwin, restrict_events=True, boot_args=None):
    t = tempfile.mkdtemp()
    path = os.path.join(t, "config.plist")
    add = {}
    if boot_args is not None:
        add["boot-args"] = boot_args
    kernel_add = []
    if restrict_events:
        kernel_add.append({"BundlePath": "RestrictEvents.kext", "Enabled": True})
    cfg = {"NVRAM": {"Add": {BOOT: add}, "Delete": {}}, "Kernel": {"Add": kernel_add, "Patch": [], "Quirks": {}},
           "Booter": {"Quirks": {}, "MmioWhitelist": []}, "Misc": {}, "ACPI": {"Add": [], "Delete": []},
           "UEFI": {"Drivers": [], "Quirks": {}}, "PlatformInfo": {"Generic": {}}}
    with open(path, "wb") as f:
        plistlib.dump(cfg, f)
    res = engine.BuildResult(ok=True, out_dir=t, macos_version=darwin,
                             hardware={"CPU": {"Manufacturer": "Intel"}, "GPU": {}})
    changes = policy.apply(path, res, engine.Policy())
    with open(path, "rb") as f:
        cfg = plistlib.load(f)
    return (cfg["NVRAM"]["Add"][BOOT].get("boot-args", "")).split(), {c["rule"] for c in changes}


class TahoeSbvmm(unittest.TestCase):
    def test_tahoe_build_gets_revpatch_sbvmm(self):
        args, rules = build("25.0.0")
        self.assertIn("revpatch=sbvmm", args)
        self.assertIn("tahoe-sbvmm", rules)

    def test_sequoia_build_does_not(self):
        args, rules = build("24.6.0")
        self.assertNotIn("revpatch=sbvmm", args)
        self.assertNotIn("tahoe-sbvmm", rules)

    def test_without_restrictevents_the_arg_is_not_added(self):
        # revpatch=sbvmm only works through RestrictEvents, so it is pointless without it.
        args, rules = build("25.0.0", restrict_events=False)
        self.assertNotIn("revpatch=sbvmm", args)
        self.assertNotIn("tahoe-sbvmm", rules)

    def test_existing_revpatch_value_is_merged_not_replaced(self):
        args, _ = build("25.0.0", boot_args="-v revpatch=memtab")
        revs = [a for a in args if a.startswith("revpatch=")]
        self.assertEqual(len(revs), 1)
        self.assertEqual(set(revs[0].split("=", 1)[1].split(",")), {"memtab", "sbvmm"})
        self.assertIn("-v", args)

    def test_sbvmm_already_present_is_left_alone(self):
        args, rules = build("25.0.0", boot_args="revpatch=sbvmm")
        self.assertEqual([a for a in args if a.startswith("revpatch=")], ["revpatch=sbvmm"])
        self.assertNotIn("tahoe-sbvmm", rules)


if __name__ == "__main__":
    unittest.main()
