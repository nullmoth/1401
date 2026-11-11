"""Three more read-only stages for the device-map worker (p1401/devicemap.py), run after its own four:

  pci_resources   the memory / I/O / IRQ / DMA / bus-number windows Windows ALLOCATED to each present PCI function
                  (Configuration Manager: CM_Get_First_Log_Conf(ALLOC_LOG_CONF) -> CM_Get_Next_Res_Des ->
                  CM_Get_Res_Des_Data, every handle freed). These are the windows the OS assigned. They are not the
                  BAR registers, not VRAM size and not the Resizable BAR enable state, and nothing here reads MMIO.
  bios_settings   documented, already-installed vendor WMI providers only, queried read-only through PowerShell's
                  Get-CimInstance: Lenovo root\\WMI Lenovo_BiosSetting.CurrentSetting, HP root\\HP\\InstrumentedBIOS
                  HP_BIOSEnumeration.Name/CurrentValue, Dell root\\DCIM\\SYSMAN DCIM_BIOSEnumeration.AttributeName/
                  CurrentValue. Password, asset, boot-order and owner classes are never queried. Only settings on a
                  strict allow-list leave the worker, with the vendor's own field name.
  nvidia_detail   NVML fields the 004 capture lacks: architecture code, driver and CUDA driver versions, VBIOS version,
                  current PCIe link, compute mode, virtualization mode, MIG mode and the maximum MIG device count.
                  MIG partitions share their GPU's PCI address and are not enumerated; no UUID, serial, process,
                  license or display name is read. A missing export (older driver) or NOT_SUPPORTED is per field.

Each backend returns (value, errors) like devicemap's own stages, so the worker checkpoints it and the builder only
ever reads the saved record."""
import ctypes
import json
import os
import re
import subprocess
import sys
import base64
import threading
import time

from . import devicemap as dm

MAX_RES_DEVICES, MAX_RES_PER_DEVICE, MAX_RES_DATA = 512, 64, 4096
# Cold PowerShell startup is included in this limit; each query is also clipped to the shared 12-second worker deadline.
PS_TIMEOUT, MAX_BIOS_ROWS = 10, 2000

# cfgmgr32.h
ALLOC_LOG_CONF, RES_ALL = 0x2, 0x0
RES_TYPES = {1: "memory", 2: "io", 3: "dma", 4: "irq", 6: "bus_number", 7: "memory_large"}
CR_NO_MORE_LOG_CONF, CR_NO_MORE_RES_DES, CR_CALL_NOT_IMPLEMENTED = 0x0E, 0x0F, 0x34
DIGCF_PRESENT, DIGCF_ALLCLASSES = 0x2, 0x4


class MEM_DES(ctypes.Structure):
    _pack_ = 1  # cfgmgr32.h allocated-resource structures are under pshpack1.h
    _fields_ = [("Count", ctypes.c_uint32), ("Type", ctypes.c_uint32), ("Alloc_Base", ctypes.c_uint64), ("Alloc_End", ctypes.c_uint64),
                ("Flags", ctypes.c_uint32), ("Reserved", ctypes.c_uint32)]


MEM_LARGE_DES = MEM_DES  # same layout (Mem_Large_Des_s: MLD_Count, MLD_Type, MLD_Alloc_Base, MLD_Alloc_End, MLD_Flags, MLD_Reserved)


class IO_DES(ctypes.Structure):
    _pack_ = 1  # cfgmgr32.h allocated-resource structures are under pshpack1.h
    _fields_ = [("Count", ctypes.c_uint32), ("Type", ctypes.c_uint32), ("Alloc_Base", ctypes.c_uint64), ("Alloc_End", ctypes.c_uint64),
                ("DesFlags", ctypes.c_uint32)]


class IRQ_DES_64(ctypes.Structure):
    _pack_ = 1  # cfgmgr32.h allocated-resource structures are under pshpack1.h
    _fields_ = [("Count", ctypes.c_uint32), ("Type", ctypes.c_uint32), ("Flags", ctypes.c_uint32),   # USHORT Flags + USHORT Group
                ("Alloc_Num", ctypes.c_uint32), ("Affinity", ctypes.c_uint64)]                        # on NT_PROCESSOR_GROUPS builds


class DMA_DES(ctypes.Structure):
    _pack_ = 1  # cfgmgr32.h allocated-resource structures are under pshpack1.h
    _fields_ = [("Count", ctypes.c_uint32), ("Type", ctypes.c_uint32), ("Flags", ctypes.c_uint32), ("Alloc_Chan", ctypes.c_uint32)]


class BUSNUMBER_DES(ctypes.Structure):
    _pack_ = 1  # cfgmgr32.h allocated-resource structures are under pshpack1.h
    _fields_ = [("Count", ctypes.c_uint32), ("Type", ctypes.c_uint32), ("Flags", ctypes.c_uint32), ("Alloc_Base", ctypes.c_uint32),
                ("Alloc_End", ctypes.c_uint32)]


HEADERS = {1: MEM_DES, 2: IO_DES, 3: DMA_DES, 4: IRQ_DES_64, 6: BUSNUMBER_DES, 7: MEM_LARGE_DES}
P, DW, CR = ctypes.POINTER, ctypes.c_uint32, ctypes.c_uint32
HANDLE = ctypes.c_size_t   # LOG_CONF / RES_DES are DWORD_PTR
RES_EXPORTS = [
    ("setupapi", "SetupDiGetClassDevsW", ctypes.c_void_p, [P(dm.GUID), ctypes.c_void_p, ctypes.c_void_p, DW]),  # PCWSTR as UTF-16LE bytes
    ("setupapi", "SetupDiEnumDeviceInfo", ctypes.c_int32, [ctypes.c_void_p, DW, P(dm.SP_DEVINFO_DATA)]),
    ("setupapi", "SetupDiGetDeviceRegistryPropertyW", ctypes.c_int32, [ctypes.c_void_p, P(dm.SP_DEVINFO_DATA), DW, P(DW), ctypes.c_void_p, DW, P(DW)]),
    ("setupapi", "SetupDiDestroyDeviceInfoList", ctypes.c_int32, [ctypes.c_void_p]),
    ("cfgmgr32", "CM_Get_Device_IDW", CR, [DW, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32]),
    ("cfgmgr32", "CM_Get_First_Log_Conf", CR, [P(HANDLE), DW, ctypes.c_uint32]),
    ("cfgmgr32", "CM_Get_Next_Res_Des", CR, [P(HANDLE), HANDLE, ctypes.c_uint32, P(ctypes.c_uint32), ctypes.c_uint32]),
    ("cfgmgr32", "CM_Get_Res_Des_Data_Size", CR, [P(ctypes.c_uint32), HANDLE, ctypes.c_uint32]),
    ("cfgmgr32", "CM_Get_Res_Des_Data", CR, [HANDLE, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32]),
    ("cfgmgr32", "CM_Free_Res_Des_Handle", CR, [HANDLE]),
    ("cfgmgr32", "CM_Free_Log_Conf_Handle", CR, [HANDLE]),
]


class Binder:
    """Same contract as devicemap.Native: exact prototypes, system-directory loading, stand-ins for tests."""

    def __init__(self, exports, paths=None, last_error=None):
        self.f, self.missing, libs = {}, {}, {}
        for dll, name, res, args in exports:
            if dll not in libs:
                try:
                    libs[dll] = (ctypes.CDLL(paths[dll]) if paths is not None else
                                 ctypes.WinDLL(dll + ".dll", use_last_error=True, winmode=dm.LOAD_LIBRARY_SEARCH_SYSTEM32))
                except (OSError, KeyError, AttributeError) as e:   # AttributeError: no WinDLL off Windows
                    libs[dll] = None
                    self.missing[dll] = f"{dll}.dll not loadable ({type(e).__name__})"
            fn = getattr(libs[dll], name, None) if libs[dll] is not None else None
            if fn is None:
                self.missing.setdefault(name, self.missing.get(dll) or f"{name} not exported")
                continue
            fn.restype, fn.argtypes = res, args
            self.f[name] = fn
        self.last_error = last_error or (ctypes.get_last_error if hasattr(ctypes, "get_last_error") else (lambda: 0))

    def need(self, *names):
        gone = [self.missing.get(n, f"{n} unavailable") for n in names if n not in self.f]
        if gone:
            raise dm.ObservationUnavailable("; ".join(gone))


# pci_resources
def parse_descriptor(rtype, data):
    """One allocated descriptor's header, from exactly the bytes CM_Get_Res_Des_Data returned."""
    cls = HEADERS.get(rtype)
    if cls is None:
        return {"type": "type %d" % rtype, "error": "descriptor type not decoded"}
    if len(data) < ctypes.sizeof(cls):
        return {"type": RES_TYPES[rtype], "error": f"{len(data)} bytes, shorter than its {ctypes.sizeof(cls)}-byte header"}
    h = cls.from_buffer_copy(data[:ctypes.sizeof(cls)])
    out = {"type": RES_TYPES[rtype]}
    if rtype in (1, 2, 7, 6):
        base, end = h.Alloc_Base, h.Alloc_End
        out.update(base="0x%X" % base, end="0x%X" % end, length=(end - base + 1) if end >= base else None,
                   flags="0x%X" % getattr(h, "Flags", getattr(h, "DesFlags", 0)))
        if end < base: out['error'] = 'allocated range end precedes base'
    elif rtype == 4:
        out.update(vector=h.Alloc_Num, flags="0x%X" % (h.Flags & 0xFFFF), group=h.Flags >> 16)
    elif rtype == 3:
        out.update(channel=h.Alloc_Chan, flags="0x%X" % h.Flags)
    return out


def _location(b, h, d):
    buf, t, need = ctypes.create_string_buffer(512), DW(), DW()
    if not b.f["SetupDiGetDeviceRegistryPropertyW"](h, ctypes.byref(d), 0xD, ctypes.byref(t), buf, 512, ctypes.byref(need)):
        return None
    used = min(need.value, 512)
    return buf.raw[:used - (used % 2)].decode("utf-16-le", "replace").split("\0", 1)[0] if t.value in (1, 2) else None


def pci_resources(b):
    """(devices, errors). Present PCI functions only; joined to the device map by device ID + location (report-local)."""
    b.need(*[n for _, n, _, _ in RES_EXPORTS])
    pci = ctypes.create_string_buffer("PCI".encode("utf-16-le") + b"\0\0")   # explicit UTF-16: wchar_t is 4 bytes off Windows
    h = b.f["SetupDiGetClassDevsW"](None, pci, None, DIGCF_PRESENT | DIGCF_ALLCLASSES)
    if h in (None, 0, ctypes.c_void_p(-1).value):
        raise dm.ObservationUnavailable(f"SetupDiGetClassDevsW(PCI) failed (error {b.last_error()})")
    out, errors = [], []
    try:
        for i in range(MAX_RES_DEVICES + 1):
            if i == MAX_RES_DEVICES:
                errors.append(f"stopped at {MAX_RES_DEVICES} PCI functions")
                break
            d = dm.SP_DEVINFO_DATA()
            d.cbSize = ctypes.sizeof(dm.SP_DEVINFO_DATA)
            if not b.f["SetupDiEnumDeviceInfo"](h, i, ctypes.byref(d)):
                err = b.last_error()
                if err != dm.ERROR_NO_MORE_ITEMS:
                    errors.append(f"SetupDiEnumDeviceInfo({i}) error {err}: walk stopped early")
                break
            idbuf = ctypes.create_string_buffer(2 * (dm.MAX_DEVICE_ID_LEN + 1))
            if b.f["CM_Get_Device_IDW"](d.DevInst, idbuf, dm.MAX_DEVICE_ID_LEN + 1, 0) != 0:
                errors.append(f"PCI function {i}: no instance ID")
                continue
            instance = idbuf.raw.decode("utf-16-le", "replace").split("\0", 1)[0]
            dev = dm.instance_key(instance)[1]
            node = dm._report_local_instances.get(instance)
            rec = {"resource_record": "r%d" % i, "node": node,
                   "node_join": "exact present PCI function in this worker's PnP snapshot" if node else "unavailable: exact function not in retained PnP snapshot; not joined by model/location",
                   "device_id": dm.scrub(dev), "location": dm.scrub(_location(b, h, d)), "allocated": []}
            lc = HANDLE()
            cr = b.f["CM_Get_First_Log_Conf"](ctypes.byref(lc), d.DevInst, ALLOC_LOG_CONF)
            if cr == CR_NO_MORE_LOG_CONF:
                rec["status"] = "no allocated configuration"
                rec["observation_status"] = "unavailable"
                out.append(rec)
                continue
            if cr != 0:
                rec["status"] = ("CR_CALL_NOT_IMPLEMENTED: a 32-bit process on 64-bit Windows cannot read resources"
                                 if cr == CR_CALL_NOT_IMPLEMENTED else f"CM_Get_First_Log_Conf CR 0x{cr:X}")
                rec["observation_status"] = "unavailable"
                errors.append("PCI function %d: %s" % (i, rec["status"]))
                out.append(rec)
                continue
            cur, owned = lc.value, False
            try:
                for k in range(MAX_RES_PER_DEVICE + 1):
                    if k == MAX_RES_PER_DEVICE:
                        rec["status"] = f"stopped at {MAX_RES_PER_DEVICE} descriptors"
                        break
                    nxt, rid = HANDLE(), ctypes.c_uint32()
                    cr = b.f["CM_Get_Next_Res_Des"](ctypes.byref(nxt), cur, RES_ALL, ctypes.byref(rid), 0)
                    if owned:
                        b.f["CM_Free_Res_Des_Handle"](cur)
                        owned = False
                    if cr == CR_NO_MORE_RES_DES:
                        owned = False
                        break
                    if cr != 0:
                        rec["status"] = f"CM_Get_Next_Res_Des CR 0x{cr:X}"
                        owned = False
                        break
                    cur, owned = nxt.value, True
                    size = ctypes.c_uint32()
                    if b.f["CM_Get_Res_Des_Data_Size"](ctypes.byref(size), cur, 0) != 0:
                        rec["allocated"].append({"type": RES_TYPES.get(rid.value, "type %d" % rid.value), "error": "size unavailable"})
                        continue
                    if size.value > MAX_RES_DATA:
                        rec["allocated"].append({"type": RES_TYPES.get(rid.value, "type %d" % rid.value),
                                                 "error": f"{size.value} bytes; over the {MAX_RES_DATA}-byte cap, not read"})
                        continue
                    buf = ctypes.create_string_buffer(max(size.value, 1))
                    cr = b.f["CM_Get_Res_Des_Data"](cur, buf, size.value, 0)
                    rec["allocated"].append(parse_descriptor(rid.value, buf.raw[:size.value]) if cr == 0 else
                                            {"type": RES_TYPES.get(rid.value, "type %d" % rid.value), "error": f"CR 0x{cr:X}"})
            finally:
                try:
                    if owned: b.f["CM_Free_Res_Des_Handle"](cur)
                finally:
                    b.f["CM_Free_Log_Conf_Handle"](lc.value)
            descriptor_errors = [item['error'] for item in rec['allocated'] if item.get('error')]
            rec.setdefault("status", "; ".join(descriptor_errors[:3]) if descriptor_errors else "ok")
            rec['observation_status'] = 'measured' if rec['status'] == 'ok' else 'partial'
            if rec['observation_status'] == 'partial': errors.append("PCI function %d: %s" % (i, rec['status']))
            out.append(rec)
    finally:
        b.f["SetupDiDestroyDeviceInfoList"](h)
    return out, errors


# bios_settings
PROVIDERS = [  # (vendor, namespace, class, name property, value property) - documented read-only query classes only
    ("Lenovo", r"root\WMI", "Lenovo_BiosSetting", "CurrentSetting", None),
    ("HP", r"root\HP\InstrumentedBIOS", "HP_BIOSEnumeration", "Name", "CurrentValue"),
    ("Dell", r"root\DCIM\SYSMAN", "DCIM_BIOSEnumeration", "AttributeName", "CurrentValue"),
]
ALLOW = {  # category -> substrings of the vendor's own setting name, lowercased with non-alphanumerics removed
    "above_4g_decoding": ("above4g", "4gdecod", "mmioabove4g", "above4gmmio"),
    "resizable_bar": ("resizebar", "resizablebar", "resizeablebar", "rebar", "smartaccessmemory"),
    "csm_legacy_boot": ("csm", "legacyboot", "legacysupport", "bootmode", "legacyoptionrom", "compatibilitysupportmodule"),
    "secure_boot": ("secureboot",),
    "cfg_lock": ("cfglock", "msr0xe2"),
    "storage_mode": ("vmd", "sataoperation", "satamode", "sataemulation", "satacontrollermode", "storagemode", "raidmode"),
    "virtualization": ("virtualization", "vtx", "vtd", "intelvt", "amdv", "svmmode", "iommu", "vtfordirect"),  # Dell: VtForDirectIo
    "dvmt": ("dvmt", "preallocated", "igdmemory", "umaframebuffer"),
}
# never output, whatever else the name matches: whole words (after splitting CamelCase), plus a few fused forms
DENY_WORDS = re.compile(r"\b(password|passwd|pwd|asset|serial|owner|uuid|tag|mac|address|key|keys|cert|certificate|order|sequence|"
                        r"ip|ipv4|ipv6|hostname|email|phone|custom|database|pin|pins|token|license|licence)\b")
DENY_FUSED = ("password", "serialnumber", "assettag", "bootorder", "bootsequence", "uuid", "macaddress", "ipaddress")
VALUE_OK = re.compile(r"^[A-Za-z0-9 .,+\-/()_]{1,64}$")


def _norm(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _words(name):
    return re.sub(r"[^a-z0-9]+", " ", re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name or "").lower())


def classify(name):
    n = _norm(name)
    if not n or DENY_WORDS.search(_words(name)) or any(x in n for x in DENY_FUSED):
        return None
    for cat, keys in ALLOW.items():
        if any(k in n for k in keys):
            return cat
    return None


def filter_settings(vendor, rows):
    """rows: [(raw name, raw value)] -> only allow-listed settings, value checked against a plain-token pattern."""
    out = []
    for name, value in rows[:MAX_BIOS_ROWS]:
        cat = classify(name)
        if cat is None:
            continue
        v = value if isinstance(value, str) else ",".join(str(x) for x in value) if isinstance(value, list) else str(value)
        v = v.strip()
        out.append({"category": cat, "vendor": vendor, "vendor_field": dm.scrub(name)[:80],
                    "value": dm.scrub(v) if VALUE_OK.fullmatch(v) else None,
                    **({} if VALUE_OK.fullmatch(v) else {"value_status": "withheld: not a plain setting token"})})
    return out


def rows_from(vendor, objs, name_prop, value_prop):
    rows = []
    for o in objs if isinstance(objs, list) else [objs]:
        if not isinstance(o, dict):
            continue
        if vendor == "Lenovo":   # "Item,Value" or "Item,Value;[Optional:...]"
            s = o.get(name_prop) or ""
            if "," in s:
                item, rest = s.split(",", 1)
                rows.append((item, rest.split(";", 1)[0]))
        else:
            rows.append((o.get(name_prop) or "", o.get(value_prop)))
    return rows


def _bounded_process(command, environment, timeout):
    from . import job_guard
    budget = min(timeout, PS_TIMEOUT)
    if budget < 0.05:
        return None, "worker time budget exhausted; query not started"
    data, code, reason = job_guard.run_bounded(command, environment, budget)
    if reason: return None, reason
    if code: return None, "BIOS query process failed (exit %d)" % code
    try:
        payload = json.loads(data.decode("utf-8-sig"))
    except (ValueError, UnicodeError): return None, "BIOS query output invalid"
    if not isinstance(payload, dict): return None, "BIOS query output invalid"
    status = payload.get("status")
    if status == "provider_absent": return None, "provider not present"
    if status == "access_denied": return None, "access denied"
    if status != "ok":
        phase = payload.get('phase')
        if phase not in ('encoding','utility_module','cim_module','cim_query','serialization'): phase='unknown'
        hresult = payload.get('hresult'); mi = payload.get('mi_code')
        suffix = ' phase='+phase
        if type(hresult) is int and -2147483648 <= hresult <= 2147483647: suffix += ' hresult=%d' % hresult
        if type(mi) is int and -1 <= mi <= 65535: suffix += ' mi_code=%d' % mi
        return None, "BIOS provider query failed;" + suffix
    rows = payload.get("rows") or []
    if not isinstance(rows, list): return None, "BIOS query rows invalid"
    if len(rows) > MAX_BIOS_ROWS: return rows[:MAX_BIOS_ROWS], "BIOS rows truncated to the observation limit"
    return rows, None


def _cim_script(namespace, cls, props):
    # Every bootstrap and query phase is covered; a bootstrap failure can report fixed JSON without a serializer.
    return (r"$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; $phase='encoding'; "
            r"try { [Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); "
            r"$PSModuleAutoLoadingPreference='None'; $phase='utility_module'; "
            r"Import-Module ($PSHOME+'\Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1'); "
            r"$phase='cim_module'; Import-Module ($PSHOME+'\Modules\CimCmdlets\CimCmdlets.psd1'); "
            r"$phase='cim_query'; $rows=@(CimCmdlets\Get-CimInstance -Namespace '%s' -ClassName '%s' | "
            r"Microsoft.PowerShell.Utility\Select-Object -First %d -Property %s); "
            r"$phase='serialization'; $r=@{status='ok';phase='complete';hresult=0;mi_code=0;rows=$rows}; "
            r"Microsoft.PowerShell.Utility\ConvertTo-Json -InputObject $r -Compress -Depth 4 } "
            r"catch { $h=[int]$_.Exception.HResult; $mi=-1; "
            r"if ($_.Exception.PSObject.Properties.Name -contains 'NativeErrorCode') {$mi=[int]$_.Exception.NativeErrorCode}; "
            r"$status='failed'; if ($phase -eq 'cim_query') { "
            r"if ($mi -eq 3 -or $mi -eq 5 -or $h -eq -2147217394 -or $h -eq -2147217392) {$status='provider_absent'}; "
            r"if ($mi -eq 2 -or $h -eq -2147217405 -or $h -eq -2147024891) {$status='access_denied'} }; "
            r'''[Console]::WriteLine('{"status":"'+$status+'","phase":"'+$phase+'","hresult":'+$h+',"mi_code":'+$mi+',"rows":[]}') }'''
            % (namespace, cls, MAX_BIOS_ROWS+1, ','.join(props)))


def powershell_cim(namespace, cls, props, timeout=PS_TIMEOUT):
    """Read-only fixed vendor query, from a pinned actual system path in the disposable worker's job."""
    from . import hwcapture, job_guard
    allowed = any(namespace == ns and cls == classname and props == [name] + ([value] if value else [])
                  for _, ns, classname, name, value in PROVIDERS)
    if not allowed: return None, "query is outside the documented provider allow-list"
    if not job_guard.ready(): return None, "subprocess containment unavailable; BIOS query not started"
    return _run_system_cim(namespace, cls, props, timeout)


def _run_system_cim(namespace, cls, props, timeout):
    from . import hwcapture, job_guard
    if not job_guard.ready(): return None, "subprocess containment unavailable; CIM query not started"
    deadline = time.monotonic() + min(timeout, PS_TIMEOUT)
    try:
        kernel = hwcapture._kernel32()
        kernel.GetSystemDirectoryW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
        kernel.GetSystemDirectoryW.restype = ctypes.c_uint32
        directory = ctypes.create_unicode_buffer(32768)
        size = kernel.GetSystemDirectoryW(directory, len(directory))
        if not 0 < size < len(directory): return None, "Windows system directory unavailable"
        ps = os.path.join(directory.value, "WindowsPowerShell", "v1.0", "powershell.exe")
        script = _cim_script(namespace, cls, props)
        environment = {key: value for key, value in os.environ.items() if not key.upper().startswith('PS')}
        kernel.GetWindowsDirectoryW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
        kernel.GetWindowsDirectoryW.restype = ctypes.c_uint32
        windows = ctypes.create_unicode_buffer(32768)
        size = kernel.GetWindowsDirectoryW(windows, len(windows))
        if not 0 < size < len(windows): return None, "Windows directory unavailable"
        environment = {key: value for key, value in environment.items() if key.upper() not in ('SYSTEMROOT', 'WINDIR', 'PATH')}
        environment.update({'PATH': directory.value, 'SystemRoot': windows.value, 'WINDIR': windows.value})
        encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
        with hwcapture._system_file(ps):
            # Verification/bootstrap work consumes the supplied budget; it does not grant a fresh process window.
            budget = deadline - time.monotonic()
            return _bounded_process([ps, '-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded], environment, budget)
    except Exception as error:
        return None, "BIOS query unavailable (%s)" % type(error).__name__


def _cim_engine_smoke():
    rows, error = _run_system_cim(r'root\CIMV2', 'Win32_OperatingSystem', ['BuildNumber'], PS_TIMEOUT)
    if error: return {'ok':False,'reason':error}
    valid = bool(rows) and all(isinstance(row,dict) and isinstance(row.get('BuildNumber'),str) and re.fullmatch(r'[0-9]{1,8}',row['BuildNumber']) for row in rows)
    return {'ok':valid,'fixed_read_only_cim_query':valid}


def bios_settings(query=powershell_cim, remaining=None):
    """(value, errors). value = {"providers": {vendor: status}, "settings": [...]}; unavailable when no provider exists."""
    providers, settings, errors = {}, [], []
    for vendor, ns, cls, name_prop, value_prop in PROVIDERS:
        if remaining is not None and remaining() < 0.15:
            providers[vendor] = 'worker time budget exhausted; query not started'
            errors.append(vendor + ': worker time budget exhausted; query not started')
            continue
        if remaining is None:
            objs, err = query(ns, cls, [name_prop] + ([value_prop] if value_prop else []))
        else:
            objs, err = query(ns, cls, [name_prop] + ([value_prop] if value_prop else []), timeout=min(PS_TIMEOUT, remaining()))
        if err:
            providers[vendor] = err
            if err != "provider not present": errors.append(f"{vendor}: {err}")
            if objs is None: continue
        else: providers[vendor] = "present"
        settings += filter_settings(vendor, rows_from(vendor, objs, name_prop, value_prop))
    if not any(v == "present" for v in providers.values()) and not errors:
        raise dm.ObservationUnavailable("no documented vendor BIOS provider is installed (Lenovo, HP, Dell); BIOS settings are not observable here")
    seen = {s["category"] for s in settings}
    return {"providers": providers, "settings": settings,
            "not_reported": sorted(set(ALLOW) - seen),
            "meaning": "the firmware's current values as the vendor provider reports them; a category it does not list is unknown, not off"}, errors


# nvidia_detail
ARCH = {2: "Kepler", 3: "Maxwell", 4: "Pascal", 5: "Volta", 6: "Turing", 7: "Ampere", 8: "Ada", 9: "Hopper", 10: "Blackwell",
        0xFFFFFFFF: "unknown to this driver"}
COMPUTE_MODE = {0: "default", 1: "exclusive thread (removed)", 2: "prohibited", 3: "exclusive process"}
VIRT_MODE = {0: "none reported by this driver", 1: "passthrough", 2: "vGPU guest", 3: "vGPU host", 4: "vSGA host"}
U, I_ = ctypes.c_uint32, ctypes.c_int32
NVML_EXPORTS = [  # nvml.h (NVML_API_VERSION 12)
    ("nvmlInit_v2", I_, []), ("nvmlShutdown", I_, []),
    ("nvmlSystemGetDriverVersion", I_, [ctypes.c_char_p, U]), ("nvmlSystemGetCudaDriverVersion_v2", I_, [P(I_)]),
    ("nvmlDeviceGetCount_v2", I_, [P(U)]), ("nvmlDeviceGetHandleByIndex_v2", I_, [U, P(ctypes.c_void_p)]),
    ("nvmlDeviceGetPciInfo_v3", I_, [ctypes.c_void_p, ctypes.c_void_p]),
    ("nvmlDeviceGetArchitecture", I_, [ctypes.c_void_p, P(U)]), ("nvmlDeviceGetVbiosVersion", I_, [ctypes.c_void_p, ctypes.c_char_p, U]),
    ("nvmlDeviceGetCurrPcieLinkGeneration", I_, [ctypes.c_void_p, P(U)]), ("nvmlDeviceGetCurrPcieLinkWidth", I_, [ctypes.c_void_p, P(U)]),
    ("nvmlDeviceGetMaxPcieLinkGeneration", I_, [ctypes.c_void_p, P(U)]), ("nvmlDeviceGetMaxPcieLinkWidth", I_, [ctypes.c_void_p, P(U)]),
    ("nvmlDeviceGetComputeMode", I_, [ctypes.c_void_p, P(I_)]), ("nvmlDeviceGetVirtualizationMode", I_, [ctypes.c_void_p, P(I_)]),
    ("nvmlDeviceGetMigMode", I_, [ctypes.c_void_p, P(U), P(U)]), ("nvmlDeviceGetMaxMigDeviceCount", I_, [ctypes.c_void_p, P(U)]),
]
NVML_NOT_SUPPORTED = 3
VBIOS_OK = re.compile(r"^[0-9A-Fa-f]{1,4}(?:\.[0-9A-Fa-f]{1,4}){1,7}$")
REQUIRED = ("nvmlInit_v2", "nvmlShutdown", "nvmlDeviceGetCount_v2", "nvmlDeviceGetHandleByIndex_v2", "nvmlDeviceGetPciInfo_v3")


class NvmlPciInfo(ctypes.Structure):
    _fields_ = [("busIdLegacy", ctypes.c_char * 16), ("domain", U), ("bus", U), ("device", U), ("pciDeviceId", U),
                ("pciSubSystemId", U), ("busId", ctypes.c_char * 32)]


def bind_nvml(lib):
    f, missing = {}, []
    for name, res, args in NVML_EXPORTS:
        fn = getattr(lib, name, None)
        if fn is None:
            missing.append(name)
            continue
        fn.restype, fn.argtypes = res, args
        f[name] = fn
    return f, missing


def open_nvml():
    """Use the verified system file-handle and loaded-module identity checks shared by capture."""
    from . import hwcapture
    lib, error = hwcapture.open_vendor_library("nvml.dll")
    if lib is None:
        raise dm.ObservationUnavailable(error)
    return bind_nvml(lib)


def _version(value, numeric=False):
    text = value.decode("ascii", errors="replace")
    rule = re.compile(r"[0-9]{1,10}(?:\.[0-9]{1,10}){1,7}") if numeric else VBIOS_OK
    if not rule.fullmatch(text): raise ValueError("unexpected version format")
    return text


def _field(f, name, call, conv, src="nvml"):
    if name not in f:
        return dm.unavailable(f"{name} not exported by this driver's NVML", src)
    rc, v = call(f[name])
    if rc == 0:
        try: converted = conv(v)
        except (ValueError, UnicodeError): return dm.unavailable("unexpected API value format", f"{src}:{name}")
        return dm.measured(converted, f"{src}:{name}")
    return dm.unavailable("not supported on this device" if rc == NVML_NOT_SUPPORTED else f"nvml error {rc}", f"{src}:{name}")


def _pci_address(pci):
    from . import hwcapture
    text = pci.busId.decode("ascii", errors="replace")
    address = hwcapture._parse_pci(text)
    if address and address[:3] == (pci.domain, pci.bus, pci.device):
        return hwcapture._pci_key(*address)
    return None


def nvidia_detail(nvml=None):
    """(value, errors). nvml = (bound functions, missing exports); default opens the system NVML."""
    f, missing = nvml if nvml is not None else open_nvml()
    gone = [n for n in REQUIRED if n not in f]
    if gone:
        raise dm.ObservationUnavailable("NVML lacks " + ", ".join(gone))
    if f["nvmlInit_v2"]() != 0:
        raise dm.ObservationUnavailable("nvmlInit_v2 failed")
    errors, out = [], {"missing_exports": missing}
    try:
        buf = ctypes.create_string_buffer(80)   # NVML_SYSTEM_DRIVER_VERSION_BUFFER_SIZE
        out["driver_version"] = _field(f, "nvmlSystemGetDriverVersion", lambda fn: (fn(buf, 80), buf.value), lambda v: _version(v, numeric=True))
        cv = ctypes.c_int32()
        out["cuda_driver_version"] = _field(f, "nvmlSystemGetCudaDriverVersion_v2", lambda fn: (fn(ctypes.byref(cv)), cv.value),
                                            lambda v: "%d.%d" % (v // 1000, v % 1000 // 10))
        n = U()
        if f["nvmlDeviceGetCount_v2"](ctypes.byref(n)) != 0:
            raise dm.ObservationUnavailable("nvmlDeviceGetCount_v2 failed")
        devices = []
        if n.value > 16: errors.append("device detail limited to 16 records")
        for i in range(min(n.value, 16)):
            h = ctypes.c_void_p()
            if f["nvmlDeviceGetHandleByIndex_v2"](i, ctypes.byref(h)) != 0 or not h.value:
                errors.append(f"device {i}: no handle")
                continue
            pci = NvmlPciInfo()
            if f["nvmlDeviceGetPciInfo_v3"](h, ctypes.byref(pci)) != 0:
                errors.append(f"device {i}: no PCI info; not recorded")
                continue
            d = {"device_record": "g%d" % i, "pci_bus_id": _pci_address(pci), "device_id": "%04X-%04X" % (pci.pciDeviceId & 0xFFFF, pci.pciDeviceId >> 16),
                 "subsystem_id": "%08X" % pci.pciSubSystemId}
            d['pci_identity_status'] = 'complete PCI function' if d['pci_bus_id'] else 'unavailable full PCI function; not joined'

            def u(name):
                v = U()
                return _field(f, name, lambda fn: (fn(h, ctypes.byref(v)), v.value), int)

            def i32(name, table):
                v = ctypes.c_int32()
                return _field(f, name, lambda fn: (fn(h, ctypes.byref(v)), v.value), lambda x: {"code": x, "name": table.get(x, "code %d" % x)})
            a = U()
            d["architecture"] = _field(f, "nvmlDeviceGetArchitecture", lambda fn: (fn(h, ctypes.byref(a)), a.value),
                                       lambda x: {"code": x, "name": ARCH.get(x, "code %d" % x)})
            vb = ctypes.create_string_buffer(32)   # NVML_DEVICE_VBIOS_VERSION_BUFFER_SIZE
            # a VBIOS version (94.02.42.00.A9) is dotted hex that an address scrub would eat: validated, never scrubbed
            d["vbios_version"] = _field(f, "nvmlDeviceGetVbiosVersion", lambda fn: (fn(h, vb, 32), vb.value),
                                        lambda v: _version(v))
            for key, name in (("pcie_gen_current", "nvmlDeviceGetCurrPcieLinkGeneration"), ("pcie_width_current", "nvmlDeviceGetCurrPcieLinkWidth"),
                              ("pcie_gen_max", "nvmlDeviceGetMaxPcieLinkGeneration"), ("pcie_width_max", "nvmlDeviceGetMaxPcieLinkWidth"),
                              ("max_mig_devices", "nvmlDeviceGetMaxMigDeviceCount")):
                d[key] = u(name)
            d["compute_mode"] = i32("nvmlDeviceGetComputeMode", COMPUTE_MODE)
            d["virtualization_mode"] = i32("nvmlDeviceGetVirtualizationMode", VIRT_MODE)
            cur, pend = U(), U()
            d["mig_mode"] = _field(f, "nvmlDeviceGetMigMode", lambda fn: (fn(h, ctypes.byref(cur), ctypes.byref(pend)), (cur.value, pend.value)),
                                   lambda v: {"current_code": v[0], "pending_code": v[1], "current": {0: "disabled", 1: "enabled"}.get(v[0], "code %d" % v[0]), "pending": {0: "disabled", 1: "enabled"}.get(v[1], "code %d" % v[1]),
                                              "note": "MIG partitions share this GPU's PCI address; they are not enumerated here"})
            d["tensor_cores"] = dm.unavailable("not reported by NVML; not derived from the architecture", "none")
            d["rt_cores"] = dm.unavailable("not reported by NVML; not derived from the architecture", "none")
            devices.append(d)
        out["devices"] = devices
    finally:
        f["nvmlShutdown"]()
    return out, errors


# worker wiring
EXTRA_STAGES = ("pci_resources", "nvidia_detail", "bios_settings")   # run in this order, after devicemap's four
EXTRA_SOURCES = {"pci_resources": "CfgMgr32 allocated logical configuration (ALLOC_LOG_CONF)",
                 "bios_settings": "vendor WMI BIOS provider (read-only CIM query)",
                 "nvidia_detail": "NVML (system nvml.dll)"}


def native_backends():
    """Bound lazily: nothing is loaded until the worker reaches the stage."""
    return {"pci_resources": lambda: pci_resources(Binder(RES_EXPORTS)), "bios_settings": bios_settings, "nvidia_detail": nvidia_detail}
