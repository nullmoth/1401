"""AMD GPU family classification: every device ID below is a real card, and most are device IDs seen in the field
uploads (support-cycle, 2026-10-14). The decision per family is what 1401 tells the user they will get. A card macOS
drives natively must never be called basic display; a card with no Apple driver (RDNA 3/4, RDNA iGPUs) must never be
called full acceleration. The negative controls prove a non-AMD GPU and an unknown AMD ID are handled, not misread."""
import unittest

from p1401 import amd_gpu


# (device id DDDD, expected path, a word the notice must contain). Field IDs are marked.
CASES = {
    # Native (Apple's own driver) - full acceleration.
    "67DF": (amd_gpu.NATIVE, "full acceleration"),       # Polaris 10 - RX 480/580
    "67EF": (amd_gpu.NATIVE, "full acceleration"),       # Polaris 11 - RX 460/560 (field)
    "6FDF": (amd_gpu.NATIVE, "full acceleration"),       # RX 580 2048SP
    "687F": (amd_gpu.NATIVE, "full acceleration"),       # Vega 64
    "66AF": (amd_gpu.NATIVE, "full acceleration"),       # Radeon VII
    "731F": (amd_gpu.NATIVE, "full acceleration"),       # Navi 10 - RX 5700 XT (field)
    "7340": (amd_gpu.NATIVE, "full acceleration"),       # Navi 14 - RX 5500 XT (field)
    "73BF": (amd_gpu.NATIVE, "full acceleration"),       # Navi 21 - RX 6800/6900 (field)
    "73DF": (amd_gpu.NATIVE, "full acceleration"),       # Navi 22 - RX 6700 XT (field)
    "73EF": (amd_gpu.NATIVE, "full acceleration"),       # Navi 23 - RX 6650 (field)
    "73FF": (amd_gpu.NATIVE, "full acceleration"),       # Navi 23 - RX 6600 (field)
    "743F": (amd_gpu.NATIVE, "full acceleration"),       # Navi 24 - RX 6400/6500
    # Pre-Polaris GCN - dropped by current macOS.
    "683F": (amd_gpu.NATIVE_LEGACY, "older AMD card"),   # Cape Verde (field)
    "6660": (amd_gpu.NATIVE_LEGACY, "older AMD card"),   # Mars (field)
    "6821": (amd_gpu.NATIVE_LEGACY, "older AMD card"),   # Pitcairn (Mac Pro D500)
    "7300": (amd_gpu.NATIVE_LEGACY, "older AMD card"),   # Fiji
    # RDNA 3 (RX 7000) - no Apple driver.
    "744C": (amd_gpu.RDNA3, "opt-in NullMoth test driver"),  # Navi 31 - RX 7900 XTX
    "747E": (amd_gpu.RDNA3, "opt-in NullMoth test driver"),  # Navi 32 - RX 7800 XT (field)
    "7480": (amd_gpu.RDNA3, "opt-in NullMoth test driver"),  # Navi 33 - RX 7600 (field)
    # RDNA 4 (RX 9070/9060) - experimental community only.
    "7550": (amd_gpu.RDNA4, "community"),                # Navi 48 - RX 9070 (field)
    "7590": (amd_gpu.RDNA4, "community"),                # Navi 44 - RX 9060
    # APU Vega iGPU - NootedRed covers it (not bundled).
    "15D8": (amd_gpu.APU_VEGA, "NootedRed"),             # Picasso (field)
    "1636": (amd_gpu.APU_VEGA, "NootedRed"),             # Renoir (field)
    "1638": (amd_gpu.APU_VEGA, "NootedRed"),             # Cezanne (field)
    # APU RDNA iGPU - no proven community driver.
    "1681": (amd_gpu.APU_RDNA, "no proven community driver"),  # Rembrandt (field)
    "164E": (amd_gpu.APU_RDNA, "no proven community driver"),  # Raphael (field)
    "15BF": (amd_gpu.APU_RDNA, "no proven community driver"),  # Phoenix 780M (field)
    "150E": (amd_gpu.APU_RDNA, "no proven community driver"),  # Strix (field)
}


def gpu(did, device_type="Discrete GPU"):
    return {"Manufacturer": "AMD", "Device ID": "1002-" + did, "Device Type": device_type}


class Families(unittest.TestCase):
    def test_every_family_maps_to_the_right_path_and_notice(self):
        for did, (path, word) in CASES.items():
            with self.subTest(device=did):
                family, got = amd_gpu.classify(gpu(did))
                self.assertEqual(got, path, f"1002-{did} -> {family!r}")
                self.assertIn(word, amd_gpu.note("Radeon", gpu(did)))

    def test_every_amd_notice_starts_with_graphics_so_the_app_shows_it(self):
        # MainForm.IsSupportNotice only surfaces notices starting with "Graphics:" (among others).
        for did in CASES:
            self.assertTrue(amd_gpu.note("Radeon", gpu(did)).startswith("Graphics:"))

    def test_native_is_never_called_basic_and_unsupported_is_never_called_full(self):
        self.assertNotIn("basic display", amd_gpu.note("RX 6700 XT", gpu("73DF")))
        self.assertIn("full acceleration after", amd_gpu.note("RX 6700 XT", gpu("73DF")))
        for did in ("744C", "7550", "15D8"):
            # none of the unsupported cards promises acceleration ("- full acceleration after macOS installs")
            self.assertNotIn("full acceleration after", amd_gpu.note("Radeon", gpu(did)))
            self.assertIn("basic display", amd_gpu.note("Radeon", gpu(did)))

    def test_lower_case_device_id_is_accepted(self):
        self.assertEqual(amd_gpu.classify({"Device ID": "1002-73df"})[1], amd_gpu.NATIVE)

    # --- negative controls: these must NOT be classified as a known AMD GPU ---
    def test_non_amd_gpu_is_not_classified(self):
        self.assertIsNone(amd_gpu.classify({"Manufacturer": "NVIDIA", "Device ID": "10DE-2D19"}))
        self.assertIsNone(amd_gpu.classify({"Manufacturer": "Intel", "Device ID": "8086-E340"}))
        self.assertIsNone(amd_gpu.note("GeForce", {"Device ID": "10DE-2D19"}))

    def test_an_unknown_amd_id_is_reported_not_silently_passed(self):
        family, path = amd_gpu.classify(gpu("1114"))  # a 1002 id in no table here
        self.assertEqual(path, amd_gpu.UNKNOWN)
        self.assertIn("report this device ID", amd_gpu.note("mystery", gpu("1114")))

    def test_placeholder_id_from_an_unreadable_card_is_unknown(self):
        # report.py plants 1002-0000 for an AMD card it could not read; it has no driver.
        self.assertEqual(amd_gpu.classify(gpu("0000"))[1], amd_gpu.UNKNOWN)

    def test_notes_skips_non_amd_and_lists_amd_in_order(self):
        report = {"GPU": {
            "NVIDIA GeForce RTX 4090": {"Device ID": "10DE-2684"},
            "AMD Radeon RX 7900 XTX": gpu("744C"),
            "AMD Radeon RX 6800": gpu("73BF"),
        }}
        out = amd_gpu.notes(report)
        self.assertEqual(len(out), 2)
        self.assertIn("RX 7900 XTX", out[0])
        self.assertIn("RX 6800", out[1])


if __name__ == "__main__":
    unittest.main()
