"""Tests for Turing micro-stutter rules and standalone tool safety guards."""
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "mac/Resources/nullmoth-rules.json"
SETUP_PATH = ROOT / "mac/Resources/nullmoth-setup.sh"
TOOL_PATH = ROOT / "tools/apply-turing-fix.sh"
LEGACY_RES_SCRIPT = ROOT / "mac/Resources/nullmoth-turing-optimize.sh"


class TuringStutterRulesTest(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        self.rules = self.data.get("rules", [])

    def test_turing_stutter_rule_exists_and_configured(self):
        rule = next((r for r in self.rules if r.get("id") == "turing-bar1-stutter-optimization"), None)
        self.assertIsNotNone(rule, "turing-bar1-stutter-optimization rule must exist in nullmoth-rules.json")

        match = rule.get("match", {})
        self.assertEqual(match.get("arch"), ["turing"], "Rule must match turing architecture")

        conf = rule.get("conf", {})
        self.assertEqual(conf.get("NVMTL_VRAM_HEADROOM_MB"), "48", "VRAM headroom must be 48MB for small BAR1")
        self.assertEqual(conf.get("NVMTL_NO_SURFACE_PAGEOFF"), "0", "Surface page-off must not be forced off")
        self.assertEqual(conf.get("NVMTL_NO_BUFREUSE"), "1", "Buffer reuse must be disabled")
        self.assertEqual(conf.get("NVMTL_CMD_POOL_MAX_CHUNKS"), "256")

        # Validate that no rule breaks hardware video encoding on Turing
        self.assertNotIn("NVMTL_NO_NVENC", conf)
        self.assertNotIn("NVMTL_NO_NVENC_HEVC", conf)

    def test_all_rule_conf_keys_and_values_valid_for_profile_swift(self):
        key_re = re.compile(r"^(NVMTL|NVK|NVRM)_[A-Z0-9_]+$")
        val_re = re.compile(r"^[A-Za-z0-9._-]{0,64}$")

        for rule in self.rules:
            for k, v in rule.get("conf", {}).items():
                self.assertTrue(key_re.match(k), f"Invalid conf key: {k} in rule {rule.get('id')}")
                self.assertTrue(val_re.match(str(v)), f"Invalid conf value: {v} in rule {rule.get('id')}")

    def test_setup_script_does_not_patch_signed_kext_binaries(self):
        setup_src = SETUP_PATH.read_text(encoding="utf-8")
        for forbidden in ("patch_turing_stutter", "0x21ea3", "0x251e0", "0x23f1c", "NVAccel.orig.bin"):
            self.assertNotIn(forbidden, setup_src, f"nullmoth-setup.sh must not contain binary patcher token {forbidden}")
        self.assertFalse(LEGACY_RES_SCRIPT.exists(), "duplicate script must not live in mac/Resources/")

    def test_standalone_tool_has_version_checksum_and_rollback_guards(self):
        self.assertTrue(TOOL_PATH.is_file(), "tools/apply-turing-fix.sh must exist")
        src = TOOL_PATH.read_text(encoding="utf-8")
        self.assertTrue(src.startswith("#!/bin/bash\n"), "apply-turing-fix.sh must use LF line endings and bash shebang")
        self.assertNotIn("\r", src, "apply-turing-fix.sh must not contain CRLF line endings")
        self.assertIn('EXPECTED_OS_MAJOR="15"', src)
        self.assertIn('EXPECTED_DRIVER_VERSION="3.0"', src)
        self.assertIn("shasum -a 256 --strict -c SHA256SUMS", src)
        self.assertIn("rollback_on_error", src)
        self.assertIn("kmutil inspect", src)
        self.assertIn("# --- 1401 turing-fix ---", src)


if __name__ == "__main__":
    unittest.main()
