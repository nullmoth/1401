"""Read-only Windows device and graphics capability stages for the owned hardware-capture worker.

The scan starts one bounded worker in p1401.hwcapture. Native stages run there only, with CPU/platform/PnP checkpoints
before optional display-driver calls. The EFI builder reads the scan-bound receipt and never invokes these APIs.

Measurements describe the loaded Windows driver and registry. They do not establish macOS driver qualification,
physical display mux or connector wiring, firmware-disabled devices, or RT/Tensor unit counts. Native queries submit no
command lists, queues or shaders. Every stage records measured, partial, or unavailable with its source and reason.

Privacy: hardware instance tails, friendly names, endpoint names, SSIDs and serials are not exported. Descriptions of
remote Bluetooth descendants are omitted. Address scrubbing preserves GUIDs, versions and technical location paths.
"""
import ctypes
from collections import Counter
import ipaddress
import json
import os
import re
import sys

MAX_NODES, MAX_IDS, MAX_LEN, MAX_ADAPTERS = 3000, 16, 200, 16
MAX_PATHS, MAX_MODES, QDC_RETRIES = 128, 256, 3
MAX_PROP_BYTES = 8192           # a registry string property larger than this is reported truncated, never over-read
STAGES = ("platform_role", "devices", "display_paths", "graphics")   # order run: safest first, DXGI/D3D12 last

KEEP_ENUMERATORS = {"PCI", "HDAUDIO", "INTELAUDIO", "ACPI", "HID", "USB", "USBSTOR", "SCSI", "NVME", "SD", "SDBUS", "BTH",
                    "BTHENUM", "BTHLEDEVICE", "BTHLE", "DISPLAY", "UEFI"}
BLUETOOTH = {"BTHENUM", "BTHLEDEVICE", "BTHLE"}
VIRTUAL_VENDORS = {0x1414: "Microsoft (Basic Render / Hyper-V)", 0x15AD: "VMware", 0x1AE0: "Google", 0x1234: "QEMU",
                   0x1AF4: "virtio", 0x1B36: "QEMU (Red Hat)", 0x80EE: "VirtualBox", 0x5853: "Xen"}
RT_TIERS = {0: "not supported by the loaded driver", 10: "1.0", 11: "1.1", 12: "1.2"}
OUTPUT_TECH = {-1: "other", 0: "VGA", 1: "S-Video", 2: "composite", 3: "component", 4: "DVI", 5: "HDMI", 6: "LVDS",
               8: "D-JPN", 9: "SDI", 10: "DisplayPort", 11: "embedded DisplayPort", 12: "UDI", 13: "embedded UDI",
               14: "SDTV dongle", 15: "Miracast", 16: "indirect (wired)", 17: "indirect (virtual)",
               18: "DisplayPort over USB tunnel", -2147483648: "internal"}
INTERNAL_TECH = {6, 11, 13, -2147483648}
PLATFORM_ROLES = {0: "unspecified", 1: "desktop", 2: "mobile", 3: "workstation", 4: "enterprise server", 5: "SOHO server",
                  6: "appliance PC", 7: "performance server", 8: "slate"}

# winerror.h / winnt.h / devpropdef.h / libloaderapi.h / cfgmgr32.h (copies and hashes in the evidence folder)
ERROR_INVALID_DATA, ERROR_INSUFFICIENT_BUFFER, ERROR_NO_MORE_ITEMS, ERROR_NOT_FOUND = 13, 122, 259, 1168
REG_SZ, REG_EXPAND_SZ, REG_MULTI_SZ, DEVPROP_TYPE_STRING = 1, 2, 7, 0x12
LOAD_LIBRARY_SEARCH_SYSTEM32, CR_SUCCESS = 0x800, 0

_MAC = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f])"
                  r"|(?<![0-9A-Fa-f&-])[0-9A-Fa-f]{12}(?![0-9A-Fa-f])")  # a GUID's last group (-xxxxxxxxxxxx}) is not a MAC
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6_CANDIDATE = re.compile(r"(?<![0-9A-Za-z:])[0-9A-Fa-f:]*:[0-9A-Fa-f:]*(?:%[0-9A-Za-z]+)?(?![0-9A-Za-z:])")


def measured(value, source):
    return {"status": "measured", "source": source, "value": value}


def partial(value, source, error):
    return {"status": "partial", "source": source, "value": value, "error": str(error)[:300]}


def unavailable(error, source):
    return {"status": "unavailable", "source": source, "error": str(error)[:300]}


def _ipv6(m):
    tok = m.group(0)
    try:
        ipaddress.IPv6Address(tok.split("%", 1)[0])
        return "[ipv6]"
    except ValueError:
        return tok


def scrub(s):
    """Last gate on every kept string: MAC, IPv4 and IPv6 addresses anywhere become markers; GUIDs stay."""
    if not isinstance(s, str):
        return s
    s = _MAC.sub("[mac]", s[:MAX_PROP_BYTES])
    s = _IPV6_CANDIDATE.sub(_ipv6, s)
    return _IPV4.sub("[ip]", s)[:MAX_LEN]


def driver_version(value):
    """Keep a numeric driver version without treating its dotted components as an address."""
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,10}(?:\.[0-9]{1,10}){1,7}", value):
        return value
    return scrub(value)


def instance_key(instance_id):
    """'USB\\VID_0781&PID_5581\\4C530001234567' -> ('USB', 'USB\\VID_0781&PID_5581'). The tail is dropped."""
    parts = (instance_id or "").split("\\")
    return parts[0].upper(), "\\".join(parts[:2])


def hdaudio_codec(hwid):
    """HDAUDIO\\FUNC_nn&VEN_vvvv&DEV_dddd&SUBSYS_ssssssss&REV_rrrr (Microsoft: identifiers for HDAUDIO devices)."""
    m = re.match(r"HDAUDIO\\FUNC_([0-9A-F]{2})&VEN_([0-9A-F]{4})&DEV_([0-9A-F]{4})(?:&SUBSYS_([0-9A-F]{8}))?(?:&REV_([0-9A-F]{4}))?", hwid or "", re.I)
    if not m:
        return None
    f = m.groups()
    return {"function_group": {"01": "audio", "02": "modem"}.get(f[0], f[0]), "vendor": f[1].upper(), "device": f[2].upper(),
            "subsystem": (f[3] or "").upper() or None, "revision": (f[4] or "").upper() or None}


def pci_ids(hwid):
    m = re.match(r"PCI\\VEN_([0-9A-F]{4})&DEV_([0-9A-F]{4})(?:&SUBSYS_([0-9A-F]{8}))?", hwid or "", re.I)
    return (m.group(1).upper(), m.group(2).upper(), (m.group(3) or "").upper() or None) if m else None


# pure builders (tested on fixtures)
_report_local_instances = {}  # volatile exact instance identity -> per-report node; never serialized


def build_device_map(raw):
    """raw: dicts from a SetupAPI walk. Returns {"nodes", "edges", "dropped"} with per-report IDs."""
    global _report_local_instances
    _report_local_instances = {}
    raw = list(raw)
    kept, dropped = [], {}
    for r in raw:
        enum, _ = instance_key(r.get("instance_id"))
        if enum in KEEP_ENUMERATORS:
            kept.append(r)
        else:
            dropped[enum or "?"] = dropped.get(enum or "?", 0) + 1
    if len(kept) > MAX_NODES:
        dropped["over node cap"] = len(kept) - MAX_NODES
        kept = kept[:MAX_NODES]
    ids, parent_of = {}, {}
    for i, r in enumerate(kept):
        ids.setdefault(r["instance_id"], "n%d" % i)
        parent_of[r["instance_id"]] = r.get("parent_instance_id")
    instance_counts = Counter(row["instance_id"] for row in kept)
    _report_local_instances = {key: value for key, value in ids.items() if instance_counts[key] == 1}
    raw_parent = {r.get("instance_id"): r.get("parent_instance_id") for r in raw}

    def under_bluetooth(inst):
        seen = 0
        while inst and seen < 64:
            if instance_key(inst)[0] in BLUETOOTH:
                return True
            inst, seen = raw_parent.get(inst), seen + 1
        return False

    nodes, edges = [], []
    for r in kept:
        enum, dev = instance_key(r["instance_id"])
        hw = [scrub(x) for x in (r.get("hardware_ids") or [])[:MAX_IDS]]
        bt = under_bluetooth(r["instance_id"])
        node = {"node": ids[r["instance_id"]], "enumerator": enum, "device_id": scrub(dev), "hardware_ids": hw,
                "compatible_ids": [scrub(x) for x in (r.get("compatible_ids") or [])[:MAX_IDS]],
                "class": scrub(r.get("class")), "location": scrub(r.get("location")),
                "location_paths": [scrub(x) for x in (r.get("location_paths") or [])[:4]],
                "description": None if bt else scrub(r.get("description")),
                "manufacturer": None if bt else scrub(r.get("manufacturer")),
                "driver": {"provider": scrub(r.get("driver_provider")), "version": driver_version(r.get("driver_version"))},
                "status": r.get("status"), "property_status": r.get("property_status") or {}}
        if bt:
            node["property_status"] = dict(node["property_status"], description="dropped: under a Bluetooth enumerator")
        if enum == "HDAUDIO" and hw:
            node["codec"] = hdaudio_codec(hw[0])
        nodes.append(node)
        parent = r.get("parent_instance_id")
        if parent:
            edges.append({"child": ids[r["instance_id"]], "parent": ids.get(parent) or "outside:" + (instance_key(parent)[0] or "?")})
    return {"nodes": nodes, "edges": edges, "dropped": dropped}


def build_graphics_map(adapters, paths, device_nodes=()):
    """adapters: DXGI descriptions + D3D12 probe; paths: active display paths (joined by adapter LUID only);
    device_nodes: the device map, for PCI candidates by vendor/device/subsystem (never by name)."""
    pci = {}
    for n in device_nodes or ():
        ids = pci_ids((n.get("hardware_ids") or [""])[0])
        if ids:
            pci.setdefault(ids, []).append(n["node"])
    out, by_luid = [], {}
    for i, a in enumerate(adapters):
        vid = a["vendor_id"]
        kind = ("software rasterizer (WARP)" if a.get("flags", 0) & 2 else
                "virtual adapter: " + VIRTUAL_VENDORS[vid] if vid in VIRTUAL_VENDORS else "hardware adapter")
        key = ("%04X" % vid, "%04X" % a["device_id"], "%08X" % a["subsys_id"])
        cands = pci.get(key, [])
        node = {"adapter": "a%d" % i, "kind": kind, "description": scrub(a.get("description")),
                "vendor_id": key[0], "device_id": key[1], "subsystem_id": key[2], "revision": a.get("revision"),
                "dedicated_video_memory": a.get("dedicated_video_memory"), "shared_system_memory": a.get("shared_system_memory"),
                "raytracing_tier": (measured(RT_TIERS.get(a["rt_tier"], "tier %d" % a["rt_tier"]), "D3D12 CheckFeatureSupport(OPTIONS5)")
                                    if a.get("rt_tier") is not None else
                                    unavailable(a.get("rt_error") or "not probed", "D3D12 CheckFeatureSupport(OPTIONS5)")),
                "raytracing_meaning": "what the loaded Windows driver exposes; not a hardware unit count and not macOS support",
                "pci_candidates": cands,
                "pci_match": "none" if not cands else ("unique by IDs" if len(cands) == 1 else "ambiguous: identical IDs on several PCI functions"),
                "displays": []}
        out.append(node)
        by_luid[tuple(a["luid"])] = node
    for p in paths:
        n = by_luid.get(tuple(p["source_luid"]))
        tech = p.get("output_technology")
        entry = {"target": "t%d" % p["target_index"], "output": OUTPUT_TECH.get(tech, "code %s" % tech),
                 "internal_panel": tech in INTERNAL_TECH, "target_available": p.get("target_available")}
        if n is not None:
            n["displays"].append(entry)
    sig = {}
    for n in out:
        sig.setdefault((n["vendor_id"], n["device_id"], n["subsystem_id"]), []).append(n["adapter"])
    for n in out:
        n["identical_adapters"] = [x for x in sig[(n["vendor_id"], n["device_id"], n["subsystem_id"])] if x != n["adapter"]]
    return out


# native layer: exact signatures, system-directory DLLs only
class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16), ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]


def guid(a, b, c, *d):
    return GUID(a, b, c, (ctypes.c_ubyte * 8)(*d))


class LUID(ctypes.Structure):
    _fields_ = [("LowPart", ctypes.c_uint32), ("HighPart", ctypes.c_int32)]


class DXGI_ADAPTER_DESC1(ctypes.Structure):
    _fields_ = [("Description", ctypes.c_uint16 * 128),   # WCHAR[128]: decoded explicitly, bounded at its first NUL
                ("VendorId", ctypes.c_uint32), ("DeviceId", ctypes.c_uint32), ("SubSysId", ctypes.c_uint32), ("Revision", ctypes.c_uint32),
                ("DedicatedVideoMemory", ctypes.c_size_t), ("DedicatedSystemMemory", ctypes.c_size_t),
                ("SharedSystemMemory", ctypes.c_size_t), ("AdapterLuid", LUID), ("Flags", ctypes.c_uint32)]


class D3D12_FEATURE_DATA_D3D12_OPTIONS5(ctypes.Structure):
    _fields_ = [("SRVOnlyTiledResourceTier3", ctypes.c_int32), ("RenderPassesTier", ctypes.c_int32), ("RaytracingTier", ctypes.c_int32)]


class DISPLAYCONFIG_PATH_SOURCE_INFO(ctypes.Structure):
    _fields_ = [("adapterId", LUID), ("id", ctypes.c_uint32), ("modeInfoIdx", ctypes.c_uint32), ("statusFlags", ctypes.c_uint32)]


class DISPLAYCONFIG_PATH_TARGET_INFO(ctypes.Structure):
    _fields_ = [("adapterId", LUID), ("id", ctypes.c_uint32), ("modeInfoIdx", ctypes.c_uint32), ("outputTechnology", ctypes.c_int32),
                ("rotation", ctypes.c_uint32), ("scaling", ctypes.c_uint32), ("refreshNum", ctypes.c_uint32), ("refreshDen", ctypes.c_uint32),
                ("scanLineOrdering", ctypes.c_uint32), ("targetAvailable", ctypes.c_int32), ("statusFlags", ctypes.c_uint32)]


class DISPLAYCONFIG_PATH_INFO(ctypes.Structure):
    _fields_ = [("sourceInfo", DISPLAYCONFIG_PATH_SOURCE_INFO), ("targetInfo", DISPLAYCONFIG_PATH_TARGET_INFO), ("flags", ctypes.c_uint32)]


class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint32), ("ClassGuid", GUID), ("DevInst", ctypes.c_uint32), ("Reserved", ctypes.c_size_t)]


class DEVPROPKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", ctypes.c_uint32)]


DISPLAYCONFIG_MODE_INFO_SIZE = 64
IID_IDXGIFactory1 = (0x770AAE78, 0xF26F, 0x4DBA, 0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87)
IID_ID3D12Device = (0x189819F1, 0x1DB6, 0x4B57, 0xBE, 0x54, 0x18, 0x21, 0x33, 0x9B, 0x85, 0xF7)
VT_RELEASE, VT_FACTORY1_ENUMADAPTERS1, VT_ADAPTER1_GETDESC1, VT_DEVICE_CHECKFEATURESUPPORT = 2, 12, 10, 13
D3D12_FEATURE_D3D12_OPTIONS5, D3D_FEATURE_LEVEL_11_0, DXGI_ERROR_NOT_FOUND = 27, 0xB000, 0x887A0002
QDC_ONLY_ACTIVE_PATHS, DIGCF_PRESENT, DIGCF_ALLCLASSES = 2, 0x2, 0x4
SPDRP = {"description": 0x0, "hardware_ids": 0x1, "compatible_ids": 0x2, "class": 0x7, "manufacturer": 0xB,
         "location": 0xD, "location_paths": 0x23}
MULTI = {"hardware_ids", "compatible_ids", "location_paths"}
DN_STARTED, DN_HAS_PROBLEM, MAX_DEVICE_ID_LEN = 0x8, 0x400, 200
DRIVER_FMTID = (0xA8B865DD, 0x2E3D, 0x4094, 0xAD, 0x97, 0xE5, 0x93, 0xA7, 0x0C, 0x75, 0xD6)  # devpkey.h
DEVPKEY_DRIVER_VERSION, DEVPKEY_DRIVER_PROVIDER = 3, 9

HRESULT, BOOL, DWORD, CONFIGRET, LONG = ctypes.c_int32, ctypes.c_int32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int32
P = ctypes.POINTER
FUNCTYPE = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
# every export used: (dll, name, restype, argtypes) - nothing is called through an unprototyped pointer
EXPORTS = [
    ("dxgi", "CreateDXGIFactory1", HRESULT, [P(GUID), P(ctypes.c_void_p)]),
    ("d3d12", "D3D12CreateDevice", HRESULT, [ctypes.c_void_p, ctypes.c_int32, P(GUID), P(ctypes.c_void_p)]),
    ("user32", "GetDisplayConfigBufferSizes", LONG, [ctypes.c_uint32, P(ctypes.c_uint32), P(ctypes.c_uint32)]),
    ("user32", "QueryDisplayConfig", LONG, [ctypes.c_uint32, P(ctypes.c_uint32), P(DISPLAYCONFIG_PATH_INFO), P(ctypes.c_uint32),
                                            ctypes.c_void_p, ctypes.c_void_p]),
    ("setupapi", "SetupDiGetClassDevsW", ctypes.c_void_p, [P(GUID), ctypes.c_wchar_p, ctypes.c_void_p, DWORD]),
    ("setupapi", "SetupDiEnumDeviceInfo", BOOL, [ctypes.c_void_p, DWORD, P(SP_DEVINFO_DATA)]),
    ("setupapi", "SetupDiGetDeviceRegistryPropertyW", BOOL, [ctypes.c_void_p, P(SP_DEVINFO_DATA), DWORD, P(DWORD), ctypes.c_void_p,
                                                             DWORD, P(DWORD)]),
    ("setupapi", "SetupDiGetDevicePropertyW", BOOL, [ctypes.c_void_p, P(SP_DEVINFO_DATA), P(DEVPROPKEY), P(DWORD), ctypes.c_void_p,
                                                     DWORD, P(DWORD), DWORD]),
    ("setupapi", "SetupDiDestroyDeviceInfoList", BOOL, [ctypes.c_void_p]),
    ("cfgmgr32", "CM_Get_Device_IDW", CONFIGRET, [DWORD, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32]),
    ("cfgmgr32", "CM_Get_Parent", CONFIGRET, [P(DWORD), DWORD, ctypes.c_uint32]),
    ("cfgmgr32", "CM_Get_DevNode_Status", CONFIGRET, [P(ctypes.c_uint32), P(ctypes.c_uint32), DWORD, ctypes.c_uint32]),
    ("powrprof", "PowerDeterminePlatformRoleEx", ctypes.c_int32, [ctypes.c_uint32]),
]
COM = {  # (vtable slot, restype, argtypes after `this`), slots read from dxgi.h / d3d12.h
    "Release": (VT_RELEASE, ctypes.c_uint32, []),
    "EnumAdapters1": (VT_FACTORY1_ENUMADAPTERS1, HRESULT, [ctypes.c_uint32, P(ctypes.c_void_p)]),
    "GetDesc1": (VT_ADAPTER1_GETDESC1, HRESULT, [P(DXGI_ADAPTER_DESC1)]),
    "CheckFeatureSupport": (VT_DEVICE_CHECKFEATURESUPPORT, HRESULT, [ctypes.c_int32, ctypes.c_void_p, ctypes.c_uint32]),
}


class Native:
    """Bound exports. Real use: system-directory DLLs with LOAD_LIBRARY_SEARCH_SYSTEM32 (their dependencies are searched
    there too). Tests pass {dll: path} for stand-in libraries and a last_error callable."""

    def __init__(self, paths=None, last_error=None, only=None):
        self.f, self.missing = {}, {}
        libs = {}
        for dll, name, res, args in EXPORTS:
            if only is not None and dll not in only:
                continue
            if dll not in libs:
                try:
                    if paths is not None:
                        libs[dll] = ctypes.CDLL(paths[dll])
                    else:
                        libs[dll] = ctypes.WinDLL(dll + ".dll", use_last_error=True, winmode=LOAD_LIBRARY_SEARCH_SYSTEM32)
                except (OSError, KeyError) as e:
                    libs[dll] = None
                    self.missing[dll] = f"{dll}.dll not loadable ({type(e).__name__})"
            lib = libs[dll]
            fn = getattr(lib, name, None) if lib is not None else None
            if fn is None:
                self.missing.setdefault(name, f"{name} not exported")
                continue
            fn.restype, fn.argtypes = res, args
            self.f[name] = fn
        self.last_error = last_error or (ctypes.get_last_error if hasattr(ctypes, "get_last_error") else (lambda: 0))

    def need(self, *names):
        gone = [self.missing.get(n) or self.missing.get(n.split("!")[0]) for n in names if n not in self.f]
        if gone:
            raise ObservationUnavailable("; ".join(x or "unavailable" for x in gone))

    @staticmethod
    def com(ptr, method):
        slot, res, args = COM[method]
        vtbl = ctypes.cast(ptr, P(P(ctypes.c_void_p)))[0]
        if not vtbl or not vtbl[slot]:
            raise ObservationUnavailable(f"{method}: null vtable entry")
        return FUNCTYPE(res, ctypes.c_void_p, *args)(vtbl[slot])

    def release(self, ptr):
        if ptr:
            self.com(ptr, "Release")(ptr)


def _hex(hr):
    return "0x%08X" % (hr & 0xFFFFFFFF)


def _wchars(arr):
    """WCHAR[] as stored (uint16 units), up to the first NUL, never past the array."""
    units = list(arr)
    n = units.index(0) if 0 in units else len(units)
    return b"".join(int(u).to_bytes(2, "little") for u in units[:n]).decode("utf-16-le", "replace")


def dxgi_adapters(nt):
    """(adapters, errors). An adapter is recorded only after EnumAdapters1 and GetDesc1 both succeed with a real
    interface pointer; a failure is an error entry, never an adapter with zero IDs."""
    nt.need("CreateDXGIFactory1")
    factory = ctypes.c_void_p()
    hr = nt.f["CreateDXGIFactory1"](ctypes.byref(guid(*IID_IDXGIFactory1)), ctypes.byref(factory))
    if hr != 0 or not factory.value:
        raise ObservationUnavailable(f"CreateDXGIFactory1 {_hex(hr)}" + ("" if factory.value else " (no factory)"))
    adapters, errors = [], []
    try:
        enum = nt.com(factory, "EnumAdapters1")
        for i in range(MAX_ADAPTERS + 1):
            if i == MAX_ADAPTERS:
                errors.append(f"stopped at the {MAX_ADAPTERS}-adapter cap")
                break
            ad = ctypes.c_void_p()
            hr = enum(factory, i, ctypes.byref(ad))
            if (hr & 0xFFFFFFFF) == DXGI_ERROR_NOT_FOUND:
                break
            if hr != 0 or not ad.value:
                errors.append(f"EnumAdapters1({i}) {_hex(hr)}" + ("" if ad.value else " (no adapter)"))
                nt.release(ad)
                if hr != 0:
                    break
                continue
            try:
                d = DXGI_ADAPTER_DESC1()
                hr = nt.com(ad, "GetDesc1")(ad, ctypes.byref(d))
                if hr != 0:
                    errors.append(f"GetDesc1(adapter {i}) {_hex(hr)}: adapter not recorded")
                    continue
                a = {"description": _wchars(d.Description), "vendor_id": d.VendorId, "device_id": d.DeviceId, "subsys_id": d.SubSysId,
                     "revision": d.Revision, "dedicated_video_memory": d.DedicatedVideoMemory,
                     "shared_system_memory": d.SharedSystemMemory, "luid": (d.AdapterLuid.HighPart, d.AdapterLuid.LowPart), "flags": d.Flags}
                if "D3D12CreateDevice" not in nt.f:
                    a["rt_error"] = nt.missing.get("d3d12") or nt.missing.get("D3D12CreateDevice") or "D3D12 unavailable"
                else:
                    dev = ctypes.c_void_p()
                    hr = nt.f["D3D12CreateDevice"](ad, D3D_FEATURE_LEVEL_11_0, ctypes.byref(guid(*IID_ID3D12Device)), ctypes.byref(dev))
                    if hr != 0 or not dev.value:
                        a["rt_error"] = f"D3D12CreateDevice {_hex(hr)}: the API is unavailable on this adapter/driver"
                        nt.release(dev)
                    else:
                        try:
                            o5 = D3D12_FEATURE_DATA_D3D12_OPTIONS5()
                            hr = nt.com(dev, "CheckFeatureSupport")(dev, D3D12_FEATURE_D3D12_OPTIONS5, ctypes.byref(o5), ctypes.sizeof(o5))
                            if hr == 0:
                                a["rt_tier"] = o5.RaytracingTier
                            else:
                                a["rt_error"] = f"CheckFeatureSupport {_hex(hr)}"
                        finally:
                            nt.release(dev)
                adapters.append(a)
            finally:
                nt.release(ad)
    finally:
        nt.release(factory)
    return adapters, errors


def display_paths(nt):
    """(paths, errors). Sizes are re-read and the query retried when the topology changes between the two calls."""
    nt.need("GetDisplayConfigBufferSizes", "QueryDisplayConfig")
    errors = []
    for attempt in range(QDC_RETRIES):
        np_, nm = ctypes.c_uint32(), ctypes.c_uint32()
        rc = nt.f["GetDisplayConfigBufferSizes"](QDC_ONLY_ACTIVE_PATHS, ctypes.byref(np_), ctypes.byref(nm))
        if rc != 0:
            raise ObservationUnavailable(f"GetDisplayConfigBufferSizes error {rc}")
        cap_p, cap_m = min(np_.value, MAX_PATHS), min(nm.value, MAX_MODES)
        if (np_.value, nm.value) != (cap_p, cap_m):
            errors.append(f"Windows reported {np_.value} paths / {nm.value} modes; capped at {MAX_PATHS}/{MAX_MODES}")
        paths = (DISPLAYCONFIG_PATH_INFO * max(cap_p, 1))()
        modes = ctypes.create_string_buffer(DISPLAYCONFIG_MODE_INFO_SIZE * max(cap_m, 1))
        got_p, got_m = ctypes.c_uint32(cap_p), ctypes.c_uint32(cap_m)
        rc = nt.f["QueryDisplayConfig"](QDC_ONLY_ACTIVE_PATHS, ctypes.byref(got_p), paths, ctypes.byref(got_m), modes, None)
        if rc == ERROR_INSUFFICIENT_BUFFER:
            errors.append(f"display topology changed during the query (attempt {attempt + 1})")
            continue
        if rc != 0:
            raise ObservationUnavailable(f"QueryDisplayConfig error {rc}")
        if got_p.value > cap_p:
            errors.append(f"QueryDisplayConfig returned {got_p.value} paths for a {cap_p}-path buffer; kept {cap_p}")
        n = min(got_p.value, cap_p)
        return [{"source_luid": (p.sourceInfo.adapterId.HighPart, p.sourceInfo.adapterId.LowPart), "target_index": i,
                 "output_technology": p.targetInfo.outputTechnology, "target_available": bool(p.targetInfo.targetAvailable)}
                for i, p in enumerate(paths[:n])], errors
    raise ObservationUnavailable("; ".join(errors) + f"; gave up after {QDC_RETRIES} attempts")


def _reg_property(nt, h, d, prop, multi):
    """(value, status). Two calls: the size, then exactly that many bytes. Only REG_SZ/REG_EXPAND_SZ/REG_MULTI_SZ are
    read; the bytes are decoded up to the reported size and never past the buffer."""
    t, need = DWORD(), DWORD()
    if nt.f["SetupDiGetDeviceRegistryPropertyW"](h, ctypes.byref(d), prop, ctypes.byref(t), None, 0, ctypes.byref(need)):
        return ([] if multi else None), "empty"
    err = nt.last_error()
    if err == ERROR_INVALID_DATA:
        return ([] if multi else None), "absent"
    if err != ERROR_INSUFFICIENT_BUFFER:
        return ([] if multi else None), f"error {err}"
    size = need.value
    if size > MAX_PROP_BYTES:
        return ([] if multi else None), f"too large ({size} bytes); not read"
    buf = ctypes.create_string_buffer(max(size, 2))
    if not nt.f["SetupDiGetDeviceRegistryPropertyW"](h, ctypes.byref(d), prop, ctypes.byref(t), buf, size, ctypes.byref(need)):
        return ([] if multi else None), f"error {nt.last_error()} on the second call"
    if t.value not in ((REG_MULTI_SZ,) if multi else (REG_SZ, REG_EXPAND_SZ)):
        return ([] if multi else None), f"unexpected registry type {t.value}"
    used = min(need.value, size)
    raw = buf.raw[:used - (used % 2)]
    text = raw.decode("utf-16-le", "replace")
    status = "ok" if used % 2 == 0 and text.endswith("\0") else "malformed (odd length or no terminator); kept what was there"
    parts = [x for x in text.split("\0") if x]
    return (parts if multi else (parts[0] if parts else None)), status


def _dev_property(nt, h, d, pid):
    key = DEVPROPKEY(guid(*DRIVER_FMTID), pid)
    t, need = DWORD(), DWORD()
    buf = ctypes.create_string_buffer(512)
    if not nt.f["SetupDiGetDevicePropertyW"](h, ctypes.byref(d), ctypes.byref(key), ctypes.byref(t), buf, 512, ctypes.byref(need), 0):
        err = nt.last_error()
        return None, "absent" if err == ERROR_NOT_FOUND else f"error {err}"
    if t.value != DEVPROP_TYPE_STRING:
        return None, f"unexpected property type {t.value:#x}"
    used = min(need.value, 512)
    return buf.raw[:used - (used % 2)].decode("utf-16-le", "replace").split("\0", 1)[0], "ok"


def _device_id(nt, inst):
    buf = ctypes.create_string_buffer(2 * (MAX_DEVICE_ID_LEN + 1))
    if nt.f["CM_Get_Device_IDW"](inst, buf, MAX_DEVICE_ID_LEN + 1, 0) != CR_SUCCESS:
        return None
    return buf.raw.decode("utf-16-le", "replace").split("\0", 1)[0]


def setupapi_devices(nt):
    """(devices, errors). The walk ends at ERROR_NO_MORE_ITEMS; any other stop is recorded as a partial walk."""
    nt.need("SetupDiGetClassDevsW", "SetupDiEnumDeviceInfo", "SetupDiGetDeviceRegistryPropertyW", "SetupDiGetDevicePropertyW",
            "SetupDiDestroyDeviceInfoList", "CM_Get_Device_IDW", "CM_Get_Parent", "CM_Get_DevNode_Status")
    h = nt.f["SetupDiGetClassDevsW"](None, None, None, DIGCF_PRESENT | DIGCF_ALLCLASSES)
    if h in (None, 0, ctypes.c_void_p(-1).value):
        raise ObservationUnavailable(f"SetupDiGetClassDevsW failed (error {nt.last_error()})")
    out, errors = [], []
    try:
        for i in range(MAX_NODES * 4 + 1):
            if i == MAX_NODES * 4:
                errors.append(f"stopped at {MAX_NODES * 4} device entries")
                break
            d = SP_DEVINFO_DATA()
            d.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
            if not nt.f["SetupDiEnumDeviceInfo"](h, i, ctypes.byref(d)):
                err = nt.last_error()
                if err != ERROR_NO_MORE_ITEMS:
                    errors.append(f"SetupDiEnumDeviceInfo({i}) error {err}: walk stopped early")
                break
            inst = _device_id(nt, d.DevInst)
            if not inst:
                errors.append(f"device {i}: no instance ID; not recorded")
                continue
            rec, pst = {"instance_id": inst}, {}
            for key, prop in SPDRP.items():
                rec[key], st = _reg_property(nt, h, d, prop, key in MULTI)
                if st not in ("ok", "empty"):
                    pst[key] = st
            for key, pid in (("driver_provider", DEVPKEY_DRIVER_PROVIDER), ("driver_version", DEVPKEY_DRIVER_VERSION)):
                rec[key], st = _dev_property(nt, h, d, pid)
                if st != "ok":
                    pst[key] = st
            st, pr, parent = ctypes.c_uint32(), ctypes.c_uint32(), DWORD()
            rec["status"] = ({"started": bool(st.value & DN_STARTED), "problem": pr.value if st.value & DN_HAS_PROBLEM else 0}
                             if nt.f["CM_Get_DevNode_Status"](ctypes.byref(st), ctypes.byref(pr), d.DevInst, 0) == CR_SUCCESS else None)
            rec["parent_instance_id"] = (_device_id(nt, parent.value)
                                         if nt.f["CM_Get_Parent"](ctypes.byref(parent), d.DevInst, 0) == CR_SUCCESS else None)
            rec["property_status"] = pst
            out.append(rec)
    finally:
        nt.f["SetupDiDestroyDeviceInfoList"](h)
    return out, errors


def platform_role(nt):
    nt.need("PowerDeterminePlatformRoleEx")
    v = nt.f["PowerDeterminePlatformRoleEx"](2)  # POWER_PLATFORM_ROLE_V2
    return PLATFORM_ROLES.get(v, "role %d" % v), []


# the worker and its contract
class ObservationUnavailable(OSError):
    """A controlled diagnostic reason; arbitrary exception text is never included in reports."""


def _stage(fn, src):
    try:
        value, errors = fn()
    except Exception as e:  # noqa: BLE001 - permission, missing API or driver: the reason is the record
        code = getattr(e, 'winerror', None) or getattr(e, 'errno', None)
        reason = str(e)[:300] if isinstance(e, ObservationUnavailable) else type(e).__name__
        if not isinstance(e, ObservationUnavailable) and isinstance(code, int): reason += " (error %d)" % code
        return unavailable(reason, src), None
    return (partial(value, src, "; ".join(errors)) if errors else measured(value, src)), value


def collect(backends, checkpoint=None):
    """Runs the stages with the given backends ({stage: callable returning (value, errors)}) and returns the record.
    Real native backends are only ever passed in by the worker (_worker_main); tests pass stand-ins."""
    global _report_local_instances
    _report_local_instances = {}
    out = {"stages_completed": []}

    def done(name, rec):
        out[name] = rec
        out["stages_completed"].append(name)
        if checkpoint:
            checkpoint(out)

    role_rec, _ = _stage(backends["platform_role"], "PowerDeterminePlatformRoleEx (firmware-declared ACPI profile)")
    done("platform_role", role_rec)
    dev_rec, devs = _stage(backends["devices"], "SetupAPI/CfgMgr32 present devices")
    if devs is not None:
        dev_rec["value"] = build_device_map(devs)
    done("devices", dev_rec)
    path_rec, paths = _stage(backends["display_paths"], "QueryDisplayConfig(QDC_ONLY_ACTIVE_PATHS)")
    done("display_paths", path_rec)
    if 'cpu_native' in backends:
        record, _ = _stage(backends['cpu_native'], 'nm_cpuinfo.exe documented read-only CPUID allow-list')
        done('cpu_native', record)
    g_rec, adapters = _stage(backends["graphics"], "DXGI EnumAdapters1 + D3D12 CheckFeatureSupport")
    if adapters is not None:
        nodes = (dev_rec.get("value") or {}).get("nodes") or []
        g_rec["value"] = build_graphics_map(adapters, paths or [], nodes)
    done("graphics", g_rec)
    from . import fwres
    for name in fwres.EXTRA_STAGES:
        if name in backends:
            record, _ = _stage(backends[name], fwres.EXTRA_SOURCES[name])
            done(name, record)
    return out


def native_backends(nt=None):
    # Delay loading optional graphics libraries until after cheaper device evidence has been checkpointed.
    return {"platform_role": lambda: platform_role(nt or Native(only={"powrprof"})),
            "devices": lambda: setupapi_devices(nt or Native(only={"setupapi", "cfgmgr32"})),
            "display_paths": lambda: display_paths(nt or Native(only={"user32"})),
            "graphics": lambda: dxgi_adapters(nt or Native(only={"dxgi", "d3d12"}))}
