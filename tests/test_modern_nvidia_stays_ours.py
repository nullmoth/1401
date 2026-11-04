"""The engine's own modern NVIDIA branch must not reach a 1401 build: nullmoth.apply is the only writer of those settings."""
import os
import unittest

from p1401 import engine


class ModernNvidiaStaysOurs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine._load_engine()
        from Scripts import config_prodigy, kext_maestro
        cls.cfg = config_prodigy.ConfigProdigy
        cls.km = kext_maestro

    def source(self, name):
        with open(os.path.join(engine.UPSTREAM, "Scripts", name), encoding="utf-8") as fh:
            return fh.read()

    def test_negative_control_the_engine_really_has_the_branch(self):
        self.assertIn("com.apple.iokit.IONDRVSupport", self.source("config_prodigy.py"))
        self.assertIn('"nvaccel=1"', self.source("config_prodigy.py"))
        self.assertIn("HighDelay", self.source("kext_maestro.py"))

    def test_no_iondrv_block_for_a_modern_card(self):
        kexts = self.km.KextMaestro().kexts
        for k in kexts:
            k.checked = False
        blocks = self.cfg.block_kext_bundle(object.__new__(self.cfg), True, "25.0.0", kexts)
        self.assertEqual([b for b in blocks if "IONDRV" in b["Identifier"]], [])

    def test_sip_value_is_the_engines_ordinary_one(self):
        c = object.__new__(self.cfg)
        c.utils = self.km.KextMaestro().utils
        self.assertEqual(self.cfg.csr_active_config(c, True, "25.0.0"), "030A0000")

    def test_report_copy_hides_only_the_modern_codename(self):
        gtx = {"Codename": "Kepler"}
        rtx = {"Codename": "Ada Lovelace", "Device ID": "10DE-2882"}
        report = {"GPU": {"a": gtx, "b": rtx}, "CPU": {"x": 1}}
        out = engine._without_modern_nvidia_codename(report)
        self.assertEqual(out["GPU"]["b"], {"Codename": "", "Device ID": "10DE-2882"})
        self.assertEqual(out["GPU"]["a"], gtx)
        self.assertEqual(out["CPU"], {"x": 1})
        self.assertEqual(rtx["Codename"], "Ada Lovelace", "the caller's report is not changed")

    def test_the_engine_still_stops_at_macos_26(self):
        from Scripts.datasets import os_data
        self.assertEqual(os_data.get_latest_darwin_version().split(".")[0], "25")

    def test_intel_wifi_answer_reads_the_menu(self):
        with_fork = "1. laobamac AirportItlwm - Native\n2. AirportItlwm - Uses\n3. itlwm - More stable"
        self.assertEqual(engine._intel_wifi_answer(with_fork), "3")
        self.assertEqual(engine._intel_wifi_answer("1. AirportItlwm - Uses\n2. itlwm - More stable"), "2")
        with self.assertRaises(engine.UnknownPrompt):
            engine._intel_wifi_answer("1. AirportItlwm - Uses only")

    def test_every_prompt_rule_matches_a_prompt_the_engine_really_asks(self):
        rule = next(r for r, _ in engine.PROMPT_RULES if "Wi-Fi" in r)
        self.assertIn("Select Intel Wi-Fi kext (default", self.source("kext_maestro.py"))
        self.assertTrue(rule.startswith("^Select Intel Wi-Fi kext"))

    def audio(self, tahoe_audio, simple, alc=True):
        from Scripts.datasets import kext_data
        kexts = self.km.KextMaestro().kexts
        idx = kext_data.kext_index_by_name
        kexts[idx["SimpleHDA"]].checked, kexts[idx["AppleALC"]].checked = simple, alc
        engine._tahoe_audio_keep_choice(kexts, tahoe_audio)
        return kexts[idx["SimpleHDA"]].checked, kexts[idx["AppleALC"]].checked

    def test_the_voodoohda_choice_selects_no_audio_kext(self):
        self.assertEqual(self.audio("voodoohda", True), (False, False))

    def test_the_applealc_choice_keeps_applealc_and_never_simplehda(self):
        self.assertEqual(self.audio("applealc", False), (False, True))
        self.assertEqual(self.audio("applealc", True), (False, True))

    def test_macos_15_keeps_applealc_where_no_menu_was_shown(self):
        self.assertEqual(self.audio("voodoohda", False), (False, True))

    def test_engine_fetcher_uses_1401s_verified_context(self):
        from Scripts import resource_fetcher as rf
        from p1401 import tls
        tls.install()
        self.assertIs(rf.get_ssl_context(), tls.context())
        self.assertIs(rf.ResourceFetcher().ssl_context, tls.context())


if __name__ == "__main__":
    unittest.main()
