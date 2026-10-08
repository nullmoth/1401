"""Hardened devicemap arms (private). Run from a p1401 tree with FAKE_WIN=<path to libfake_win.dylib>:
    python3 -m unittest tests.test_devicemap_native
The stand-in library exports the same C signatures as the Windows DLLs and fake COM objects with the dxgi.h/d3d12.h
vtable slots, so the real bound exports and COM calls run. Nothing here runs Windows code."""
import ctypes, json, os, subprocess, sys, tempfile, textwrap, unittest
from p1401 import devicemap as dm
from pathlib import Path
from unittest.mock import patch

LIB = os.environ.get("FAKE_WIN", "")
DLLS = ("dxgi", "d3d12", "user32", "setupapi", "cfgmgr32", "powrprof")
PRIVATE = ["FixtureOwner", "D8A35C1B2E4F", "fe80::", "2600:1700", "4C530001234567", "5e6f"]


class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        suffix = ".dll" if sys.platform == "win32" else ".dylib"
        cls.path = LIB or str(Path(cls.temp.name) / ("fake-win" + suffix))
        if not Path(cls.path).exists():
            source = Path(__file__).parent / "native/fake_win.c"
            command = ["cl", "/nologo", "/LD", "/O2", str(source), "/link", "/OUT:" + cls.path] if sys.platform == "win32" else ["cc", "-shared", "-fPIC", "-o", cls.path, str(source)]
            subprocess.run(command, cwd=cls.temp.name, check=True, capture_output=True, timeout=30)
        cls.loads = []

    @classmethod
    def tearDownClass(cls):
        if sys.platform == "win32":
            from _ctypes import FreeLibrary
            for library in cls.loads:
                FreeLibrary(library._handle)
        cls.loads.clear()
        cls.temp.cleanup()
    def setUp(self):
        loader = ctypes.CDLL
        def own(path):
            library = loader(path)
            self.loads.append(library)
            return library
        self.library_patch = patch.object(dm.ctypes, "CDLL", side_effect=own)
        self.library_patch.start()
        self.addCleanup(self.library_patch.stop)
        self.lib = ctypes.CDLL(self.path)
        for k, v in (("fk_desc_fail_at", -1), ("fk_null_adapter_at", -1), ("fk_d3d12_fail_at", -1), ("fk_qdc_changes", 0),
                     ("fk_qdc_overreport", 0), ("fk_setup_err_at", -1), ("fk_prop_mode", 0), ("fk_role", 2), ("fk_factory_fail", 0),
                     ("fk_qdc_calls", 0), ("fk_max_prop_buf", 0), ("fk_destroyed", 0)):
            ctypes.c_int.in_dll(self.lib, k).value = v
        self.nt = dm.Native(paths={d: self.path for d in DLLS}, last_error=lambda: ctypes.c_int.in_dll(self.lib, "fk_last_error").value)

    def g(self, name):
        return ctypes.c_int.in_dll(self.lib, name).value

    def set(self, name, v):
        ctypes.c_int.in_dll(self.lib, name).value = v

    def run_all(self):
        return dm.collect(dm.native_backends(self.nt))

    # graphics
    def test_every_export_is_prototyped(self):
        for _, name, res, args in dm.EXPORTS:
            self.assertEqual((self.nt.f[name].restype, self.nt.f[name].argtypes), (res, args), name)

    def test_adapters_through_com_and_every_object_released(self):
        r = self.run_all()
        g = r["graphics"]
        self.assertEqual(g["status"], "measured")
        tiers = [a["raytracing_tier"]["value"] for a in g["value"]]
        self.assertEqual(tiers, ["1.1", "1.1", "not supported by the loaded driver"])
        self.assertEqual((g["value"][0]["identical_adapters"], g["value"][1]["identical_adapters"]), (["a1"], ["a0"]))
        self.assertEqual(g["value"][0]["description"], "NVIDIA GeForce RTX 3090")
        self.assertEqual(self.g("fk_live_objects"), 0)

    def test_getdesc_failure_records_no_adapter_and_marks_partial(self):
        self.set("fk_desc_fail_at", 1)
        g = self.run_all()["graphics"]
        self.assertEqual(g["status"], "partial"); self.assertIn("GetDesc1(adapter 1)", g["error"])
        self.assertEqual(len(g["value"]), 2)
        self.assertTrue(all(a["vendor_id"] != "0000" and a["device_id"] != "0000" for a in g["value"]))
        self.assertEqual(self.g("fk_live_objects"), 0)

    def test_success_with_null_adapter_is_not_an_adapter(self):
        self.set("fk_null_adapter_at", 0)
        g = self.run_all()["graphics"]
        self.assertEqual(g["status"], "partial"); self.assertIn("no adapter", g["error"])
        self.assertEqual([a["device_id"] for a in g["value"]], ["2204", "4680"])

    def test_d3d12_failure_is_api_unavailable_not_absent_hardware(self):
        self.set("fk_d3d12_fail_at", 2)
        g = self.run_all()["graphics"]
        rt = g["value"][2]["raytracing_tier"]
        self.assertEqual(rt["status"], "unavailable"); self.assertIn("0x887A0004", rt["error"])
        self.assertEqual(g["status"], "measured")
        self.assertEqual(self.g("fk_live_objects"), 0)

    def test_factory_failure_is_unavailable_and_never_counted(self):
        self.set("fk_factory_fail", 1)
        r = self.run_all()
        self.assertEqual(r["graphics"]["status"], "unavailable"); self.assertNotIn("value", r["graphics"])
        self.assertNotIn(r["graphics"]["status"], ("measured", "partial"))

    def test_identical_gpus_on_two_pci_functions_are_ambiguous(self):
        g = self.run_all()["graphics"]["value"]
        self.assertEqual(len(g[0]["pci_candidates"]), 2)
        self.assertTrue(g[0]["pci_match"].startswith("ambiguous"))
        self.assertEqual(g[2]["pci_match"], "none")

    # display paths
    def test_topology_change_is_retried_and_reported(self):
        self.set("fk_qdc_changes", 2)
        r = self.run_all()
        p = r["display_paths"]
        self.assertEqual(p["status"], "partial"); self.assertEqual(len(p["value"]), 2); self.assertEqual(self.g("fk_qdc_calls"), 3)
        out = {a["adapter"]: [d["output"] for d in a["displays"]] for a in r["graphics"]["value"]}
        self.assertEqual(out, {"a0": [], "a1": ["HDMI"], "a2": ["internal"]})

    def test_endless_topology_change_gives_up(self):
        self.set("fk_qdc_changes", 99)
        p = self.run_all()["display_paths"]
        self.assertEqual(p["status"], "unavailable"); self.assertIn("gave up", p["error"]); self.assertEqual(self.g("fk_qdc_calls"), dm.QDC_RETRIES)

    def test_overreported_count_never_reads_past_the_buffer(self):
        self.set("fk_qdc_overreport", 1)
        p = self.run_all()["display_paths"]
        self.assertEqual(p["status"], "partial"); self.assertEqual(len(p["value"]), 2); self.assertIn("returned 9 paths", p["error"])

    # devices
    def test_walk_error_is_partial_with_what_was_seen(self):
        self.set("fk_setup_err_at", 3)
        d = self.run_all()["devices"]
        self.assertEqual(d["status"], "partial"); self.assertIn("error 5", d["error"])
        self.assertEqual(len(d["value"]["nodes"]), 3); self.assertEqual(self.g("fk_destroyed"), 1)

    def test_property_replies(self):
        for mode, want in ((1, "malformed"), (2, "too large"), (3, "unexpected registry type")):
            with self.subTest(mode=mode):
                self.set("fk_prop_mode", mode)
                n0 = self.run_all()["devices"]["value"]["nodes"][0]
                self.assertIn(want, n0["property_status"].get("description", ""))
        self.assertLessEqual(self.g("fk_max_prop_buf"), dm.MAX_PROP_BYTES)
        self.set("fk_prop_mode", 0)
        n = self.run_all()["devices"]["value"]["nodes"]
        self.assertEqual(n[0]["property_status"].get("manufacturer"), "absent")
        self.assertEqual(n[2]["property_status"].get("driver_version"), "absent")
        self.assertEqual(n[0]["driver"]["version"], "31.0.15.5222")

    def test_problem_code_and_codec(self):
        n = self.run_all()["devices"]["value"]["nodes"]
        self.assertEqual(n[1]["status"], {"started": False, "problem": 43})
        self.assertEqual(n[2]["codec"]["device"], "0897")

    def test_privacy_on_the_full_record(self):
        s = json.dumps(self.run_all())
        for p in PRIVATE:
            self.assertNotIn(p, s)
        self.assertIn("{00001124-0000-1000-8000-00805F9B34FB}", s)
        self.assertIn("31.0.15.5222", s)


class Scrub(unittest.TestCase):
    def test_addresses_go_identifiers_stay(self):
        for s in ("fe80::1c2b:3cff:fe4d:5e6f%12", "2600:1700:abcd:1234::5", "::1", "D8:A3:5C:1B:2E:4F", "192.168.1.44", "D8A35C1B2E4F"):
            self.assertNotIn(s.split("%")[0], dm.scrub("x " + s + " y"), s)
        for s in ("{0000110B-0000-1000-8000-00805F9B34FB}", "31.0.15.5222", "12:30:45", "PCIROOT(0)#PCI(0100)", "Port_#0003.Hub_#0001",
                  "HDAUDIO\\FUNC_01&VEN_10EC&DEV_0897&SUBSYS_14627D25&REV_1001"):
            self.assertEqual(dm.scrub(s), s, s)


class Collect(unittest.TestCase):
    """005's collect() arms, ported to the worker backends (the no-argument in-process collect() is gone by design)."""
    def stub(self, **over):
        b = {"platform_role": lambda: ("mobile", []), "devices": lambda: ([], []), "display_paths": lambda: ([], []),
             "graphics": lambda: ([], [])}
        b.update(over)
        return b

    def test_missing_permission_keeps_the_rest(self):
        def denied():
            raise PermissionError(5, "private failed path that must not leave the collector")
        r = dm.collect(self.stub(devices=denied))
        self.assertEqual(r["devices"]["status"], "unavailable"); self.assertIn("error 5", r["devices"]["error"])
        self.assertEqual(r["graphics"]["status"], "measured"); self.assertEqual(r["platform_role"]["value"], "mobile")

    def test_laptop_is_never_inferred_from_names_or_panels(self):
        def fail():
            raise OSError("powrprof unavailable")
        r = dm.collect(self.stub(platform_role=fail))
        self.assertEqual(r["platform_role"]["status"], "unavailable")
        self.assertNotIn("laptop", json.dumps(r).lower())

    def test_collect_needs_explicit_backends(self):
        with self.assertRaises(TypeError):
            dm.collect()

