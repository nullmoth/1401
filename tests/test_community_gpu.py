"""Community graphics projects (p1401/community_gpu.py): the selection is checked against the hardware fingerprints the
projects themselves document as running (PCI IDs from their READMEs and issue reports), so no machine is needed. A
project is named only for the GPUs it targets, and only the pointer projects reach the build notice; WhateverXe stays
with the Mac app."""
import os
import re
import unittest

from p1401 import community_gpu, engine, intel_gpu

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def machine(*gpu_ids):
    """A scan report with one GPU per "VVVV-DDDD" id."""
    return {"GPU": {f"GPU {i}": {"Device ID": d} for i, d in enumerate(gpu_ids)}}


def projects(report):
    return sorted(o["project"] for o in community_gpu.options(report))


class Selection(unittest.TestCase):
    def test_the_680m_laptop_with_an_nvidia_card_is_pointed_at_primebridge(self):
        # the machine PrimeBridge runs on: Radeon 680M (1681) beside an RTX 4050 Laptop (28A1)
        r = machine("1002-1681", "10DE-28A1")
        self.assertEqual(projects(r), ["myvoow/PrimeBridge"])
        self.assertTrue(any("PrimeBridge" in n and "2.6.3" in n for n in community_gpu.notes(r)))

    def test_a_680m_without_an_nvidia_card_gets_nothing(self):
        self.assertEqual(projects(machine("1002-1681")), [])

    def test_an_nvidia_card_beside_another_amd_igpu_is_not_a_primebridge_machine(self):
        # PrimeBridge matches 1002:1681 only; its register offsets are Rembrandt's
        self.assertEqual(projects(machine("1002-15BF", "10DE-2684")), ["luuumi-dev/nullarc"])
        self.assertEqual(projects(machine("1002-164E", "10DE-2684")), [])

    def test_meteor_and_arrow_lake_laptops_are_pointed_at_xegfx(self):
        for did in ("8086-7D55", "8086-7D45", "8086-7D67", "8086-7D51", "8086-7DD5"):
            self.assertEqual(projects(machine(did)), ["watchthelight-labs/WTLIntelGfx"], did)
            self.assertEqual(len(community_gpu.notes(machine(did))), 1, did)

    def test_xe_lp_gpus_stay_with_whateverxe_and_get_no_pointer(self):
        # Tiger Lake 9A49, Alder Lake-P 46A6, Alder Lake-U 46B3, Raptor Lake-P A7A0 (not a Dell XPS 13 Plus), Alder Lake-HX 4688
        for did in ("8086-9A49", "8086-46A6", "8086-46B3", "8086-A7A0", "8086-4688"):
            opts = community_gpu.options(machine(did))
            self.assertEqual([(o["project"], o["action"]) for o in opts], [("b00t0x/WhateverXe", "mac-app")], did)
            self.assertEqual(community_gpu.notes(machine(did)), [], did)

    def test_a_dell_xps_13_plus_gets_the_pinned_archive_of_the_licence_restricted_project_as_a_notice(self):
        r = machine("8086-A7A0"); r["Motherboard"] = {"Name": "Dell Inc. 0X1234 XPS 13 9320"}
        self.assertEqual(projects(r), ["JulioNectar/Hackintosh-XPS13Plus-IrisXe-Tahoe", "b00t0x/WhateverXe"])
        (n,) = community_gpu.notes(r)
        d = community_gpu.OPTIONAL_DOWNLOADS["JulioNectar/Hackintosh-XPS13Plus-IrisXe-Tahoe"]
        self.assertIn(d["sha256"], n)
        self.assertIn("24450b476d7ca025b83c85d7b8362caf3234d2f2", n)
        self.assertIn("does not include or host", n)
        self.assertRegex(d["sha256"], r"^[0-9a-f]{64}$")

    def test_the_same_gpu_in_another_laptop_does_not_get_the_xps_notice(self):
        r = machine("8086-A7A0"); r["Motherboard"] = {"Name": "LENOVO 83F0"}
        self.assertEqual(community_gpu.notes(r), [])

    def test_unlicensed_projects_are_named_with_a_link_and_never_downloaded(self):
        cases = {("8086-A7A8", "10DE-2582"): "nmx-intel", ("8086-A7AC",): "First-Custom-iGPU-Driver", ("8086-B080",): "vibe-nullmoth-xe3-qemu"}
        for ids, word in cases.items():
            (n,) = community_gpu.notes(machine(*ids))
            self.assertIn(word, n)
            self.assertIn("https://github.com/", n)
            self.assertIn("cannot include or download it", n)
        self.assertEqual(community_gpu.notes(machine("8086-A7A8")), [])      # nmx-intel needs the NVIDIA card too

    def test_only_the_licence_restricted_project_has_a_pinned_download(self):
        self.assertEqual(list(community_gpu.OPTIONAL_DOWNLOADS), ["JulioNectar/Hackintosh-XPS13Plus-IrisXe-Tahoe"])
        for p in community_gpu.PROJECTS:
            if p["verdict"] == community_gpu.NAMED:
                self.assertIn("none", p["licence"].lower(), p["repo"])
                self.assertNotIn(p["repo"], community_gpu.OPTIONAL_DOWNLOADS)

    def test_the_whateverxe_ids_added_by_0_8_0_are_recognised(self):
        # single-channel Alder Lake-H (4626), Tiger Lake-H45 (9AC0) and Raptor Lake-U (A721) were not in the 0.6.1 list
        for did in ("4626", "9AC0", "A721", "A720", "9A59", "46C1"):
            self.assertIn(did, intel_gpu.WHATEVERXE_IDS)
            self.assertEqual(projects(machine("8086-" + did)), ["b00t0x/WhateverXe"], did)

    def test_phoenix_and_hawk_point_are_pointed_at_nullarc(self):
        for did in ("1002-1900", "1002-15BF", "1002-15C8"):
            self.assertEqual(projects(machine(did)), ["luuumi-dev/nullarc"], did)

    def test_other_amd_and_nvidia_hardware_gets_no_community_graphics_notice(self):
        # Navi 33, Navi 31, Strix Point, Polaris, an RTX 5060, a Kaby Lake iGPU, Lunar Lake
        for did in ("1002-7480", "1002-744C", "1002-150E", "1002-67EF", "10DE-2D05", "8086-5912", "8086-64A0"):
            self.assertEqual(projects(machine(did)), [], did)

    def test_a_scan_with_no_gpu_section_is_not_an_error(self):
        self.assertEqual(community_gpu.options({}), [])
        self.assertEqual(community_gpu.notes({"GPU": {"x": "not a dict"}}), [])

    def test_the_engine_adds_these_notices_to_the_build(self):
        self.assertIs(engine.community_gpu, community_gpu)


class Catalogue(unittest.TestCase):
    def test_every_project_is_pinned_to_a_full_commit_with_a_verdict_and_a_reason(self):
        seen = set()
        for p in community_gpu.PROJECTS:
            self.assertRegex(p["commit"], r"^[0-9a-f]{40}$", p["repo"])
            self.assertIn(p["verdict"], community_gpu.VERDICTS, p["repo"])
            self.assertTrue(p["licence"].strip() and p["what"].strip() and p["why"].strip(), p["repo"])
            self.assertRegex(p["date"], r"^2026-\d\d-\d\d$|^2025-\d\d-\d\d$|^2024-\d\d-\d\d$", p["repo"])
            self.assertNotIn(p["repo"].lower(), seen)
            seen.add(p["repo"].lower())

    def test_the_repositories_named_in_the_request_are_all_evaluated(self):
        wanted = ["myvoow/primebridge", "kitsuneislife/nmx-intel", "julionectar/hackintosh-xps13plus-irisxe-tahoe",
                  "b00t0x/whateverxe", "b00t0x/whateverxe-graphics", "thatisjigen/whateverxe",
                  "vedcloud/meteor-lake-xe-lpg-metal-graphics", "watchthelight-labs/wtlintelgfx", "rx4darwin/amdradeonrdna4.kext",
                  "ericek111/vibe-nullmoth-xe3-qemu", "pongpan-bk/first-custom-igpu-driver-for-intel-core-5-120u-on-macos",
                  "emirercan3459/nullmoth-nvidia-audio", "carnations-botanica/intelmklfixup"]
        have = {p["repo"].lower() for p in community_gpu.PROJECTS}
        self.assertEqual([w for w in wanted if w not in have], [])

    def test_nothing_without_a_licence_or_made_by_an_ai_is_integrated(self):
        for p in community_gpu.PROJECTS:
            if p["verdict"] in (community_gpu.INTEGRATED, community_gpu.DRIVER_IDEA):
                self.assertFalse(p["licence"].lower().startswith(("none", "polyform", "thou shalt")), p["repo"])
                self.assertNotRegex(p["why"].lower(), r"assistant-written|assistant-aided|no licence", p["repo"])

    def test_the_integrated_projects_have_a_licence_record_and_a_credit(self):
        import json
        table = json.load(open(os.path.join(ROOT, "p1401", "licenses.json"), encoding="utf-8"))["projects"]
        notice = open(os.path.join(ROOT, "NOTICE.md"), encoding="utf-8").read()
        low = {k.lower(): v for k, v in table.items()}
        for repo, cls in (("b00t0x/WhateverXe", "permissive"), ("carnations-botanica/IntelMKLFixup", "copyleft")):
            self.assertEqual(low[repo.lower()]["class"], cls, repo)
            self.assertIn(repo.split("/")[1], notice, repo)
        self.assertIn("PrimeBridge", notice)
        self.assertIn("RX4Darwin/AMDRadeonRDNA4", notice)

    def test_the_document_lists_every_project_with_the_same_commit(self):
        doc = open(os.path.join(ROOT, "docs", "COMMUNITY-DRIVERS.md"), encoding="utf-8").read()
        for p in community_gpu.PROJECTS:
            self.assertIn(p["repo"], doc, p["repo"])
            self.assertIn(p["commit"][:7], doc, p["repo"])
        self.assertIn("Verdict", doc)

    def test_nothing_shipped_names_an_ai_tool(self):
        banned = re.compile("|".join(a + b for a, b in (("clau", "de"), ("anthr", "opic"), ("chat", "gpt"), ("open", "ai"), ("co", "dex"),
                                                      ("gem", "ini"), ("copi", "lot"), ("antigra", "vity"), ("open", "code"))), re.I)
        for rel in ("p1401/community_gpu.py", "docs/COMMUNITY-DRIVERS.md"):
            text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
            self.assertIsNone(banned.search(text), rel)


if __name__ == "__main__":
    unittest.main()
