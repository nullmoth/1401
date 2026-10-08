"""devicemap arms (private). Run from a p1401 tree: python3 -m unittest tests.test_devicemap. ABI arms need clang and
ABI_DIR=<dir holding abi_check.py>; they compile header layouts for x86_64-pc-windows-msvc."""
import json, os, shutil, subprocess, tempfile, unittest
from p1401 import devicemap as dm

NV = 0x10DE; AMD = 0x1002; INTEL = 0x8086
ADAPTERS = [
    {"description": "NVIDIA GeForce RTX 3090", "vendor_id": NV, "device_id": 0x2204, "subsys_id": 0x87AF1043, "revision": 161,
     "dedicated_video_memory": 25 << 30, "luid": (0, 0x1001), "flags": 0, "rt_tier": 11},
    {"description": "NVIDIA GeForce RTX 3090", "vendor_id": NV, "device_id": 0x2204, "subsys_id": 0x87AF1043, "revision": 161,
     "dedicated_video_memory": 25 << 30, "luid": (0, 0x2002), "flags": 0, "rt_tier": 11},
    {"description": "AMD Radeon RX 6800", "vendor_id": AMD, "device_id": 0x73BF, "subsys_id": 0x0E3A1002, "luid": (0, 0x3003), "flags": 0,
     "rt_error": "D3D12CreateDevice HRESULT 0x887A0004: the API is unavailable on this adapter/driver"},
    {"description": "Intel(R) UHD Graphics 770", "vendor_id": INTEL, "device_id": 0x4680, "subsys_id": 0x7D251462, "luid": (0, 0x4004), "flags": 0, "rt_tier": 0},
    {"description": "Microsoft Basic Render Driver", "vendor_id": 0x1414, "device_id": 0x008C, "subsys_id": 0, "luid": (0, 0x5005), "flags": 2},
    {"description": "Google virtual display", "vendor_id": 0x1AE0, "device_id": 0xA001, "subsys_id": 0x00011AE0, "luid": (0, 0x6006), "flags": 0}]
PATHS = [{"source_luid": (0, 0x4004), "target_index": 0, "output_technology": -2147483648, "target_available": True},
         {"source_luid": (0, 0x2002), "target_index": 1, "output_technology": 5, "target_available": True}]
SECRETS = ["4C530001234567", "D8A35C1B2E4F", "D8:A3:5C:1B:2E:4F", "192.168.1.44", "Fixture Owner Endpoint", "MyHomeWiFi"]
DEVICES = [
    {"instance_id": "PCI\\VEN_8086&DEV_7A4C&SUBSYS_7D251462&REV_11\\3&11583659&0&A8", "parent_instance_id": "ACPI_HAL\\PNP0C08\\0",
     "hardware_ids": ["PCI\\VEN_8086&DEV_7A4C&SUBSYS_7D251462&REV_11"], "class": "System", "location": "PCI bus 0, device 21, function 0",
     "location_paths": ["PCIROOT(0)#PCI(1500)", "ACPI(_SB_)#ACPI(PC00)#ACPI(I2C0)"], "description": "Intel Serial IO I2C Host Controller",
     "driver_provider": "Intel Corporation", "driver_version": "30.100.2221.20", "status": {"started": True, "problem": 0}},
    {"instance_id": "ACPI\\ELAN0001\\4&2c6c41d&0", "parent_instance_id": "PCI\\VEN_8086&DEV_7A4C&SUBSYS_7D251462&REV_11\\3&11583659&0&A8",
     "hardware_ids": ["ACPI\\VEN_ELAN&DEV_0001", "ACPI\\ELAN0001"], "compatible_ids": ["ACPI\\PNP0C50"], "class": "HIDClass",
     "location_paths": ["ACPI(_SB_)#ACPI(PC00)#ACPI(I2C0)#ACPI(TPD0)"], "description": "I2C HID Device", "status": {"started": True, "problem": 0}},
    {"instance_id": "HID\\ELAN0001&COL01\\5&3a1b2c&0&0000", "parent_instance_id": "ACPI\\ELAN0001\\4&2c6c41d&0",
     "hardware_ids": ["HID\\VEN_ELAN&DEV_0001&Col01"], "class": "Mouse", "description": "HID-compliant touch pad", "status": {"started": True, "problem": 0}},
    {"instance_id": "HDAUDIO\\FUNC_01&VEN_10EC&DEV_0287&SUBSYS_17AA3A4E&REV_1000\\4&1d3e5f&0&0001", "parent_instance_id": "PCI\\VEN_8086&DEV_51C8\\3&1&0&FB",
     "hardware_ids": ["HDAUDIO\\FUNC_01&VEN_10EC&DEV_0287&SUBSYS_17AA3A4E&REV_1000", "HDAUDIO\\FUNC_01&VEN_10EC&DEV_0287&SUBSYS_17AA3A4E"],
     "class": "MEDIA", "description": "Realtek(R) Audio", "driver_provider": "Realtek Semiconductor Corp.", "driver_version": "6.0.9549.1",
     "status": {"started": True, "problem": 0}},
    {"instance_id": "USB\\VID_0781&PID_5581\\4C530001234567", "parent_instance_id": "USB\\ROOT_HUB30\\4&abc&0&0",
     "hardware_ids": ["USB\\VID_0781&PID_5581&REV_0100"], "class": "USB", "location": "Port_#0003.Hub_#0001", "status": {"started": True, "problem": 0}},
    {"instance_id": "USB\\VID_0781&PID_5581\\4C530001234999", "parent_instance_id": "USB\\ROOT_HUB30\\4&abc&0&0",
     "hardware_ids": ["USB\\VID_0781&PID_5581&REV_0100"], "class": "USB", "location": "Port_#0004.Hub_#0001", "status": {"started": True, "problem": 0}},
    {"instance_id": "BTHENUM\\{0000111E-0000-1000-8000-00805F9B34FB}_VID&0001004C_PID&2002\\7&2A3B&0&D8A35C1B2E4F_C00000000",
     "parent_instance_id": "BTH\\MS_BTHBRB\\6&1", "hardware_ids": ["BTHENUM\\{0000111E-0000-1000-8000-00805F9B34FB}_VID&0001004C_PID&2002"],
     "class": "Bluetooth", "description": "Fixture Owner Endpoint", "location": "D8:A3:5C:1B:2E:4F at 192.168.1.44", "status": {"started": True, "problem": 0}},
    {"instance_id": "PCI\\VEN_10EC&DEV_8125&SUBSYS_7D251462&REV_05\\4&2&0&00E4", "hardware_ids": ["PCI\\VEN_10EC&DEV_8125&SUBSYS_7D251462&REV_05"],
     "class": "Net", "description": "Realtek Gaming 2.5GbE Family Controller", "status": {"started": False, "problem": 28}},
    {"instance_id": "SWD\\WPDBUSENUM\\_??_USBSTOR#DISK&VEN_SANDISK#4C530001234567#{53f56307}", "hardware_ids": ["SWD\\WPDBUSENUM\\MyHomeWiFi"], "class": "WPD"},
    {"instance_id": "ROOT\\NET\\0000", "hardware_ids": ["ROOT\\MyHomeWiFi"], "class": "Net"}]


class Graphics(unittest.TestCase):
    def setUp(self):
        self.g = dm.build_graphics_map(ADAPTERS, PATHS)

    def test_mixed_vendors_tiers_and_api_unavailability(self):
        t = {a["adapter"]: a["raytracing_tier"] for a in self.g}
        self.assertEqual(t["a0"]["value"], "1.1")
        self.assertEqual(t["a3"]["value"], "not supported by the loaded driver")
        self.assertEqual(t["a2"]["status"], "unavailable")
        self.assertIn("API is unavailable", t["a2"]["error"])
        self.assertNotIn("value", t["a2"])

    def test_identical_gpus_stay_distinct_and_routes_follow_luid(self):
        a0, a1 = self.g[0], self.g[1]
        self.assertEqual((a0["identical_adapters"], a1["identical_adapters"]), (["a1"], ["a0"]))
        self.assertEqual(a0["displays"], [])
        self.assertEqual([d["output"] for d in a1["displays"]], ["HDMI"])

    def test_internal_panel_is_an_os_path_fact_on_the_igpu(self):
        d = self.g[3]["displays"]
        self.assertEqual((d[0]["output"], d[0]["internal_panel"]), ("internal", True))

    def test_software_and_virtual_adapters_are_labelled(self):
        self.assertEqual(self.g[4]["kind"], "software rasterizer (WARP)")
        self.assertTrue(self.g[5]["kind"].startswith("virtual adapter: Google"))
        self.assertEqual(self.g[0]["kind"], "hardware adapter")


class Devices(unittest.TestCase):
    def setUp(self):
        self.m = dm.build_device_map(DEVICES)
        self.by = {n["device_id"]: n for n in self.m["nodes"]}

    def test_versions_are_preserved_only_in_the_driver_version_field(self):
        source = dict(DEVICES[0], driver_version="1.2.3.4", description="address 1.2.3.4")
        node = dm.build_device_map([source])["nodes"][0]
        self.assertEqual(node["driver"]["version"], "1.2.3.4")
        self.assertEqual(node["description"], "address [ip]")
        source["driver_version"] = "address 192.168.1.44"
        self.assertEqual(dm.build_device_map([source])["nodes"][0]["driver"]["version"], "address [ip]")

    def test_address_filtering_precedes_output_truncation(self):
        text = "x " * 96 + "2001:db8:1234:5678::abcd"
        self.assertNotIn("2001:db8", dm.scrub(text))
        self.assertLessEqual(len(dm.scrub(text)), dm.MAX_LEN)

    def test_planted_identifiers_never_serialize(self):
        s = json.dumps(self.m)
        for secret in SECRETS:
            self.assertNotIn(secret, s)

    def test_identical_usb_devices_are_two_nodes_with_their_own_ports(self):
        usb = [n for n in self.m["nodes"] if n["device_id"] == "USB\\VID_0781&PID_5581"]
        self.assertEqual(len(usb), 2)
        self.assertNotEqual(usb[0]["node"], usb[1]["node"])
        self.assertEqual({n["location"] for n in usb}, {"Port_#0003.Hub_#0001", "Port_#0004.Hub_#0001"})

    def test_touchpad_chain_and_codec(self):
        e = {x["child"]: x["parent"] for x in self.m["edges"]}
        i2c, tpd, hid = (self.by[k]["node"] for k in ("PCI\\VEN_8086&DEV_7A4C&SUBSYS_7D251462&REV_11", "ACPI\\ELAN0001", "HID\\ELAN0001&COL01"))
        self.assertEqual((e[hid], e[tpd]), (tpd, i2c))
        self.assertEqual(e[i2c], "outside:ACPI_HAL")
        c = self.by["HDAUDIO\\FUNC_01&VEN_10EC&DEV_0287&SUBSYS_17AA3A4E&REV_1000"]["codec"]
        self.assertEqual((c["function_group"], c["vendor"], c["device"], c["subsystem"]), ("audio", "10EC", "0287", "17AA3A4E"))

    def test_problem_status_driver_and_dropped_enumerators(self):
        self.assertEqual(self.by["PCI\\VEN_10EC&DEV_8125&SUBSYS_7D251462&REV_05"]["status"]["problem"], 28)
        self.assertEqual(self.by["HDAUDIO\\FUNC_01&VEN_10EC&DEV_0287&SUBSYS_17AA3A4E&REV_1000"]["driver"]["version"], "6.0.9549.1")
        self.assertEqual(self.m["dropped"], {"SWD": 1, "ROOT": 1})
        bt = [n for n in self.m["nodes"] if n["enumerator"] == "BTHENUM"][0]
        self.assertIsNone(bt["description"])
        self.assertIn("_VID&0001004C_PID&2002", bt["hardware_ids"][0])
        self.assertIn("{0000111E-0000-1000-8000-00805F9B34FB}", bt["hardware_ids"][0])  # service GUID stays whole

