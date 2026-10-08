"""Measured hardware facts for failed-build logs that the hardware report does not carry: CPU topology from Windows, and
per-GPU compute limits from NVIDIA's own driver libraries when they are already installed.

Every field is {"status": "measured" | "unavailable", "source": <API>, "value" | "error"}. Nothing is derived from
architecture tables: an SM count does not give Tensor or RT unit counts (GTX 16 and RTX 20 share compute capability 7.5
with different units), so those stay "unavailable" with the reason. A device the vendor library does not list keeps its
raw PCI identity from the hardware report. NVIDIA libraries are loaded only from the Windows system directory and only
after their Authenticode signature verifies; nothing is installed, and a missing library is a status, not an error.
Hardware UUIDs and serials are never read."""
import ctypes
import os
import struct
import re
import sys
import json
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

# PCI vendor IDs of virtual and emulated display adapters. A report naming one of these describes a virtual machine's
# adapter, never a physical GPU behind it.
VIRTUAL_VENDORS = {"1414": "Microsoft Hyper-V / Basic Render", "15AD": "VMware", "1AE0": "Google virtual GPU",
                   "1234": "QEMU standard VGA", "1AF4": "virtio GPU", "1B36": "QEMU (Red Hat)", "80EE": "VirtualBox",
                   "5853": "Xen"}
NOT_EXPOSED = "not reported by NVML or the CUDA driver API; not derived from architecture tables"


def measured(value, source):
    return {"status": "measured", "source": source, "value": value}


def unavailable(error, source):
    return {"status": "unavailable", "source": source, "error": str(error)[:200]}


# CPU topology: GetLogicalProcessorInformationEx (winnt.h layouts, Microsoft Learn)
RELATION_CORE, RELATION_NUMA, RELATION_CACHE, RELATION_PACKAGE, RELATION_GROUP, RELATION_DIE = 0, 1, 2, 3, 4, 5
CACHE_TYPES = {0: "unified", 1: "instruction", 2: "data", 3: "trace"}


def _masks(buf, off, count):
    """GROUP_AFFINITY[count] at off: KAFFINITY Mask (8 bytes on x64), WORD Group, WORD Reserved[3] = 16 bytes each."""
    out = []
    for i in range(count):
        mask, group = struct.unpack_from("<QH", buf, off + 16 * i)
        out.append((group, mask))
    return out


def _lps(masks):
    return sorted((g, b) for g, m in masks for b in range(64) if m >> b & 1)


def parse_topology(buf):
    """Parse a SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX buffer into packages, cores (SMT, efficiency class), caches, NUMA."""
    cores, packages, dies, caches, numa = [], [], [], [], []
    off = 0
    while off < len(buf):
        if off + 8 > len(buf):
            raise ValueError("truncated topology header")
        rel, size = struct.unpack_from("<II", buf, off)
        if size < 8 or off + size > len(buf):
            raise ValueError(f"record at {off} has size {size}")
        record = memoryview(buf)[off:off + size]
        def require(minimum):
            if size < minimum:
                raise ValueError("truncated topology record")
        def masks(start, count):
            require(start + 16 * count)
            if count < 1 or count > 1024:
                raise ValueError("invalid topology group count")
            return _masks(record, start, count)
        if rel in (RELATION_CORE, RELATION_PACKAGE, RELATION_DIE):
            require(32)
            flags, eff = buf[off + 8], buf[off + 9]
            gc = struct.unpack_from("<H", buf, off + 30)[0]
            lps = _lps(masks(32, gc))
            if rel == RELATION_CORE:
                cores.append({"smt": bool(flags & 1), "efficiency_class": eff, "logical": len(lps), "lps": lps})
            else:
                (packages if rel == RELATION_PACKAGE else dies).append({"logical": len(lps), "lps": lps})
        elif rel == RELATION_CACHE:
            require(40)
            level, assoc, line, size_b, ctype = struct.unpack_from("<BBHII", buf, off + 8)
            gc = struct.unpack_from("<H", buf, off + 38)[0]
            caches.append({"level": level, "type": CACHE_TYPES.get(ctype, "unknown"), "bytes": size_b, "line": line,
                           "associativity": "full" if assoc == 0xFF else assoc,
                           "shared_by": len(_lps(masks(40, max(gc, 1)))), "lps": _lps(masks(40, max(gc, 1)))})
        elif rel in (RELATION_NUMA, 6):
            require(32)
            node = struct.unpack_from("<I", buf, off + 8)[0]
            gc = struct.unpack_from("<H", buf, off + 30)[0]
            numa.append({"node": node, "relationship": rel, "logical": len(_lps(masks(32, max(gc, 1)))), "lps": _lps(masks(32, max(gc, 1)))})
        off += size
    classes = sorted({c["efficiency_class"] for c in cores})
    hybrid = len(classes) > 1
    lp_package = {lp: i for i, p in enumerate(packages) for lp in p["lps"]}
    out = {"packages": len(packages), "dies": len(dies), "cores": len(cores), "logical_processors": sum(c["logical"] for c in cores),
           "hybrid": hybrid, "numa_nodes": len({n["node"] for n in numa}),
           "core_map": cores, "package_map": packages, "die_map": dies, "cache_map": caches, "numa_map": numa,
           "logical_address_format": "[processor group, group-local logical processor index]",
           "core_classes": [{"efficiency_class": k, "cores": sum(1 for c in cores if c["efficiency_class"] == k),
                             "logical": sum(c["logical"] for c in cores if c["efficiency_class"] == k),
                             "smt_cores": sum(1 for c in cores if c["efficiency_class"] == k and c["smt"])} for k in classes],
           "caches": sorted({json_key(c): {k: v for k, v in c.items() if k != "lps"} for c in caches}.values(), key=lambda c: (c["level"], c["type"], c["bytes"])),
           "cores_per_package": [sum(1 for c in cores if c["lps"] and lp_package.get(c["lps"][0]) == i) for i in range(len(packages))]}
    if hybrid:
        out["note"] = ("Windows reports efficiency classes; a higher class is the higher-performance core. The P/E names are "
                       "not reported by this API.")
    return out


def json_key(c):
    return (c["level"], c["type"], c["bytes"], c["line"], c["shared_by"])


def cpu_topology(kernel32=None):
    source = "kernel32!GetLogicalProcessorInformationEx(RelationAll)"
    if kernel32 is None:
        if sys.platform != "win32":
            return unavailable("not Windows", source)
        kernel32 = _kernel32()
    try:
        kernel32.GetLogicalProcessorInformationEx.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        kernel32.GetLogicalProcessorInformationEx.restype = ctypes.c_int32
        n = ctypes.c_uint32(0)
        kernel32.GetLogicalProcessorInformationEx(0xFFFF, None, ctypes.byref(n))
        if not 8 <= n.value <= 8 * 1024 * 1024:
            return unavailable("topology buffer size unavailable or out of bounds", source)
        capacity = n.value
        buf = ctypes.create_string_buffer(capacity)
        if not kernel32.GetLogicalProcessorInformationEx(0xFFFF, buf, ctypes.byref(n)):
            return unavailable(f"call failed (error {ctypes.get_last_error()})", source)
        if n.value > capacity:
            return unavailable("topology buffer grew during collection", source)
        return measured(parse_topology(buf.raw[:n.value]), source)
    except Exception as e:  # noqa: BLE001 - the reason rides in the record
        return unavailable(f"{type(e).__name__}: {e}", source)


# NVIDIA: NVML + CUDA driver API (nvml.h API 12 / cuda.h 12.9 constants)
class NvmlPciInfo(ctypes.Structure):
    _fields_ = [("busIdLegacy", ctypes.c_char * 16), ("domain", ctypes.c_uint), ("bus", ctypes.c_uint),
                ("device", ctypes.c_uint), ("pciDeviceId", ctypes.c_uint), ("pciSubSystemId", ctypes.c_uint),
                ("busId", ctypes.c_char * 32)]


class NvmlMemory(ctypes.Structure):
    _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong), ("used", ctypes.c_ulonglong)]


class NvmlBar1(ctypes.Structure):
    _fields_ = [("bar1Total", ctypes.c_ulonglong), ("bar1Free", ctypes.c_ulonglong), ("bar1Used", ctypes.c_ulonglong)]


CU_ATTRS = {"max_threads_per_block": 1, "max_shared_memory_per_block": 8, "warp_size": 10, "max_registers_per_block": 12,
            "multiprocessor_count": 16, "integrated": 18, "pci_bus_id": 33, "pci_device_id": 34, "memory_bus_width": 37,
            "l2_cache_bytes": 38, "max_threads_per_multiprocessor": 39, "pci_domain_id": 50,
            "compute_capability_major": 75, "compute_capability_minor": 76, "max_shared_memory_per_multiprocessor": 81,
            "max_registers_per_multiprocessor": 82, "max_shared_memory_per_block_optin": 97, "max_blocks_per_multiprocessor": 106}
NVML_NOT_SUPPORTED = 3


# Windows ABI types use fixed-width DWORD/WORD, not platform-native unsigned long.
class GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]


class FileInfo(ctypes.Structure):
    _fields_ = [("cbStruct", ctypes.c_uint32), ("pcwszFilePath", ctypes.c_wchar_p), ("hFile", ctypes.c_void_p),
                ("pgKnownSubject", ctypes.c_void_p)]


class TrustData(ctypes.Structure):
    _fields_ = [("cbStruct", ctypes.c_uint32), ("pPolicyCallbackData", ctypes.c_void_p), ("pSIPClientData", ctypes.c_void_p),
                ("dwUIChoice", ctypes.c_uint32), ("fdwRevocationChecks", ctypes.c_uint32), ("dwUnionChoice", ctypes.c_uint32),
                ("pFile", ctypes.POINTER(FileInfo)), ("dwStateAction", ctypes.c_uint32), ("hWVTStateData", ctypes.c_void_p),
                ("pwszURLReference", ctypes.c_wchar_p), ("dwProvFlags", ctypes.c_uint32), ("dwUIContext", ctypes.c_uint32),
                ("pSignatureSettings", ctypes.c_void_p)]


def _kernel32():
    return ctypes.WinDLL("kernel32", use_last_error=True, winmode=0x800)


def system_library(name):
    """Only the two installed vendor DLLs in the OS system directory are candidates."""
    if sys.platform != "win32" or name not in ("nvml.dll", "nvcuda.dll"):
        return None
    k = _kernel32()
    k.GetSystemDirectoryW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
    k.GetSystemDirectoryW.restype = ctypes.c_uint32
    buf = ctypes.create_unicode_buffer(32768)
    n = k.GetSystemDirectoryW(buf, len(buf))
    if not 0 < n < len(buf):
        return None
    p = os.path.join(buf.value, name)
    return p if os.path.isfile(p) else None


def _canonical_windows_path(path):
    return os.path.normcase(os.path.normpath(path.removeprefix("\\\\?\\")))


@contextmanager
def _system_file(path):
    """Pin the file while verifying/loading; refuse reparse files and redirected final paths."""
    k = _kernel32()
    k.GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
    k.GetFileAttributesW.restype = ctypes.c_uint32
    k.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                             ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    k.CreateFileW.restype = ctypes.c_void_p
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    k.CloseHandle.restype = ctypes.c_int32
    k.GetFinalPathNameByHandleW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32]
    k.GetFinalPathNameByHandleW.restype = ctypes.c_uint32
    for item in (path, os.path.dirname(path)):
        attrs = k.GetFileAttributesW(item)
        if attrs == 0xFFFFFFFF or attrs & 0x400:  # FILE_ATTRIBUTE_REPARSE_POINT
            raise OSError("system library is missing or uses a reparse point")
    # GENERIC_READ, FILE_SHARE_READ only: replacement/writes cannot race the trust and load calls.
    h = k.CreateFileW(path, 0x80000000, 1, None, 3, 0x00200000, None)
    if h in (None, ctypes.c_void_p(-1).value):
        raise OSError("system library cannot be pinned for read-only verification")
    try:
        final = ctypes.create_unicode_buffer(32768)
        n = k.GetFinalPathNameByHandleW(h, final, len(final), 0)
        if not 0 < n < len(final) or _canonical_windows_path(final.value) != _canonical_windows_path(path):
            raise OSError("system library final path does not match its OS directory")
        yield h
    finally:
        k.CloseHandle(h)


def authenticode_status(path, handle=None, trust=None):
    """Offline Authenticode verification on the pinned file, with state cleanup on every result."""
    action = GUID(0x00AAC56B, 0xCD44, 0x11D0, (ctypes.c_ubyte * 8)(0x8C, 0xC2, 0x00, 0xC0, 0x4F, 0xC2, 0x95, 0xEE))
    fi = FileInfo(ctypes.sizeof(FileInfo), path, handle, None)
    d = TrustData(ctypes.sizeof(TrustData), None, None, 2, 0, 1, ctypes.pointer(fi), 1, None, None, 0x1000, 0, None)
    wt = trust or ctypes.WinDLL("wintrust", use_last_error=True, winmode=0x800)
    wt.WinVerifyTrust.argtypes = [ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(TrustData)]
    wt.WinVerifyTrust.restype = ctypes.c_int32
    try:
        return int(wt.WinVerifyTrust(None, ctypes.byref(action), ctypes.byref(d)))
    finally:
        d.dwStateAction = 2
        wt.WinVerifyTrust(None, ctypes.byref(action), ctypes.byref(d))


def authenticode_ok(path, handle=None, trust=None):
    return authenticode_status(path, handle=handle, trust=trust) == 0


def open_vendor_library(name):
    """No caller-supplied path. Verification and restricted system-only dependency loading are mandatory."""
    p = system_library(name)
    if not p:
        return None, f"{name} not present in the Windows system directory (not observed)"
    try:
        with _system_file(p) as h:
            if not authenticode_ok(p, h):
                return None, f"{name} signature did not verify; not loaded"
            dll = ctypes.WinDLL(p, use_last_error=True, winmode=0x800)
            k = _kernel32()
            k.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32]
            k.GetModuleFileNameW.restype = ctypes.c_uint32
            actual = ctypes.create_unicode_buffer(32768)
            n = k.GetModuleFileNameW(dll._handle, actual, len(actual))
            if not 0 < n < len(actual) or _canonical_windows_path(actual.value) != _canonical_windows_path(p):
                raise OSError("loaded module path does not match the verified system library")
            return dll, None
    except Exception as e:
        return None, f"{name} not loaded ({type(e).__name__})"


def _bind(lib, name, args, result=ctypes.c_int):
    fn = getattr(lib, name, None)
    if fn is not None:
        fn.argtypes, fn.restype = args, result
    return fn


def nvml_devices(lib):
    src = "nvml"
    _bind(lib, "nvmlInit_v2", [])
    _bind(lib, "nvmlShutdown", [])
    _bind(lib, "nvmlDeviceGetCount_v2", [ctypes.POINTER(ctypes.c_uint)])
    _bind(lib, "nvmlDeviceGetHandleByIndex_v2", [ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)])
    _bind(lib, "nvmlDeviceGetPciInfo_v3", [ctypes.c_void_p, ctypes.POINTER(NvmlPciInfo)])
    _bind(lib, "nvmlDeviceGetName", [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint])
    for name in ("nvmlDeviceGetNumGpuCores", "nvmlDeviceGetMaxPcieLinkGeneration", "nvmlDeviceGetMaxPcieLinkWidth"):
        _bind(lib, name, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)])
    _bind(lib, "nvmlDeviceGetMemoryInfo", [ctypes.c_void_p, ctypes.POINTER(NvmlMemory)])
    _bind(lib, "nvmlDeviceGetBAR1MemoryInfo", [ctypes.c_void_p, ctypes.POINTER(NvmlBar1)])
    if lib.nvmlInit_v2() != 0:
        raise RuntimeError("nvmlInit_v2 failed")
    try:
        n = ctypes.c_uint(0)
        if lib.nvmlDeviceGetCount_v2(ctypes.byref(n)) != 0 or n.value > 256:
            raise RuntimeError("NVML device count unavailable or out of bounds")
        out = []
        for i in range(n.value):
            h = ctypes.c_void_p()
            if lib.nvmlDeviceGetHandleByIndex_v2(i, ctypes.byref(h)) != 0:
                continue
            d = {}
            pci = NvmlPciInfo()
            rc = lib.nvmlDeviceGetPciInfo_v3(h, ctypes.byref(pci))
            if rc == 0:
                bus_id = pci.busId.decode(errors="replace")
                address = _parse_pci(bus_id)
                function = address[3] if address and address[:3] == (pci.domain, pci.bus, pci.device) else None
                d["pci"] = measured({"bus_id": bus_id, "function": function,
                                     "function_status": "measured" if function is not None else "unavailable", "domain": pci.domain, "bus": pci.bus,
                                     "device": pci.device, "device_id": "%04X-%04X" % (pci.pciDeviceId & 0xFFFF, pci.pciDeviceId >> 16),
                                     "subsystem_id": "%08X" % pci.pciSubSystemId}, src + ":nvmlDeviceGetPciInfo_v3")
            name = ctypes.create_string_buffer(96)
            if lib.nvmlDeviceGetName(h, name, 96) == 0:
                d["name"] = measured(name.value.decode(errors="replace"), src + ":nvmlDeviceGetName")
            for key, fn, ctype, conv in (("gpu_cores", "nvmlDeviceGetNumGpuCores", ctypes.c_uint, int),
                                         ("max_pcie_gen", "nvmlDeviceGetMaxPcieLinkGeneration", ctypes.c_uint, int),
                                         ("max_pcie_width", "nvmlDeviceGetMaxPcieLinkWidth", ctypes.c_uint, int)):
                v = ctype(0)
                f = getattr(lib, fn, None)
                rc = f(h, ctypes.byref(v)) if f else 13
                d[key] = measured(conv(v.value), f"{src}:{fn}") if rc == 0 else unavailable(
                    "not supported on this device" if rc == NVML_NOT_SUPPORTED else f"nvml error {rc}", f"{src}:{fn}")
            mem, bar = NvmlMemory(), NvmlBar1()
            rc = lib.nvmlDeviceGetMemoryInfo(h, ctypes.byref(mem))
            d["vram_bytes"] = measured(mem.total, src + ":nvmlDeviceGetMemoryInfo") if rc == 0 else unavailable(f"nvml error {rc}", src + ":nvmlDeviceGetMemoryInfo")
            rc = lib.nvmlDeviceGetBAR1MemoryInfo(h, ctypes.byref(bar))
            d["bar1_bytes"] = measured(bar.bar1Total, src + ":nvmlDeviceGetBAR1MemoryInfo") if rc == 0 else unavailable(f"nvml error {rc}", src + ":nvmlDeviceGetBAR1MemoryInfo")
            out.append(d)
        return out
    finally:
        lib.nvmlShutdown()


def cuda_devices(lib):
    src = "nvcuda"
    _bind(lib, "cuInit", [ctypes.c_uint])
    _bind(lib, "cuDeviceGetCount", [ctypes.POINTER(ctypes.c_int)])
    _bind(lib, "cuDeviceGet", [ctypes.POINTER(ctypes.c_int), ctypes.c_int])
    _bind(lib, "cuDeviceGetAttribute", [ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.c_int])
    pci_function = _bind(lib, "cuDeviceGetPCIBusId", [ctypes.c_char_p, ctypes.c_int, ctypes.c_int])
    if lib.cuInit(0) != 0:
        raise RuntimeError("cuInit failed")
    n = ctypes.c_int(0)
    if lib.cuDeviceGetCount(ctypes.byref(n)) != 0 or not 0 <= n.value <= 256:
        raise RuntimeError("CUDA device count unavailable or out of bounds")
    out = []
    for i in range(n.value):
        dev = ctypes.c_int()
        if lib.cuDeviceGet(ctypes.byref(dev), i) != 0:
            continue
        d = {}
        for key, attr in CU_ATTRS.items():
            v = ctypes.c_int(0)
            rc = lib.cuDeviceGetAttribute(ctypes.byref(v), attr, dev)
            d[key] = measured(v.value, f"{src}:cuDeviceGetAttribute({attr})") if rc == 0 else unavailable(f"CUresult {rc}", f"{src}:cuDeviceGetAttribute({attr})")
        bus_id = ctypes.create_string_buffer(32)
        rc = pci_function(bus_id, len(bus_id), dev) if pci_function else -1
        address = _parse_pci(bus_id.value.decode(errors="replace")) if rc == 0 else None
        if address:
            fields = ("pci_domain_id", "pci_bus_id", "pci_device_id")
            if any(d.get(k, {}).get("status") == "measured" and d[k]["value"] != address[i] for i, k in enumerate(fields)):
                address = None
        d["pci"] = measured(dict(zip(("domain", "bus", "device", "function"), address)), "nvcuda:cuDeviceGetPCIBusId") if address else unavailable("full PCI function identity unavailable or inconsistent; not joined by partial address", "nvcuda:cuDeviceGetPCIBusId")
        out.append(d)
    return out


def _parse_pci(value):
    match = re.fullmatch(r"([0-9a-fA-F]{4,8}):([0-9a-fA-F]{2}):([0-9a-fA-F]{2})\.([0-7])", value)
    if not match:
        return None
    values = tuple(int(v, 16) for v in match.groups())
    return values if values[2] <= 31 else None


def _pci_key(domain, bus, device, function):
    return "%04x:%02x:%02x.%x" % (domain, bus, device, function)


def nvidia_compute(nvml=None, cuda=None):
    """Join only complete PCI domain:bus:device.function identities. Ambiguous records stay separate."""
    res = {"nvml": None, "cuda": None, "devices": []}
    records = []
    for vendor, lib, filename, getter in (("nvml", nvml, "nvml.dll", nvml_devices),
                                         ("cuda", cuda, "nvcuda.dll", cuda_devices)):
        if lib is None:
            lib, res[vendor] = open_vendor_library(filename)
        if lib is None:
            continue
        try:
            for d in getter(lib):
                pci = (d.get("pci") or {}).get("value")
                address = None
                if pci and all(pci.get(k) is not None for k in ("domain", "bus", "device", "function")):
                    address = _pci_key(*(pci[k] for k in ("domain", "bus", "device", "function")))
                records.append((vendor, d, address))
            res[vendor] = "ok"
        except Exception as error:
            res[vendor] = type(error).__name__
    groups = {}
    for i, (vendor, data, address) in enumerate(records):
        groups.setdefault(address if address else f"unavailable:{i:04d}", []).append((vendor, data, address))
    for key, group in sorted(groups.items()):
        ambiguous = any(sum(v == vendor for v, _, _ in group) > 1 for vendor in ("nvml", "cuda"))
        views = [{vendor: data, "pci_address": address, "identity_status": "ambiguous duplicate PCI function"}
                 for vendor, data, address in group] if ambiguous else [
                    {**{vendor: data for vendor, data, _ in group}, "pci_address": group[0][2],
                     "identity_status": "complete PCI function" if group[0][2] else "unavailable full PCI function; not joined"}]
        for view in views:
            view["tensor_cores"] = unavailable(NOT_EXPOSED, "none")
            view["rt_cores"] = unavailable(NOT_EXPOSED, "none")
            res["devices"].append(view)
    return res


def gpu_inventory(report):
    """Every GPU in the hardware report with its raw identity and what it is: physical, virtual, or unidentified."""
    out = []
    for name, p in list(((report or {}).get("GPU") or {}).items())[:256]:
        if not isinstance(p, dict):
            continue
        def value(key):
            v = p.get(key)
            return v if isinstance(v, str) and len(v) <= 512 else None
        name = name if isinstance(name, str) and len(name) <= 512 else "unnamed adapter"
        dev = (value("Device ID") or "").upper()
        vendor = dev[:4] if re.fullmatch(r"[0-9A-F]{4}-[0-9A-F]{4}", dev) else ""
        kind = ("virtual adapter: " + VIRTUAL_VENDORS[vendor]) if vendor in VIRTUAL_VENDORS else \
               ("no usable PCI identity reported; not evidence of any physical GPU model" if not vendor else "PCI adapter; physical backing and driver qualification unverified")
        out.append({"name": name, "device_id": dev or None, "subsystem_id": value("Subsystem ID") or None,
                    "pci_path": value("PCI Path"), "acpi_path": value("ACPI Path"), "kind": kind,
                    "raytracing": unavailable("not queried: the hardware report has no D3D12 raytracing tier", "none")})
    return out


CAPTURE_TIMEOUT = 8
CAPTURE_MAX_BYTES = 256 * 1024


def _native_collect():
    out = {}
    for key, fn in (("cpu_topology", cpu_topology), ("nvidia", nvidia_compute)):
        try:
            out[key] = fn()
        except Exception as e:
            out[key] = unavailable(type(e).__name__, key)
    return out


def _bounded_native(command=None, timeout=CAPTURE_TIMEOUT):
    """Vendor calls stay in an owned process. A crash/hang/output overflow cannot freeze the EFI builder."""
    source = "isolated hardware capture"
    fail = lambda why: {"cpu_topology": unavailable(why, source), "nvidia": {"status": "unavailable", "error": why, "devices": []}}
    try:
        with tempfile.TemporaryDirectory(prefix="1401-capture-") as directory:
            output = Path(directory) / "capture.json"
            cmd = command or [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--collect-worker", str(output)]
            if command is not None:
                cmd = [*command, str(output)]
            with subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as child:
                try:
                    child.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                    return fail("capture timed out; raw scan retained")
                if child.returncode != 0:
                    return fail("capture process failed; raw scan retained")
            with output.open("rb") as f:
                payload = f.read(CAPTURE_MAX_BYTES + 1)
            if len(payload) > CAPTURE_MAX_BYTES:
                return fail("capture output exceeded its limit; raw scan retained")
            result = json.loads(payload)
            if not isinstance(result, dict) or set(result) != {"cpu_topology", "nvidia"}:
                return fail("capture output was invalid; raw scan retained")
            return result
    except Exception:
        return fail("capture unavailable; raw scan retained")


def collect(report):
    """Optional, bounded measurements. Never let collection failure change a build or its raw device evidence."""
    try:
        out = {"gpus": gpu_inventory(report)}
    except Exception:
        out = {"gpus": [], "inventory": unavailable("invalid report shape", "hardware report")}
    out.update(_bounded_native() if sys.platform == "win32" else _native_collect())
    return out


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--collect-worker":
        raise SystemExit(2)
    payload = json.dumps(_native_collect(), ensure_ascii=True).encode("utf-8")
    if len(payload) > CAPTURE_MAX_BYTES:
        raise SystemExit(3)
    with open(sys.argv[2], "xb") as output:
        output.write(payload)
