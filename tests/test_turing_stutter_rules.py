"""Tests for Turing micro-stutter and small BAR1 optimization rules in nullmoth-rules.json."""
import json
import pathlib
import re
import unittest

RULES_PATH = pathlib.Path(__file__).resolve().parents[1] / "mac/Resources/nullmoth-rules.json"


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
        self.assertEqual(conf.get("NVMTL_NO_SURFACE_PAGEOFF"), "0", "Surface page-off must be disabled")
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


if __name__ == "__main__":
    unittest.main()
