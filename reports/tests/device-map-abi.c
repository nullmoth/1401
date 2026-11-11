#define COBJMACROS
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

A(sizeof(DXGI_ADAPTER_DESC1) == 312, "DXGI_ADAPTER_DESC1 size");
A(offsetof(DXGI_ADAPTER_DESC1, Description) == 0, "DXGI_ADAPTER_DESC1.Description offset");
A(offsetof(DXGI_ADAPTER_DESC1, VendorId) == 256, "DXGI_ADAPTER_DESC1.VendorId offset");
A(offsetof(DXGI_ADAPTER_DESC1, DeviceId) == 260, "DXGI_ADAPTER_DESC1.DeviceId offset");
A(offsetof(DXGI_ADAPTER_DESC1, SubSysId) == 264, "DXGI_ADAPTER_DESC1.SubSysId offset");
A(offsetof(DXGI_ADAPTER_DESC1, Revision) == 268, "DXGI_ADAPTER_DESC1.Revision offset");
A(offsetof(DXGI_ADAPTER_DESC1, DedicatedVideoMemory) == 272, "DXGI_ADAPTER_DESC1.DedicatedVideoMemory offset");
A(offsetof(DXGI_ADAPTER_DESC1, DedicatedSystemMemory) == 280, "DXGI_ADAPTER_DESC1.DedicatedSystemMemory offset");
A(offsetof(DXGI_ADAPTER_DESC1, SharedSystemMemory) == 288, "DXGI_ADAPTER_DESC1.SharedSystemMemory offset");
A(offsetof(DXGI_ADAPTER_DESC1, AdapterLuid) == 296, "DXGI_ADAPTER_DESC1.AdapterLuid offset");
A(offsetof(DXGI_ADAPTER_DESC1, Flags) == 304, "DXGI_ADAPTER_DESC1.Flags offset");
A(sizeof(D3D12_FEATURE_DATA_D3D12_OPTIONS5) == 12, "D3D12_FEATURE_DATA_D3D12_OPTIONS5 size");
A(offsetof(D3D12_FEATURE_DATA_D3D12_OPTIONS5, SRVOnlyTiledResourceTier3) == 0, "D3D12_FEATURE_DATA_D3D12_OPTIONS5.SRVOnlyTiledResourceTier3 offset");
A(offsetof(D3D12_FEATURE_DATA_D3D12_OPTIONS5, RenderPassesTier) == 4, "D3D12_FEATURE_DATA_D3D12_OPTIONS5.RenderPassesTier offset");
A(offsetof(D3D12_FEATURE_DATA_D3D12_OPTIONS5, RaytracingTier) == 8, "D3D12_FEATURE_DATA_D3D12_OPTIONS5.RaytracingTier offset");
A(sizeof(DISPLAYCONFIG_PATH_INFO) == 72, "DISPLAYCONFIG_PATH_INFO size");
A(offsetof(DISPLAYCONFIG_PATH_INFO, sourceInfo) == 0, "DISPLAYCONFIG_PATH_INFO.sourceInfo offset");
A(offsetof(DISPLAYCONFIG_PATH_INFO, targetInfo) == 20, "DISPLAYCONFIG_PATH_INFO.targetInfo offset");
A(offsetof(DISPLAYCONFIG_PATH_INFO, flags) == 68, "DISPLAYCONFIG_PATH_INFO.flags offset");
A(sizeof(DISPLAYCONFIG_PATH_SOURCE_INFO) == 20, "DISPLAYCONFIG_PATH_SOURCE_INFO size");
A(offsetof(DISPLAYCONFIG_PATH_SOURCE_INFO, adapterId) == 0, "DISPLAYCONFIG_PATH_SOURCE_INFO.adapterId offset");
A(offsetof(DISPLAYCONFIG_PATH_SOURCE_INFO, id) == 8, "DISPLAYCONFIG_PATH_SOURCE_INFO.id offset");
A(offsetof(DISPLAYCONFIG_PATH_SOURCE_INFO, modeInfoIdx) == 12, "DISPLAYCONFIG_PATH_SOURCE_INFO.modeInfoIdx offset");
A(offsetof(DISPLAYCONFIG_PATH_SOURCE_INFO, statusFlags) == 16, "DISPLAYCONFIG_PATH_SOURCE_INFO.statusFlags offset");
A(sizeof(DISPLAYCONFIG_PATH_TARGET_INFO) == 48, "DISPLAYCONFIG_PATH_TARGET_INFO size");
A(offsetof(DISPLAYCONFIG_PATH_TARGET_INFO, adapterId) == 0, "DISPLAYCONFIG_PATH_TARGET_INFO.adapterId offset");
A(offsetof(DISPLAYCONFIG_PATH_TARGET_INFO, id) == 8, "DISPLAYCONFIG_PATH_TARGET_INFO.id offset");
A(offsetof(DISPLAYCONFIG_PATH_TARGET_INFO, modeInfoIdx) == 12, "DISPLAYCONFIG_PATH_TARGET_INFO.modeInfoIdx offset");
A(offsetof(DISPLAYCONFIG_PATH_TARGET_INFO, outputTechnology) == 16, "DISPLAYCONFIG_PATH_TARGET_INFO.outputTechnology offset");
A(offsetof(DISPLAYCONFIG_PATH_TARGET_INFO, rotation) == 20, "DISPLAYCONFIG_PATH_TARGET_INFO.rotation offset");
A(offsetof(DISPLAYCONFIG_PATH_TARGET_INFO, scaling) == 24, "DISPLAYCONFIG_PATH_TARGET_INFO.scaling offset");
A(offsetof(DISPLAYCONFIG_PATH_TARGET_INFO, refreshRate.Numerator) == 28, "DISPLAYCONFIG_PATH_TARGET_INFO.refreshNum offset");
A(offsetof(DISPLAYCONFIG_PATH_TARGET_INFO, refreshRate.Denominator) == 32, "DISPLAYCONFIG_PATH_TARGET_INFO.refreshDen offset");
A(offsetof(DISPLAYCONFIG_PATH_TARGET_INFO, scanLineOrdering) == 36, "DISPLAYCONFIG_PATH_TARGET_INFO.scanLineOrdering offset");
A(offsetof(DISPLAYCONFIG_PATH_TARGET_INFO, targetAvailable) == 40, "DISPLAYCONFIG_PATH_TARGET_INFO.targetAvailable offset");
A(offsetof(DISPLAYCONFIG_PATH_TARGET_INFO, statusFlags) == 44, "DISPLAYCONFIG_PATH_TARGET_INFO.statusFlags offset");
A(sizeof(SP_DEVINFO_DATA) == 32, "SP_DEVINFO_DATA size");
A(offsetof(SP_DEVINFO_DATA, cbSize) == 0, "SP_DEVINFO_DATA.cbSize offset");
A(offsetof(SP_DEVINFO_DATA, ClassGuid) == 4, "SP_DEVINFO_DATA.ClassGuid offset");
A(offsetof(SP_DEVINFO_DATA, DevInst) == 20, "SP_DEVINFO_DATA.DevInst offset");
A(offsetof(SP_DEVINFO_DATA, Reserved) == 24, "SP_DEVINFO_DATA.Reserved offset");
A(sizeof(DEVPROPKEY) == 20, "DEVPROPKEY size");
A(offsetof(DEVPROPKEY, fmtid) == 0, "DEVPROPKEY.fmtid offset");
A(offsetof(DEVPROPKEY, pid) == 16, "DEVPROPKEY.pid offset");
A(sizeof(LUID) == 8, "LUID size");
A(offsetof(LUID, LowPart) == 0, "LUID.LowPart offset");
A(offsetof(LUID, HighPart) == 4, "LUID.HighPart offset");
A(sizeof(GUID) == 16, "GUID size");
A(offsetof(GUID, Data1) == 0, "GUID.Data1 offset");
A(offsetof(GUID, Data2) == 4, "GUID.Data2 offset");
A(offsetof(GUID, Data3) == 6, "GUID.Data3 offset");
A(offsetof(GUID, Data4) == 8, "GUID.Data4 offset");
A(offsetof(IDXGIFactory1Vtbl, EnumAdapters1) / sizeof(void *) == 12, "IDXGIFactory1Vtbl.EnumAdapters1 slot");
A(offsetof(IDXGIAdapter1Vtbl, GetDesc1) / sizeof(void *) == 10, "IDXGIAdapter1Vtbl.GetDesc1 slot");
A(offsetof(ID3D12DeviceVtbl, CheckFeatureSupport) / sizeof(void *) == 13, "ID3D12DeviceVtbl.CheckFeatureSupport slot");
A(offsetof(IUnknownVtbl, Release) / sizeof(void *) == 2, "IUnknownVtbl.Release slot");
A((long long)(D3D12_FEATURE_D3D12_OPTIONS5) == (long long)(27), "D3D12_FEATURE_D3D12_OPTIONS5");
A((long long)(D3D_FEATURE_LEVEL_11_0) == (long long)(45056), "D3D_FEATURE_LEVEL_11_0");
A((unsigned long)(DXGI_ERROR_NOT_FOUND) == (unsigned long)(2289696770), "DXGI_ERROR_NOT_FOUND");
A((long long)(QDC_ONLY_ACTIVE_PATHS) == (long long)(2), "QDC_ONLY_ACTIVE_PATHS");
A((long long)(DIGCF_PRESENT) == (long long)(2), "DIGCF_PRESENT");
A((long long)(DIGCF_ALLCLASSES) == (long long)(4), "DIGCF_ALLCLASSES");
A((long long)(SPDRP_DEVICEDESC) == (long long)(0), "SPDRP_DEVICEDESC");
A((long long)(SPDRP_HARDWAREID) == (long long)(1), "SPDRP_HARDWAREID");
A((long long)(SPDRP_COMPATIBLEIDS) == (long long)(2), "SPDRP_COMPATIBLEIDS");
A((long long)(SPDRP_CLASS) == (long long)(7), "SPDRP_CLASS");
A((long long)(SPDRP_MFG) == (long long)(11), "SPDRP_MFG");
A((long long)(SPDRP_LOCATION_INFORMATION) == (long long)(13), "SPDRP_LOCATION_INFORMATION");
A((long long)(SPDRP_LOCATION_PATHS) == (long long)(35), "SPDRP_LOCATION_PATHS");
A((long long)(DN_STARTED) == (long long)(8), "DN_STARTED");
A((long long)(DN_HAS_PROBLEM) == (long long)(1024), "DN_HAS_PROBLEM");
A((long long)(MAX_DEVICE_ID_LEN) == (long long)(200), "MAX_DEVICE_ID_LEN");
A((long long)(ERROR_INVALID_DATA) == (long long)(13), "ERROR_INVALID_DATA");
A((long long)(ERROR_INSUFFICIENT_BUFFER) == (long long)(122), "ERROR_INSUFFICIENT_BUFFER");
A((long long)(ERROR_NO_MORE_ITEMS) == (long long)(259), "ERROR_NO_MORE_ITEMS");
A((long long)(ERROR_NOT_FOUND) == (long long)(1168), "ERROR_NOT_FOUND");
A((long long)(REG_SZ) == (long long)(1), "REG_SZ");
A((long long)(REG_EXPAND_SZ) == (long long)(2), "REG_EXPAND_SZ");
A((long long)(REG_MULTI_SZ) == (long long)(7), "REG_MULTI_SZ");
A((long long)(DEVPROP_TYPE_STRING) == (long long)(18), "DEVPROP_TYPE_STRING");
A((long long)(LOAD_LIBRARY_SEARCH_SYSTEM32) == (long long)(2048), "LOAD_LIBRARY_SEARCH_SYSTEM32");
A((long long)(CR_SUCCESS) == (long long)(0), "CR_SUCCESS");
A((long long)(DXGI_ADAPTER_FLAG_SOFTWARE) == (long long)(2), "DXGI_ADAPTER_FLAG_SOFTWARE");
A((long long)(POWER_PLATFORM_ROLE_V2) == (long long)(2), "POWER_PLATFORM_ROLE_V2");
int check_guids(void) {
  if (IID_IDXGIFactory1.Data1 != 0x770aae78u || IID_IDXGIFactory1.Data2 != 0xf26f || IID_IDXGIFactory1.Data3 != 0x4dba) return 1;
  if (IID_IDXGIFactory1.Data4[0] != 0xa8) return 1;
  if (IID_IDXGIFactory1.Data4[1] != 0x29) return 1;
  if (IID_IDXGIFactory1.Data4[2] != 0x25) return 1;
  if (IID_IDXGIFactory1.Data4[3] != 0x3c) return 1;
  if (IID_IDXGIFactory1.Data4[4] != 0x83) return 1;
  if (IID_IDXGIFactory1.Data4[5] != 0xd1) return 1;
  if (IID_IDXGIFactory1.Data4[6] != 0xb3) return 1;
  if (IID_IDXGIFactory1.Data4[7] != 0x87) return 1;
  if (IID_ID3D12Device.Data1 != 0x189819f1u || IID_ID3D12Device.Data2 != 0x1db6 || IID_ID3D12Device.Data3 != 0x4b57) return 1;
  if (IID_ID3D12Device.Data4[0] != 0xbe) return 1;
  if (IID_ID3D12Device.Data4[1] != 0x54) return 1;
  if (IID_ID3D12Device.Data4[2] != 0x18) return 1;
  if (IID_ID3D12Device.Data4[3] != 0x21) return 1;
  if (IID_ID3D12Device.Data4[4] != 0x33) return 1;
  if (IID_ID3D12Device.Data4[5] != 0x9b) return 1;
  if (IID_ID3D12Device.Data4[6] != 0x85) return 1;
  if (IID_ID3D12Device.Data4[7] != 0xf7) return 1;
  if (DEVPKEY_Device_DriverVersion.pid != 3 || DEVPKEY_Device_DriverProvider.pid != 9) return 1;
  if (DEVPKEY_Device_DriverVersion.fmtid.Data1 != 0xa8b865ddu) return 1;
  return 0;
}

int main(void) {return check_guids();}
