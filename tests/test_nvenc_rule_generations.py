"""The per-system rules must not turn the hardware encoder off on a generation the driver has encoders for.

The rule that wrote NVMTL_NO_NVENC was made when only Blackwell encoded. It kept matching Turing and Ampere after the
driver gained their encoders, so every 1401 install on those cards had no NVIDIA encoder (an RTX 3080 Ti encoded
H.264 and HEVC 8 of 8 frames once the knobs were removed)."""
import json
import pathlib
import unittest

RULES = pathlib.Path(__file__).resolve().parents[1] / "mac/Resources/nullmoth-rules.json"
ENCODES = {"turing", "ampere", "blackwell"}  # generations with an encoder library in the driver


def encoder_off_generations(rules):
    off = set()
    for rule in rules["rules"]:
        conf = rule.get("conf", {})
        if conf.get("NVMTL_NO_NVENC") == "1" or conf.get("NVMTL_NO_NVENC_HEVC") == "1":
            arch = rule.get("match", {}).get("arch")
            off |= set(arch) if arch else {"every generation"}
    return off


class NvencRuleGenerations(unittest.TestCase):
    def test_no_rule_turns_the_encoder_off_where_the_driver_has_one(self):
        off = encoder_off_generations(json.loads(RULES.read_text()))
        self.assertFalse(off & ENCODES or "every generation" in off, f"encoder turned off on {sorted(off)}")

    def test_the_old_rule_is_caught(self):
        old = {"rules": [{"match": {"arch": ["turing", "ampere", "ada"]}, "conf": {"NVMTL_NO_NVENC": "1"}}]}
        self.assertEqual(encoder_off_generations(old) & ENCODES, {"turing", "ampere"})


if __name__ == "__main__":
    unittest.main()
