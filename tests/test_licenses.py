"""Every download 1401 can make has a known licence, and the mirror hosts only what that licence allows (10-21)."""
import json
import os
import unittest

from p1401 import engine, licenses, mirror

BUILD = "https://github.com/dortania/build-repo/releases/download/"


class Licenses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine._load_engine()
        from Scripts.datasets import kext_data
        cls.kexts = kext_data.kexts
        with open(mirror.MANIFEST, encoding="utf-8") as fh:
            cls.manifest = json.load(fh)["entries"]

    def test_every_engine_kext_names_a_project_with_a_licence(self):
        missing = []
        for k in self.kexts:
            if k.github_repo:
                name = f"{k.github_repo['owner']}/{k.github_repo['repo']}"
                if not licenses.project(name)[1]:
                    missing.append(f"{k.name}: {name}")
            else:
                url = (k.download_info or {}).get("download_url") or (k.download_info or {}).get("url") or ""
                kind, name, _ = licenses.classify(url)
                if not (name and licenses.project(name)[1]):
                    missing.append(f"{k.name}: {url or 'no URL'}")
        self.assertEqual(missing, [], "add each to p1401/licenses.json with the licence read from the project")

    def test_a_new_project_must_be_permissive_or_copyleft(self):
        bad = [k for k, e in licenses.table()["projects"].items()
               if e["class"] not in licenses.ADMITTED and not e.get("grandfathered")]
        self.assertEqual(bad, [], "only grandfathered projects may be none, restricted or tool-payload")

    def test_the_shipped_manifest_hosts_nothing_its_licence_forbids(self):
        refused = {u: licenses.hostable(u)[1] for u in self.manifest if not licenses.hostable(u)[0]}
        self.assertEqual(refused, {}, "rerun tools/record_mirror.py; it leaves these out")

    def test_every_hosted_copyleft_binary_has_its_source_beside_it(self):
        alone = [u for u in self.manifest if (licenses.hostable(u)[2] or "") and licenses.hostable(u)[2] not in self.manifest]
        self.assertEqual(alone, [])

    def test_the_mirror_refuses_restricted_unlicensed_and_tool_payload_files(self):
        # the negative arm: each of these is in some 1401 release's manifest, and none may be served
        for url in ("https://nightly.link/ChefKissInc/NootRX/workflows/main/master/Artifacts.zip",
                    "https://github.com/blankmac/AlpsHID/releases/download/v1.2/AlpsHID1.2_release.zip",
                    BUILD + "ECEnabler-29dcde7/ECEnabler-1.0.6-RELEASE.zip",
                    "https://github.com/dortania/OpenCore-Legacy-Patcher/raw/main/payloads/Kexts/Wifi/IOSkywalkFamily-v1.2.0.zip",
                    "https://github.com/someone/unlisted/releases/download/v1/x.zip"):
            self.assertFalse(licenses.hostable(url)[0], url)

    def test_permissive_is_hosted_and_copyleft_names_its_exact_source(self):
        self.assertEqual(licenses.hostable(BUILD + "Lilu-0515f40/Lilu-1.7.3-RELEASE.zip"), (True, None, None))
        self.assertEqual(licenses.hostable(BUILD + "BrcmPatchRAM-6538902/BrcmPatchRAM-2.7.3-RELEASE.zip")[2],
                         "https://github.com/acidanthera/BrcmPatchRAM/archive/6538902.tar.gz")
        self.assertEqual(licenses.hostable("https://github.com/Mieze/IntelLucy/releases/download/v1.1.5/IntelLucy-V1.1.5.zip")[2],
                         "https://github.com/Mieze/IntelLucy/archive/refs/tags/v1.1.5.tar.gz")

    def test_an_old_manifest_cannot_bring_a_refused_file_back(self):
        import tempfile
        old = {"schema": mirror.SCHEMA, "entries": {
            "https://nightly.link/ChefKissInc/NootRX/workflows/main/master/Artifacts.zip": {"sha256": "a" * 64, "size": 10},
            BUILD + "Lilu-0515f40/Lilu-1.7.3-RELEASE.zip": {"sha256": "b" * 64, "size": 10}}}
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "mirror.json")
            with open(path, "w") as fh:
                json.dump(old, fh)
            try:
                got = mirror.entries(path)
                self.assertEqual(sorted(got), [BUILD + "Lilu-0515f40/Lilu-1.7.3-RELEASE.zip"])
                self.assertIn("not ours to host", mirror.problem())
            finally:
                mirror._state["entries"] = None          # the next caller reads the shipped manifest again


if __name__ == "__main__":
    unittest.main()
