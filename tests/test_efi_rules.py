"""efi_rules.json is what the Mac app checks an installed EFI against; policy.py is what the Windows builder applies. These
tests keep the two the same rule: a config policy.py built passes every rule, the same config before policy.py is
flagged with exactly the rules policy.py changed, and fixing the flagged issues leaves nothing to flag."""
import ast
import copy
import os
import plistlib
import tempfile
import unittest

from p1401 import efi_rules, engine, policy

BOOT = policy.BOOT

# Hardware shapes taken from real reports in the support chats and the policy tests: (label, report, Darwin version).
SHAPES = [
    ("Zen 4 AM5 desktop", {"CPU": {"Manufacturer": "AMD", "Processor Name": "AMD Ryzen 5 7600 6-Core Processor", "Codename": "Raphael"},
                           "Motherboard": {"Name": "PRO B650M-A", "Chipset": "", "Platform": "Desktop"}}, "24.6.0"),
    ("Zen 3 B550 desktop", {"CPU": {"Manufacturer": "AMD", "Processor Name": "AMD Ryzen 7 5800X 8-Core Processor", "Codename": "Vermeer"},
                            "Motherboard": {"Name": "B550 AORUS", "Chipset": "B550", "Platform": "Desktop"}}, "24.6.0"),
    ("Core Ultra desktop", {"CPU": {"Manufacturer": "Intel", "Processor Name": "Intel(R) Core(TM) Ultra 5 225F", "Codename": "Arrow Lake"},
                            "Motherboard": {"Name": "B860", "Chipset": "", "Platform": "Desktop"}}, "24.6.0"),
    ("Core Ultra laptop", {"CPU": {"Manufacturer": "Intel", "Processor Name": "Intel(R) Core(TM) Ultra 7 255HX", "Codename": "Arrow Lake"},
                           "Motherboard": {"Name": "Laptop", "Chipset": "", "Platform": "Laptop"}}, "24.6.0"),
    ("Raptor Lake desktop", {"CPU": {"Manufacturer": "Intel", "Processor Name": "13th Gen Intel(R) Core(TM) i7-13700K", "Codename": "Raptor Lake"},
                             "Motherboard": {"Name": "Z790", "Chipset": "", "Platform": "Desktop"}}, "24.6.0"),
    ("Comet Lake desktop", {"CPU": {"Manufacturer": "Intel", "Processor Name": "Intel(R) Core(TM) i5-10400", "Codename": "Comet Lake"},
                            "Motherboard": {"Name": "B460", "Chipset": "", "Platform": "Desktop"}}, "24.6.0"),
    ("Tahoe, AMD card, no iGPU", {"CPU": {"Manufacturer": "AMD", "Processor Name": "AMD Ryzen 7 5800X 8-Core Processor", "Codename": "Vermeer"},
                                  "Motherboard": {"Name": "X570", "Chipset": "X570", "Platform": "Desktop"},
                                  "GPU": {"RX 6600": {"Manufacturer": "AMD", "Device Type": "Discrete GPU"}}}, "25.0.0"),
    ("Tahoe, Intel desktop", {"CPU": {"Manufacturer": "Intel", "Processor Name": "Intel(R) Core(TM) i5-10400", "Codename": "Comet Lake"},
                              "Motherboard": {"Name": "B460", "Chipset": "", "Platform": "Desktop"}}, "25.0.0"),
]


def engine_like():
    """A config with every setting the rules care about set the way upstream configs ship it (each one wrong for some
    machine), plus the structural faults the validator refuses."""
    return {
        "ACPI": {"Add": [{"Path": "SSDT-EC.aml", "Enabled": True}, {"Path": "SSDT-EC.aml", "Enabled": True}], "Delete": []},
        "Booter": {"MmioWhitelist": [{"Address": 4278190080, "Enabled": True}],
                   "Quirks": {"DevirtualiseMmio": True, "SetupVirtualMap": True, "ProvideCustomSlide": True,
                              "AvoidRuntimeDefrag": True, "AllowRelocationBlock": False, "DisableVariableWrite": False}},
        "Kernel": {"Add": [{"BundlePath": n, "Enabled": True} for n in
                           ("Lilu.kext", "WhateverGreen.kext", "IntelBluetoothFirmware.kext", "RestrictEvents.kext", "CpuTopologyRebuild.kext",
                            "USBToolBox.kext", "USBInjectAll.kext", "IntelMausi.kext", "IntelSnowMausi.kext")]
                          + [{"BundlePath": "NVMeFix.kext", "Enabled": False}],
                   "Block": [], "Patch": [{"Comment": "masked", "Replace": b"\xff\xff", "ReplaceMask": b"\x0f\x0f"}],
                   "Quirks": {"DisableIoMapper": False}},
        "Misc": {"Boot": {"HideAuxiliary": True, "ShowPicker": False, "PickerMode": "Apple"},
                 "Debug": {"Target": 3, "AppleDebug": False, "ApplePanic": False}, "Security": {"ExposeSensitiveData": 6}},
        "NVRAM": {"Add": {BOOT: {"boot-args": "-v ctrsmt=full keepsyms=1"}}, "Delete": {BOOT: ["boot-args"]}},
        "UEFI": {"Drivers": [{"Path": "OpenRuntime.efi", "Enabled": True}], "Quirks": {}},
        "PlatformInfo": {"Generic": {}},
    }


def run_policy(cfg, hardware, darwin):
    t = tempfile.mkdtemp()
    path = os.path.join(t, "config.plist")
    with open(path, "wb") as f:
        plistlib.dump(cfg, f)
    res = engine.BuildResult(ok=True, out_dir=t, macos_version=darwin, hardware=copy.deepcopy(hardware))
    changes = policy.apply(path, res, engine.Policy())
    with open(path, "rb") as f:
        return plistlib.load(f), changes


def policy_rule_ids():
    """Every rule name policy.py can record, read with a parser: change("id", ...) calls and {"rule": "id"} dicts."""
    with open(policy.__file__, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "change" and node.args \
                and isinstance(node.args[0], ast.Constant):
            ids.add(node.args[0].value)
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value == "rule" and isinstance(v, ast.Constant):
                    ids.add(v.value)
    return ids


class EfiRules(unittest.TestCase):
    def setUp(self):
        self.rules = efi_rules.load()
        self.ids = {r["id"] for r in self.rules["rules"]}

    def test_every_policy_rule_is_a_check_or_named_builder_only(self):
        found = policy_rule_ids()
        self.assertGreater(len(found), 20, "the parser found too few rule names to trust")
        accounted = self.ids | set(self.rules["builder_only"]["ids"])
        self.assertEqual(found - accounted, set(), "policy.py records a rule efi_rules.json does not know")
        self.assertEqual((self.ids | set(self.rules["builder_only"]["ids"])) - found - {"arrow-lake-ctrsmt"}, set(),
                         "efi_rules.json names a rule policy.py no longer has")

    def test_a_config_policy_built_passes_every_rule(self):
        for label, hw, darwin in SHAPES:
            built, _ = run_policy(engine_like(), hw, darwin)
            issues = efi_rules.check(built, efi_rules.facts_from_report(hw, darwin), "stick", self.rules)
            self.assertEqual([i["id"] for i in issues], [], f"{label}: policy.py built a config the rules flag")

    def test_before_policy_the_checker_flags_exactly_what_policy_changed(self):
        for label, hw, darwin in SHAPES:
            raw = engine_like()
            flagged = {i["id"] for i in efi_rules.check(raw, efi_rules.facts_from_report(hw, darwin), "stick", self.rules)}
            _, changes = run_policy(raw, hw, darwin)
            changed = {c["rule"] for c in changes} & self.ids
            self.assertEqual(flagged, changed, f"{label}: the checker and policy.py disagree")
            self.assertTrue(flagged, f"{label}: the bad config was not flagged at all")

    def test_fixing_the_flagged_issues_leaves_nothing_and_never_touches_the_input(self):
        for label, hw, darwin in SHAPES:
            raw = engine_like()
            before = copy.deepcopy(raw)
            facts = efi_rules.facts_from_report(hw, darwin)
            issues = efi_rules.check(raw, facts, "stick", self.rules)
            fixed = efi_rules.fix(raw, issues)
            self.assertEqual(raw, before, f"{label}: fix() changed its input")
            self.assertEqual(efi_rules.check(fixed, facts, "stick", self.rules), [], f"{label}: issues left after fixing")
            self.assertEqual(efi_rules.fix(fixed, efi_rules.check(fixed, facts, "stick", self.rules)), fixed,
                             f"{label}: a second fix changed a fixed config")

    def test_a_rule_never_fires_on_hardware_it_does_not_match(self):
        hw = dict(SHAPES[5][1])   # Comet Lake: not AMD, not hybrid, not Core Ultra
        flagged = {i["id"] for i in efi_rules.check(engine_like(), efi_rules.facts_from_report(hw, "24.6.0"), "stick", self.rules)}
        for rid in ("amd-zen4-memory-map", "amd-devirtualisemmio", "hybrid-intel-devmmio", "core-ultra-drop-dmar", "tahoe-intel-bt"):
            self.assertNotIn(rid, flagged)
        self.assertIn("boot-logs-on-stick", flagged)   # and the guard does fire for what applies to every machine

    def test_installer_only_rules_stay_off_an_installed_mac(self):
        hw = SHAPES[5][1]
        stick = {i["id"] for i in efi_rules.check(engine_like(), efi_rules.facts_from_report(hw, "24.6.0"), "stick", self.rules)}
        installed = {i["id"] for i in efi_rules.check(engine_like(), efi_rules.facts_from_report(hw, "24.6.0"), "installed", self.rules)}
        self.assertIn("show-installer-entry", stick)
        self.assertNotIn("show-installer-entry", installed)

    def test_firmware_with_vt_d_off_is_not_told_to_drop_dmar(self):
        hw = SHAPES[2][1]   # Core Ultra desktop
        facts = efi_rules.facts_from_report(hw, "24.6.0")
        self.assertIn("core-ultra-drop-dmar", {i["id"] for i in efi_rules.check(engine_like(), facts, "installed", self.rules)})
        facts["fact"] = facts["fact"] + ["firmware_no_dmar"]
        self.assertNotIn("core-ultra-drop-dmar", {i["id"] for i in efi_rules.check(engine_like(), facts, "installed", self.rules)})

    def test_every_rule_has_the_text_the_app_shows(self):
        for r in self.rules["rules"]:
            for key in ("title", "what", "steps", "source"):
                self.assertTrue(r.get(key), f"{r['id']} has no {key}")
            self.assertTrue(set(r["scope"]) <= {"stick", "installed"}, r["id"])

    def test_a_rule_the_checker_cannot_read_stops_instead_of_passing(self):
        bad = {"rules": [{"id": "x", "scope": ["installed"], "match": {"gpu_vendr": "AMD"}, "expect": [], "title": "", "what": "", "steps": [], "restart": False}]}
        with self.assertRaises(ValueError):
            efi_rules.check({}, {}, "installed", bad)


if __name__ == "__main__":
    unittest.main()
