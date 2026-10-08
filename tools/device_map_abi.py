"""Real Windows SDK ABI check for p1401/devicemap.py, for the Windows CI runner (MSVC or clang-cl with the Windows SDK):

    python tests\\abi_windows_sdk.py abi_sdk.c
    cl /nologo /c /W3 /TC abi_sdk.c          (or: clang-cl /c abi_sdk.c)

The generated C file includes the SDK's own headers and asserts, at compile time, every struct size and field offset the
ctypes structures use, the COM vtable slots called (as offsetof(<Interface>Vtbl, Method) / sizeof(void *)), the IIDs and
the constants. A compile error is a mismatch. Nothing runs."""
import ctypes
import os
import sys

sys.path.insert(0, os.getcwd())
from p1401 import devicemap as d  # noqa: E402

HEAD = """#define COBJMACROS
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <initguid.h>
#include <dxgi.h>
#include <d3d12.h>
#include <setupapi.h>
#include <cfgmgr32.h>
#include <devpkey.h>
#include <powrprof.h>
#include <stddef.h>
#define A(c, m) _Static_assert(c, m)
"""
STRUCTS = {"DXGI_ADAPTER_DESC1": d.DXGI_ADAPTER_DESC1, "D3D12_FEATURE_DATA_D3D12_OPTIONS5": d.D3D12_FEATURE_DATA_D3D12_OPTIONS5,
           "DISPLAYCONFIG_PATH_INFO": d.DISPLAYCONFIG_PATH_INFO, "DISPLAYCONFIG_PATH_SOURCE_INFO": d.DISPLAYCONFIG_PATH_SOURCE_INFO,
           "DISPLAYCONFIG_PATH_TARGET_INFO": d.DISPLAYCONFIG_PATH_TARGET_INFO, "SP_DEVINFO_DATA": d.SP_DEVINFO_DATA,
           "DEVPROPKEY": d.DEVPROPKEY, "LUID": d.LUID, "GUID": d.GUID}
RENAME = {"refreshNum": "refreshRate.Numerator", "refreshDen": "refreshRate.Denominator", "Data4": "Data4"}
VTBL = [("IDXGIFactory1Vtbl", "EnumAdapters1", d.VT_FACTORY1_ENUMADAPTERS1), ("IDXGIAdapter1Vtbl", "GetDesc1", d.VT_ADAPTER1_GETDESC1),
        ("ID3D12DeviceVtbl", "CheckFeatureSupport", d.VT_DEVICE_CHECKFEATURESUPPORT), ("IUnknownVtbl", "Release", d.VT_RELEASE)]
CONSTS = [("D3D12_FEATURE_D3D12_OPTIONS5", d.D3D12_FEATURE_D3D12_OPTIONS5), ("D3D_FEATURE_LEVEL_11_0", d.D3D_FEATURE_LEVEL_11_0),
          ("DXGI_ERROR_NOT_FOUND", d.DXGI_ERROR_NOT_FOUND), ("QDC_ONLY_ACTIVE_PATHS", d.QDC_ONLY_ACTIVE_PATHS),
          ("DIGCF_PRESENT", d.DIGCF_PRESENT), ("DIGCF_ALLCLASSES", d.DIGCF_ALLCLASSES), ("SPDRP_DEVICEDESC", d.SPDRP["description"]),
          ("SPDRP_HARDWAREID", d.SPDRP["hardware_ids"]), ("SPDRP_COMPATIBLEIDS", d.SPDRP["compatible_ids"]), ("SPDRP_CLASS", d.SPDRP["class"]),
          ("SPDRP_MFG", d.SPDRP["manufacturer"]), ("SPDRP_LOCATION_INFORMATION", d.SPDRP["location"]),
          ("SPDRP_LOCATION_PATHS", d.SPDRP["location_paths"]), ("DN_STARTED", d.DN_STARTED), ("DN_HAS_PROBLEM", d.DN_HAS_PROBLEM),
          ("MAX_DEVICE_ID_LEN", d.MAX_DEVICE_ID_LEN), ("ERROR_INVALID_DATA", d.ERROR_INVALID_DATA),
          ("ERROR_INSUFFICIENT_BUFFER", d.ERROR_INSUFFICIENT_BUFFER), ("ERROR_NO_MORE_ITEMS", d.ERROR_NO_MORE_ITEMS),
          ("ERROR_NOT_FOUND", d.ERROR_NOT_FOUND), ("REG_SZ", d.REG_SZ), ("REG_EXPAND_SZ", d.REG_EXPAND_SZ), ("REG_MULTI_SZ", d.REG_MULTI_SZ),
          ("DEVPROP_TYPE_STRING", d.DEVPROP_TYPE_STRING), ("LOAD_LIBRARY_SEARCH_SYSTEM32", d.LOAD_LIBRARY_SEARCH_SYSTEM32),
          ("CR_SUCCESS", d.CR_SUCCESS), ("DXGI_ADAPTER_FLAG_SOFTWARE", 2), ("POWER_PLATFORM_ROLE_V2", 2)]
GUIDS = [("IID_IDXGIFactory1", d.IID_IDXGIFactory1), ("IID_ID3D12Device", d.IID_ID3D12Device)]


def generate():
    out = [HEAD]
    for name, py in STRUCTS.items():
        out.append(f'A(sizeof({name}) == {ctypes.sizeof(py)}, "{name} size");')
        for f in py._fields_:
            out.append(f'A(offsetof({name}, {RENAME.get(f[0], f[0])}) == {getattr(py, f[0]).offset}, "{name}.{f[0]} offset");')
    for vt, m, slot in VTBL:
        out.append(f'A(offsetof({vt}, {m}) / sizeof(void *) == {slot}, "{vt}.{m} slot");')
    for c, v in CONSTS:
        out.append(f'A((long long)({c}) == (long long)({v}), "{c}");')
    out.append("int check_guids(void) {")
    for g, v in GUIDS:
        out.append(f"  if ({g}.Data1 != {v[0]:#x}u || {g}.Data2 != {v[1]:#x} || {g}.Data3 != {v[2]:#x}) return 1;")
        out += [f"  if ({g}.Data4[{i}] != {b:#x}) return 1;" for i, b in enumerate(v[3:])]
    out.append("  if (DEVPKEY_Device_DriverVersion.pid != %d || DEVPKEY_Device_DriverProvider.pid != %d) return 1;"
               % (d.DEVPKEY_DRIVER_VERSION, d.DEVPKEY_DRIVER_PROVIDER))
    out.append("  if (DEVPKEY_Device_DriverVersion.fmtid.Data1 != %#xu) return 1;" % d.DRIVER_FMTID[0])
    out.append("  return 0;\n}")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    open(sys.argv[1], "w").write(generate())
    print("wrote", sys.argv[1])
