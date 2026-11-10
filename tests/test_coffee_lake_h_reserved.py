"""Seven panics on physical page 0x1000c8000 across Coffee Lake-H laptops (driver #328, #451): the page is reserved in the
generated EFI, for that platform only, and OpenCore's validator accepts the entry."""
import os, platform as plat, plistlib, subprocess, tempfile, unittest, zipfile
from p1401 import engine, policy, validate
from tests.ocvalidate_run import run_validator


def build(cpu, kind="Laptop", vendor="Intel"):
    t = tempfile.mkdtemp(); path = os.path.join(t, "config.plist")
    cfg = {"NVRAM": {"Add": {}, "Delete": {}}, "Kernel": {"Add": [], "Patch": [], "Quirks": {}}, "Booter": {"Quirks": {}, "MmioWhitelist": []},
           "Misc": {}, "ACPI": {"Add": []}, "UEFI": {"Drivers": [], "Quirks": {}, "ReservedMemory": []}, "PlatformInfo": {"Generic": {}}}
    with open(path, "wb") as f: plistlib.dump(cfg, f)
    res = engine.BuildResult(ok=True, out_dir=t, macos_version="24.6.0", hardware={
        "Motherboard": {"Name": "B", "Chipset": "", "Platform": kind}, "CPU": {"Manufacturer": vendor, "Processor Name": cpu, "Codename": ""}, "GPU": {}})
    ch = policy.apply(path, res, engine.Policy())
    with open(path, "rb") as f: return plistlib.load(f), [c["rule"] for c in ch]


class Reserved(unittest.TestCase):
    def test_coffee_lake_h_laptops_reserve_the_page(self):
        for n in ("Intel(R) Core(TM) i5-9300H CPU @ 2.40GHz", "Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz", "Intel(R) Core(TM) i7-9750HK"):
            cfg, rules = build(n)
            (e,) = cfg["UEFI"]["ReservedMemory"]
            self.assertTrue(e["Address"] <= 0x1000C8000 < e["Address"] + e["Size"] and e["Type"] == "Reserved" and e["Enabled"], n)
            self.assertIn("coffee-lake-h-reserved-page", rules)

    def test_other_machines_get_nothing(self):
        for n, kind, v in (("Intel(R) Core(TM) i7-9700K", "Desktop", "Intel"), ("Intel(R) Core(TM) i7-9750H", "Desktop", "Intel"),
                           ("Intel(R) Core(TM) i7-10750H", "Laptop", "Intel"), ("Intel(R) Core(TM) i7-8750H", "Laptop", "Intel"),
                           ("AMD Ryzen 7 5800H", "Laptop", "AMD")):
            self.assertEqual(build(n, kind, v)[0]["UEFI"]["ReservedMemory"], [], n)

    def test_opencore_validator_accepts_it(self):
        z = os.environ.get("OPENCORE_TEST_ZIP", os.path.join(validate.CACHE, "OpenCore-1.0.8-RELEASE.zip"))
        if not os.path.isfile(z): self.skipTest("OpenCore 1.0.8 archive missing")
        with zipfile.ZipFile(z) as a:
            sample = plistlib.loads(a.read("Docs/Sample.plist"))
            tool = a.read("Utilities/ocvalidate/" + {"Windows": "ocvalidate.exe", "Linux": "ocvalidate.linux"}.get(plat.system(), "ocvalidate"))
        sample["UEFI"]["ReservedMemory"] = build("Intel(R) Core(TM) i7-9750H")[0]["UEFI"]["ReservedMemory"]
        d = tempfile.mkdtemp()
        c = os.path.join(d, "c.plist"); open(c, "wb").write(plistlib.dumps(sample))
        r = run_validator(tool, c)
        self.assertEqual([l for l in (r.stdout + r.stderr).splitlines() if "ReservedMemory" in l], [])


if __name__ == "__main__":
    unittest.main()
