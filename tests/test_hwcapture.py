"""hwcapture arms (private). Run from a p1401 tree with FAKES=<dir of libfake_*.dylib>: python3 -m unittest tests.test_hwcapture.
The fakes are C libraries with NVIDIA's exported signatures, so the real ctypes bindings run."""
import ctypes, json, os, struct, unittest, sys, tempfile, subprocess, shutil
from pathlib import Path
from unittest.mock import patch
from p1401 import hwcapture as hc

FAKES = os.environ.get("FAKES", "")


def rec(rel, payload):
    return struct.pack("<II", rel, 8 + len(payload)) + payload


def core(eff, smt, lps):
    mask = sum(1 << b for b in lps)
    return rec(0, bytes([1 if smt else 0, eff]) + bytes(20) + struct.pack("<H", 1) + struct.pack("<QH6x", mask, 0))


def pkg(lps):
    return rec(3, bytes(22) + struct.pack("<H", 1) + struct.pack("<QH6x", sum(1 << b for b in lps), 0))


def cache(level, ctype, size, lps):
    return rec(2, struct.pack("<BBHII", level, 12, 64, size, ctype) + bytes(18) + struct.pack("<H", 1) +
               struct.pack("<QH6x", sum(1 << b for b in lps), 0))


def numa(node, lps):
    return rec(1, struct.pack("<I", node) + bytes(18) + struct.pack("<H", 1) + struct.pack("<QH6x", sum(1 << b for b in lps), 0))


class Capture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.fakes = Path(os.environ.get("FAKES", cls.temp.name))
        suffix = ".dll" if sys.platform == "win32" else ".dylib"
        for vendor in ("nvml", "cuda"):
            dest = cls.fakes / ("libfake_" + vendor + suffix)
            if not dest.exists():
                source = Path(__file__).parent / "native" / ("fake_" + vendor + ".c")
                if sys.platform == "win32":
                    command = ["cl", "/nologo", "/LD", "/O2", str(source), "/link", "/OUT:" + str(dest)]
                else:
                    command = ["cc", "-shared", "-fPIC", "-o", str(dest), str(source)]
                subprocess.run(command, cwd=cls.temp.name, check=True, capture_output=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
    def libs(self):
        suffix = ".dll" if sys.platform == "win32" else ".dylib"
        loader = ctypes.WinDLL if sys.platform == "win32" else ctypes.CDLL
        n = loader(str(self.fakes / ("libfake_nvml" + suffix))); c = loader(str(self.fakes / ("libfake_cuda" + suffix)))
        return n, c

    def test_absent_driver_is_a_status_and_raw_pci_stays(self):
        with patch.object(hc, "system_library", return_value=None):
            res = hc.nvidia_compute()
        self.assertEqual(res["devices"], [])
        self.assertIn("not present", res["nvml"]); self.assertIn("not present", res["cuda"])
        inv = hc.gpu_inventory({"GPU": {"NVIDIA GeForce RTX 3050": {"Device ID": "10DE-2507", "Subsystem ID": "380217AA",
                                                                    "PCI Path": "PciRoot(0x0)/Pci(0x1,0x0)/Pci(0x0,0x0)"}}})
        self.assertEqual((inv[0]["device_id"], inv[0]["subsystem_id"]), ("10DE-2507", "380217AA"))
        self.assertEqual(inv[0]["kind"], "PCI adapter; physical backing and driver qualification unverified")

    def test_virtual_and_unidentified_adapters_are_labelled(self):
        inv = {g["name"]: g["kind"] for g in hc.gpu_inventory({"GPU": {
            "Google virtual": {"Device ID": "1AE0-A001"}, "Microsoft Basic Display Adapter": {"Device ID": ""}}})}
        self.assertTrue(inv["Google virtual"].startswith("virtual adapter"))
        self.assertIn("not evidence of any physical GPU", inv["Microsoft Basic Display Adapter"])

    def test_vendor_libraries_join_by_pci_not_name(self):
        n, c = self.libs()
        res = hc.nvidia_compute(nvml=n, cuda=c)
        self.assertEqual([d["pci_address"] for d in res["devices"]], ["0000:01:00", "0000:05:00", "0000:2a:00"])
        a, b = res["devices"][0], res["devices"][2]
        self.assertEqual(a["nvml"]["name"]["value"], b["nvml"]["name"]["value"])  # same model, two entries
        self.assertEqual(a["cuda"]["multiprocessor_count"]["value"], 82)
        self.assertEqual(a["nvml"]["pci"]["value"]["subsystem_id"], "87AF1043")
        self.assertEqual(a["nvml"]["pci"]["value"]["device_id"], "10DE-2204")
        self.assertEqual(b["nvml"]["bar1_bytes"]["value"], 268435456)

    def test_same_compute_capability_never_yields_unit_counts(self):
        n, c = self.libs()
        res = hc.nvidia_compute(nvml=n, cuda=c)
        g1660 = next(d for d in res["devices"] if d["pci_address"] == "0000:05:00")
        self.assertEqual((g1660["cuda"]["compute_capability_major"]["value"], g1660["cuda"]["compute_capability_minor"]["value"]), (7, 5))
        for d in res["devices"]:
            self.assertEqual(d["tensor_cores"]["status"], "unavailable"); self.assertEqual(d["rt_cores"]["status"], "unavailable")
        self.assertEqual(g1660["nvml"]["gpu_cores"]["status"], "unavailable")
        self.assertIn("not supported", g1660["nvml"]["gpu_cores"]["error"])

    def test_uuid_is_never_read(self):
        n, c = self.libs()
        hc.nvidia_compute(nvml=n, cuda=c)
        self.assertEqual(ctypes.c_int.in_dll(n, "uuid_calls").value, 0)
        self.assertNotIn("GPU-0000", json.dumps(hc.nvidia_compute(nvml=n, cuda=c)))

    def test_only_the_system_directory_is_ever_searched(self):
        self.assertIsNone(hc.system_library("nvml.dll") if os.name != "nt" else None)
        with patch.object(hc, "system_library", return_value=None):
            dll, err = hc.open_vendor_library("nvml.dll")
        self.assertIsNone(dll); self.assertIn("system directory", err)

    def test_hybrid_cpu_topology(self):
        buf = b"".join([pkg(range(8)), numa(0, range(8)), core(1, True, [0, 1]), core(1, True, [2, 3]),
                        core(0, False, [4]), core(0, False, [5]), core(0, False, [6]), core(0, False, [7]),
                        cache(2, 0, 1310720, [0, 1]), cache(2, 0, 2097152, [4, 5, 6, 7]), cache(3, 0, 12582912, range(8))])
        t = hc.parse_topology(buf)
        self.assertEqual((t["packages"], t["cores"], t["logical_processors"], t["numa_nodes"], t["hybrid"]), (1, 6, 8, 1, True))
        cls = {c["efficiency_class"]: c for c in t["core_classes"]}
        self.assertEqual((cls[1]["cores"], cls[1]["logical"], cls[1]["smt_cores"]), (2, 4, 2))
        self.assertEqual((cls[0]["cores"], cls[0]["logical"]), (4, 4))
        self.assertIn((3, 12582912, 8), {(c["level"], c["bytes"], c["shared_by"]) for c in t["caches"]})

    def test_topology_off_windows_is_unavailable_not_guessed(self):
        with patch.object(hc.sys, "platform", "linux"):
            r = hc.cpu_topology()
        self.assertEqual(r["status"], "unavailable"); self.assertNotIn("value", r)


if __name__ == "__main__":
    unittest.main()
