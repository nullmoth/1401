"""fwres arms (private). Run from a p1401 tree with FAKE_DIR=<dir holding libfake_cm / libfake_nvml2 / libfake_nvml2_old>:
    python3 -m unittest tests.test_fwres
The stand-ins export the real C signatures (cfgmgr32.h / setupapi.h / nvml.h), so the bound calls run as written."""
import ctypes, json, os, unittest
import subprocess, sys, tempfile
from pathlib import Path
from unittest.mock import patch
from p1401 import devicemap as dm, fwres

class NativeFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        suffix = '.dll' if sys.platform == 'win32' else '.dylib'
        cls.paths = {}
        for name, source, older in [('cm', 'fake_cm.c', False), ('nvml', 'fake_nvml2.c', False), ('nvml_old', 'fake_nvml2.c', True)]:
            path = str(Path(cls.temp.name) / (name + suffix))
            source = str(Path(__file__).parent / 'native' / source)
            if sys.platform == 'win32':
                command = ['cl', '/nologo', '/LD', '/O2', *(['/DOLD'] if older else []), source, '/link', '/OUT:' + path]
            else:
                command = ['cc', '-shared', '-fPIC', *(['-DOLD'] if older else []), source, '-o', path]
            subprocess.run(command, cwd=cls.temp.name, check=True, capture_output=True, timeout=30)
            cls.paths[name] = path
        cls.loads = []
    @classmethod
    def tearDownClass(cls):
        if sys.platform == 'win32':
            from _ctypes import FreeLibrary
            for library in cls.loads: FreeLibrary(library._handle)
        cls.loads.clear(); cls.temp.cleanup()
    def setUp(self):
        loader = ctypes.CDLL
        def tracked(path):
            library = loader(path); self.loads.append(library); return library
        self.addCleanup(patch.stopall)
        patch.object(ctypes, 'CDLL', side_effect=tracked).start()


class Resources(NativeFixtures):
    def setUp(self):
        super().setUp()
        CM = self.paths['cm']
        self.lib = ctypes.CDLL(CM)
        for k in ("fk_walk_err_at", "fk_wow64_at", "fk_huge_at", "fk_short_at", "fk_next_err_at"):
            ctypes.c_int.in_dll(self.lib, k).value = -1
        for k in ("fk_live_handles", "fk_destroyed"):
            ctypes.c_int.in_dll(self.lib, k).value = 0
        self.b = fwres.Binder(fwres.RES_EXPORTS, paths={"setupapi": CM, "cfgmgr32": CM},
                              last_error=lambda: ctypes.c_int.in_dll(self.lib, "fk_last_error").value)

    def g(self, k):
        return ctypes.c_int.in_dll(self.lib, k).value

    def set(self, k, v):
        ctypes.c_int.in_dll(self.lib, k).value = v

    def test_allocated_windows_and_every_handle_freed(self):
        devs, errors = fwres.pci_resources(self.b)
        self.assertEqual(errors, [])
        self.assertEqual(self.g("fk_enumerator_ok"), 1)
        gpu, nic, bridge = devs
        self.assertEqual(gpu["device_id"], "PCI\\VEN_10DE&DEV_2204&SUBSYS_87AF1043&REV_A1")
        self.assertEqual(gpu["location"], "PCI bus 1, device 0, function 0")
        big = gpu["allocated"][0]
        self.assertEqual((big["type"], big["base"], big["length"]), ("memory_large", "0x6000000000", 32 << 30))
        irq = gpu["allocated"][2]
        self.assertEqual((irq["type"], irq["vector"], irq["group"], irq["flags"]), ("irq", 4294967262, 1, "0x3"))
        self.assertEqual([a["type"] for a in nic["allocated"]], ["io", "memory"])
        self.assertEqual(bridge["status"], "no allocated configuration")
        self.assertEqual((self.g("fk_live_handles"), self.g("fk_destroyed")), (0, 1))

    def test_wow64_is_named_not_hidden(self):
        self.set("fk_wow64_at", 0)
        devs, _ = fwres.pci_resources(self.b)
        self.assertIn("CR_CALL_NOT_IMPLEMENTED", devs[0]["status"]); self.assertEqual(devs[0]["allocated"], [])
        self.assertEqual(self.g("fk_live_handles"), 0)

    def test_oversized_and_short_descriptors(self):
        self.set("fk_huge_at", 0); self.set("fk_short_at", 1)
        devs, _ = fwres.pci_resources(self.b)
        self.assertTrue(all("over the 4096-byte cap" in a["error"] for a in devs[0]["allocated"]))
        self.assertTrue(all("shorter than its" in a["error"] for a in devs[1]["allocated"]))
        self.assertEqual(self.g("fk_live_handles"), 0)

    def test_descriptor_walk_error_frees_and_reports(self):
        self.set("fk_next_err_at", 0)
        devs, _ = fwres.pci_resources(self.b)
        self.assertEqual(devs[0]["status"], "CM_Get_Next_Res_Des CR 0x6"); self.assertEqual(len(devs[0]["allocated"]), 1)
        self.assertEqual(self.g("fk_live_handles"), 0)

    def test_device_walk_error_is_partial(self):
        self.set("fk_walk_err_at", 1)
        rec = dm.collect({"platform_role": lambda: ("desktop", []), "devices": lambda: ([], []), "display_paths": lambda: ([], []),
                          "graphics": lambda: ([], []), "pci_resources": lambda: fwres.pci_resources(self.b)})
        r = rec["pci_resources"]
        self.assertEqual(r["status"], "partial"); self.assertEqual(len(r["value"]), 1); self.assertIn("error 5", r["error"])

    def test_unexpected_parse_failure_frees_current_descriptor_and_configuration(self):
        with patch.object(fwres, 'parse_descriptor', side_effect=ValueError('fixture parser failure')):
            with self.assertRaises(ValueError): fwres.pci_resources(self.b)
        self.assertEqual((self.g('fk_live_handles'), self.g('fk_destroyed')), (0, 1))

    def test_packed_io_header_and_reversed_range(self):
        import struct
        exact = struct.pack('<IIQQI', 0, 0, 0x3000, 0x30ff, 1)
        self.assertEqual(len(exact), 28)
        self.assertEqual(fwres.parse_descriptor(2, exact)['length'], 256)
        malformed = struct.pack('<IIQQI', 0, 0, 0x3000, 0x2000, 1)
        self.assertIn('precedes', fwres.parse_descriptor(2, malformed)['error'])

    def test_malformed_resources_mark_device_and_overall_partial(self):
        self.set('fk_short_at', 0)
        value, errors = fwres.pci_resources(self.b)
        self.assertEqual(value[0]['observation_status'], 'partial')
        self.assertTrue(errors)
        self.assertEqual(self.g('fk_live_handles'), 0)

    def test_exact_function_join_keeps_identical_models_separate(self):
        one = r'PCI\VEN_10DE&DEV_2204&SUBSYS_87AF1043&REV_A1\4&1&0&0008'
        two = r'PCI\VEN_10DE&DEV_2204&SUBSYS_87AF1043&REV_A1\4&1&0&0009'
        dm.build_device_map([{'instance_id': one}, {'instance_id': two}])
        records, _ = fwres.pci_resources(self.b)
        self.assertEqual(records[0]['node'], 'n0')
        self.assertEqual(dm._report_local_instances[two], 'n1')
        self.assertNotIn('4&1&0&0008', json.dumps(records))
        dm.build_device_map([{'instance_id': two}])
        self.assertIsNone(fwres.pci_resources(self.b)[0][0]['node'])

    def test_no_bar_vram_or_rebar_claims(self):
        s = json.dumps(fwres.pci_resources(self.b)[0]).lower()
        for word in ("vram", "rebar", "resizable", "bar_size"):
            self.assertNotIn(word, s)


LENOVO = [{"CurrentSetting": "SecureBoot,Enable;[Optional:Disable,Enable]"}, {"CurrentSetting": "VirtualizationTechnology,Enable"},
          {"CurrentSetting": "Above 4G Memory Mapping,Enabled"}, {"CurrentSetting": "BootOrder,NVMe0:USBHDD:S4EWNX0R123456A"},
          {"CurrentSetting": "AssetTag,NM-ASSET-0042"}, {"CurrentSetting": "SupervisorPasswordState,Enabled"},
          {"CurrentSetting": "WakeOnLAN,Enable"}, {"CurrentSetting": "MACAddressPassThrough,D8:A3:5C:1B:2E:4F"},
          {"CurrentSetting": "CFGLock,Enabled"}, {"CurrentSetting": ""}, {"CurrentSetting": "noComma"}]
HP = [{"Name": "Configure Legacy Support and Secure Boot", "CurrentValue": "Legacy Support Disable and Secure Boot Enable"},
      {"Name": "Secure Boot Keys Protection", "CurrentValue": "Disable"}, {"Name": "DVMT Pre-Allocated", "CurrentValue": "64M"},
      {"Name": "Ownership Tag", "CurrentValue": "Fixture Owner property"}, {"Name": "Re-Size BAR Support", "CurrentValue": "Enable;rm -rf"}]
DELL = [{"AttributeName": "SataOperation", "CurrentValue": ["RAID"]}, {"AttributeName": "VtForDirectIo", "CurrentValue": ["Enabled"]},
        {"AttributeName": "AdminSetupLockout", "CurrentValue": ["Disabled"]}, {"AttributeName": "EmbNic1", "CurrentValue": ["Enabled"]}]
PRIVATE = ["S4EWNX0R123456A", "NM-ASSET-0042", "D8:A3:5C:1B:2E:4F", "Fixture Owner", "rm -rf"]


def query_for(present, fail=None):
    data = {"Lenovo_BiosSetting": LENOVO, "HP_BIOSEnumeration": HP, "DCIM_BIOSEnumeration": DELL}

    def q(ns, cls, props):
        if fail and cls in fail:
            return None, fail[cls]
        return (data[cls], None) if cls in present else (None, "provider not present")
    return q


class Bios(unittest.TestCase):
    def cats(self, value):
        return {(s["vendor"], s["vendor_field"]): (s["category"], s["value"]) for s in value["settings"]}

    def test_allow_list_only_with_vendor_field_names(self):
        v, errors = fwres.bios_settings(query_for({"Lenovo_BiosSetting", "HP_BIOSEnumeration", "DCIM_BIOSEnumeration"}))
        c = self.cats(v)
        self.assertEqual(errors, [])
        self.assertEqual(c[("Lenovo", "SecureBoot")], ("secure_boot", "Enable"))
        self.assertEqual(c[("Lenovo", "VirtualizationTechnology")], ("virtualization", "Enable"))
        self.assertEqual(c[("Lenovo", "Above 4G Memory Mapping")], ("above_4g_decoding", "Enabled"))
        self.assertEqual(c[("Lenovo", "CFGLock")], ("cfg_lock", "Enabled"))
        self.assertEqual(c[("HP", "DVMT Pre-Allocated")], ("dvmt", "64M"))
        self.assertEqual(c[("Dell", "SataOperation")], ("storage_mode", "RAID"))
        self.assertEqual(c[("Dell", "VtForDirectIo")], ("virtualization", "Enabled"))
        self.assertEqual(c[("HP", "Re-Size BAR Support")], ("resizable_bar", None))
        for dropped in (("Lenovo", "BootOrder"), ("Lenovo", "AssetTag"), ("Lenovo", "SupervisorPasswordState"), ("Lenovo", "WakeOnLAN"),
                        ("Lenovo", "MACAddressPassThrough"), ("HP", "Secure Boot Keys Protection"), ("HP", "Ownership Tag"),
                        ("Dell", "AdminSetupLockout"), ("Dell", "EmbNic1")):
            self.assertNotIn(dropped, c)
        self.assertEqual(v["providers"], {"Lenovo": "present", "HP": "present", "Dell": "present"})

    def test_private_values_never_serialize(self):
        v, _ = fwres.bios_settings(query_for({"Lenovo_BiosSetting", "HP_BIOSEnumeration", "DCIM_BIOSEnumeration"}))
        s = json.dumps(v)
        for p in PRIVATE:
            self.assertNotIn(p, s)

    def test_no_provider_is_unavailable_not_empty(self):
        rec = dm.collect({"platform_role": lambda: ("desktop", []), "devices": lambda: ([], []), "display_paths": lambda: ([], []),
                          "graphics": lambda: ([], []), "bios_settings": lambda: fwres.bios_settings(query_for(set()))})
        r = rec["bios_settings"]
        self.assertEqual(r["status"], "unavailable"); self.assertIn("not observable", r["error"]); self.assertNotIn("value", r)

    def test_access_denied_and_timeout_are_partial(self):
        q = query_for({"Lenovo_BiosSetting"}, fail={"HP_BIOSEnumeration": "access denied", "DCIM_BIOSEnumeration": "query did not finish in 15 s"})
        v, errors = fwres.bios_settings(q)
        self.assertEqual(sorted(errors), ["Dell: query did not finish in 15 s", "HP: access denied"])
        self.assertIn("secure_boot", {s["category"] for s in v["settings"]})

    def test_unreported_categories_are_unknown_not_off(self):
        v, _ = fwres.bios_settings(query_for({"DCIM_BIOSEnumeration"}))
        self.assertIn("above_4g_decoding", v["not_reported"]); self.assertIn("unknown, not off", v["meaning"])


class Nvidia(NativeFixtures):
    def run_lib(self, name):
        path = self.paths['nvml_old' if '_old' in name else 'nvml']
        lib = ctypes.CDLL(path)
        for k in ("uuid_calls", "init_calls", "shutdown_calls"):
            ctypes.c_int.in_dll(lib, k).value = 0
        v, errors = fwres.nvidia_detail(fwres.bind_nvml(lib))
        return v, errors, lib

    def test_fields_mig_and_no_unit_counts(self):
        v, errors, lib = self.run_lib("libfake_nvml2.dylib")
        self.assertEqual(errors, [])
        self.assertEqual((v["driver_version"]["value"], v["cuda_driver_version"]["value"]), ("581.42", "13.0"))
        a, b = v["devices"]
        self.assertEqual(a["architecture"]["value"], {"code": 7, "name": "Ampere"})
        self.assertEqual(a["mig_mode"]["value"]["current"], "enabled"); self.assertIn("not enumerated", a["mig_mode"]["value"]["note"])
        self.assertEqual(a["max_mig_devices"]["value"], 7)
        self.assertEqual((b["pcie_gen_current"]["value"], b["pcie_width_current"]["value"], b["pcie_gen_max"]["value"]), (3, 8, 4))
        self.assertEqual(b["virtualization_mode"]["status"], "unavailable"); self.assertIn("not supported", b["virtualization_mode"]["error"])
        self.assertEqual(b["vbios_version"]["value"], "94.02.42.00.A9")
        for d in v["devices"]:
            self.assertEqual((d["tensor_cores"]["status"], d["rt_cores"]["status"]), ("unavailable", "unavailable"))
        self.assertEqual(len(v["devices"]), 2)   # seven MIG partitions on device 0 are NOT separate devices here
        self.assertEqual(ctypes.c_int.in_dll(lib, "uuid_calls").value, 0)
        self.assertEqual(ctypes.c_int.in_dll(lib, "shutdown_calls").value, ctypes.c_int.in_dll(lib, "init_calls").value)
        self.assertNotIn("GPU-1234", json.dumps(v))

    def test_overcount_is_capped_and_unknown_mig_codes_are_preserved(self):
        lib = ctypes.CDLL(self.paths['nvml'])
        functions, missing = fwres.bind_nvml(lib)
        def count(pointer):
            ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32)).contents.value = 17
            return 0
        def handle(index, pointer):
            ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p)).contents.value = int(index) % 2 + 1
            return 0
        def mig(device, current, pending):
            ctypes.cast(current, ctypes.POINTER(ctypes.c_uint32)).contents.value = 2
            ctypes.cast(pending, ctypes.POINTER(ctypes.c_uint32)).contents.value = 4
            return 0
        functions.update(nvmlDeviceGetCount_v2=count, nvmlDeviceGetHandleByIndex_v2=handle, nvmlDeviceGetMigMode=mig)
        value, errors = fwres.nvidia_detail((functions, missing))
        self.assertEqual(len(value['devices']), 16)
        self.assertIn('limited to 16', ';'.join(errors))
        mode = value['devices'][0]['mig_mode']['value']
        self.assertEqual((mode['current_code'], mode['pending_code'], mode['current'], mode['pending']), (2, 4, 'code 2', 'code 4'))
        virtualization = value['devices'][0]['virtualization_mode']['value']
        self.assertEqual(virtualization, {'code': 0, 'name': 'none reported by this driver'})
        self.assertEqual(len({device['device_record'] for device in value['devices']}), 16)

    def test_older_driver_missing_exports_are_per_field(self):
        v, errors, _ = self.run_lib("libfake_nvml2_old.dylib")
        self.assertEqual(set(v["missing_exports"]), {"nvmlDeviceGetArchitecture", "nvmlDeviceGetMigMode", "nvmlDeviceGetMaxMigDeviceCount"})
        a = v["devices"][0]
        self.assertIn("not exported", a["architecture"]["error"]); self.assertIn("not exported", a["mig_mode"]["error"])
        self.assertEqual(a["vbios_version"]["status"], "measured")

    def test_no_nvml_is_unavailable(self):
        rec = dm.collect({"platform_role": lambda: ("desktop", []), "devices": lambda: ([], []), "display_paths": lambda: ([], []),
                          "graphics": lambda: ([], []), "nvidia_detail": fwres.nvidia_detail})
        if os.name != "nt":
            self.assertEqual(rec["nvidia_detail"]["status"], "unavailable")


class Scrub(unittest.TestCase):
    def test_versions_survive_real_addresses_do_not(self):
        for keep in ("94.02.42.00.A9", "31.0.15.5222", "10.0.19041.1"):
            validated = fwres._version(keep.encode()) if 'A9' in keep else dm.driver_version(keep)
            self.assertEqual(validated, keep, keep)
        for gone in ("192.168.1.44", "10.0.0.1", "fe80::1", "D8:A3:5C:1B:2E:4F"):
            self.assertNotIn(gone, dm.scrub("x " + gone + " y"), gone)


class Worker(unittest.TestCase):
    def test_seven_stages_in_order_with_checkpoints(self):
        seen = []
        stub = lambda v: (lambda: (v, []))
        rec = dm.collect({"platform_role": stub("desktop"), "devices": stub([]), "display_paths": stub([]), "graphics": stub([]),
                          "pci_resources": stub([]), "bios_settings": stub({"settings": []}), "nvidia_detail": stub({"devices": []})},
                         checkpoint=lambda o: seen.append(list(o["stages_completed"])))
        order = list(dm.STAGES) + list(fwres.EXTRA_STAGES)
        self.assertEqual(rec["stages_completed"], order)
        self.assertEqual([len(s) for s in seen], list(range(1, 8)))

    def test_partial_record_marks_unreached_extra_stages(self):
        from p1401 import hwcapture
        r = hwcapture._recover({'device_map': {'stages_completed': ['platform_role'], 'platform_role': dm.measured('desktop', 'fixture')}}, 'timed out')
        for stage in fwres.EXTRA_STAGES:
            self.assertEqual(r['device_map'][stage]['status'], 'unavailable')
            self.assertIn('timed out', r['device_map'][stage]['error'])



if __name__ == "__main__":
    unittest.main()

class Security(unittest.TestCase):
    def test_nvml_reuses_the_verified_loader_and_never_checks_then_reopens(self):
        from p1401 import hwcapture
        library = type('Empty', (), {})()
        with patch.object(hwcapture, 'open_vendor_library', return_value=(library, None)) as verified, patch.object(hwcapture, 'authenticode_ok', side_effect=AssertionError('unowned verification')), patch.object(ctypes, 'CDLL', side_effect=AssertionError('reopen')):
            bound, missing = fwres.open_nvml()
        verified.assert_called_once_with('nvml.dll')
        self.assertFalse(bound); self.assertTrue(missing)
    def test_uncontained_or_nonallowlisted_bios_query_does_not_start(self):
        from p1401 import job_guard
        with patch.object(job_guard, 'ready', return_value=False), patch.object(fwres.subprocess, 'Popen', side_effect=AssertionError('launch')):
            self.assertIn('containment', fwres.powershell_cim(*fwres.PROVIDERS[0][1:3], ['CurrentSetting'])[1])
            self.assertIn('allow-list', fwres.powershell_cim('untrusted', 'untrusted', ['untrusted'])[1])
    def test_arbitrary_exception_text_is_never_retained(self):
        observation, _ = dm._stage(lambda: (_ for _ in ()).throw(OSError('private-host C:/private-account')), 'fixture')
        self.assertEqual(observation['error'], 'OSError')
    def test_invalid_version_is_unavailable_without_the_raw_value(self):
        functions = {'version': lambda: 0}
        result = fwres._field(functions, 'version', lambda _: (0, b'private-host malformed version'), lambda value: fwres._version(value))
        self.assertEqual(result['status'], 'unavailable')
        self.assertNotIn('private-host', json.dumps(result))

    def test_field_specific_version_validation(self):
        self.assertEqual(fwres._version(b'1.2.3.4', numeric=True), '1.2.3.4')
        self.assertEqual(fwres._version(b'94.02.42.00.A9'), '94.02.42.00.A9')
        with self.assertRaises(ValueError): fwres._version(b'private-host version')

class CimBootstrap(unittest.TestCase):
    def test_bootstrap_failure_has_controlled_phase_and_numeric_metadata_only(self):
        from p1401 import job_guard
        payload={'status':'failed','phase':'utility_module','hresult':-2146233087,'mi_code':-1,'message':'private-host C:/private-account'}
        with patch.object(job_guard,'run_bounded',return_value=(json.dumps(payload).encode(),0,None)):
            rows,error=fwres._bounded_process([],{},1)
        self.assertIsNone(rows);self.assertIn('phase=utility_module',error);self.assertIn('hresult=-2146233087',error)
        self.assertNotIn('private',error)
    def test_script_covers_bootstrap_and_uses_a_single_module_separator(self):
        script=fwres._cim_script(r'root\WMI','Lenovo_BiosSetting',['CurrentSetting'])
        self.assertLess(script.index('try {'),script.index('Import-Module'))
        self.assertIn(r'CimCmdlets\Get-CimInstance',script)
        self.assertNotIn(r'CimCmdlets\\Get-CimInstance',script)
        self.assertNotIn('-ExecutionPolicy',script);self.assertNotIn('.Exception.Message',script)
    def test_provider_absence_is_distinct_from_bootstrap_failure(self):
        from p1401 import job_guard
        with patch.object(job_guard,'run_bounded',return_value=(b'{"status":"provider_absent","phase":"cim_query","hresult":-2147217394,"mi_code":3,"rows":[]}',0,None)):
            self.assertEqual(fwres._bounded_process([],{},1),(None,'provider not present'))
