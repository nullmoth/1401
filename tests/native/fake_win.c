#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API
#endif
/* Stand-in for the Windows exports devicemap.py binds (dxgi, d3d12, user32, setupapi, cfgmgr32, powrprof), with the same
   C signatures and fake COM objects whose vtable slots match dxgi.h / d3d12.h. Scenario switches and counters are
   exported globals the tests set and read. Built as one shared library and loaded once per DLL name. */
#include <stdint.h>
#include <string.h>
#include <stdlib.h>

typedef int32_t HRESULT; typedef int32_t BOOL; typedef uint32_t DWORD;
typedef struct { uint32_t Data1; uint16_t Data2, Data3; uint8_t Data4[8]; } GUID;
typedef struct { uint32_t LowPart; int32_t HighPart; } LUID;
typedef struct { uint16_t Description[128]; uint32_t VendorId, DeviceId, SubSysId, Revision; size_t DedicatedVideoMemory,
  DedicatedSystemMemory, SharedSystemMemory; LUID AdapterLuid; uint32_t Flags; } DXGI_ADAPTER_DESC1;
typedef struct { LUID adapterId; uint32_t id, modeInfoIdx, statusFlags; } SRC;
typedef struct { LUID adapterId; uint32_t id, modeInfoIdx; int32_t outputTechnology; uint32_t rotation, scaling, rn, rd, scan;
  int32_t targetAvailable; uint32_t statusFlags; } TGT;
typedef struct { SRC s; TGT t; uint32_t flags; } PATH;
typedef struct { DWORD cbSize; GUID ClassGuid; DWORD DevInst; size_t Reserved; } SP_DEVINFO_DATA;
typedef struct { GUID fmtid; uint32_t pid; } DEVPROPKEY;

/* scenario switches */
API int fk_desc_fail_at = -1, fk_null_adapter_at = -1, fk_d3d12_fail_at = -1, fk_qdc_changes = 0, fk_qdc_overreport = 0;
API int fk_setup_err_at = -1, fk_prop_mode = 0, fk_role = 2, fk_factory_fail = 0;
/* observations */
API uint32_t fk_refresh_num = 60000, fk_refresh_den = 1001;
API int fk_live_objects = 0, fk_releases = 0, fk_last_error = 0, fk_destroyed = 0, fk_qdc_calls = 0, fk_max_prop_buf = 0;
API int fk_GetLastError(void) { return fk_last_error; }

typedef struct { void **vtbl; int refs; int idx; } OBJ;
static OBJ *make(void **vtbl, int idx) { OBJ *o = calloc(1, sizeof *o); o->vtbl = vtbl; o->refs = 1; o->idx = idx; fk_live_objects++; return o; }
static uint32_t Release(OBJ *o) { fk_releases++; if (--o->refs == 0) { fk_live_objects--; free(o); return 0; } return o->refs; }

static const struct { const char *name; uint32_t ven, dev, sub; int32_t luid; int tier; } AD[] = {
  {"NVIDIA GeForce RTX 3090", 0x10DE, 0x2204, 0x87AF1043, 0x1001, 11},
  {"NVIDIA GeForce RTX 3090", 0x10DE, 0x2204, 0x87AF1043, 0x2002, 11},
  {"Intel(R) UHD Graphics 770", 0x8086, 0x4680, 0x7D251462, 0x4004, 0}};
#define NAD 3

static HRESULT GetDesc1(OBJ *self, DXGI_ADAPTER_DESC1 *d) {
  if (self->idx == fk_desc_fail_at) return (HRESULT)0x887A0001;            /* DXGI_ERROR_INVALID_CALL */
  memset(d, 0, sizeof *d);
  for (int i = 0; AD[self->idx].name[i] && i < 127; i++) d->Description[i] = (uint16_t)AD[self->idx].name[i];
  d->VendorId = AD[self->idx].ven; d->DeviceId = AD[self->idx].dev; d->SubSysId = AD[self->idx].sub; d->Revision = 0xA1;
  d->DedicatedVideoMemory = (size_t)24 << 30; d->AdapterLuid.LowPart = (uint32_t)AD[self->idx].luid; return 0;
}
static HRESULT CheckFeatureSupport(OBJ *self, int32_t feature, void *data, uint32_t size) {
  if (feature != 27 || size != 12) return (HRESULT)0x80070057;            /* E_INVALIDARG: wrong feature or size */
  int32_t *o5 = data; o5[0] = 1; o5[1] = 1; o5[2] = AD[self->idx].tier; return 0;
}
static void *adapter_vtbl[11], *device_vtbl[14], *factory_vtbl[14];
static HRESULT EnumAdapters1(OBJ *self, uint32_t i, void **out) {
  *out = NULL;
  if (i >= NAD) return (HRESULT)0x887A0002;                                /* DXGI_ERROR_NOT_FOUND */
  if ((int)i == fk_null_adapter_at) return 0;                             /* success with no interface: must not count */
  *out = make(adapter_vtbl, (int)i); return 0;
}
API HRESULT CreateDXGIFactory1(const GUID *iid, void **out) {
  adapter_vtbl[2] = (void *)Release; adapter_vtbl[10] = (void *)GetDesc1;
  device_vtbl[2] = (void *)Release; device_vtbl[13] = (void *)CheckFeatureSupport;
  factory_vtbl[2] = (void *)Release; factory_vtbl[12] = (void *)EnumAdapters1;
  *out = NULL;
  if (fk_factory_fail || iid->Data1 != 0x770AAE78) return (HRESULT)0x80004002;  /* E_NOINTERFACE */
  *out = make(factory_vtbl, -1); return 0;
}
API HRESULT D3D12CreateDevice(OBJ *adapter, int32_t level, const GUID *iid, void **out) {
  *out = NULL;
  if (!adapter || level != 0xB000 || iid->Data1 != 0x189819F1) return (HRESULT)0x80070057;
  if (adapter->idx == fk_d3d12_fail_at) return (HRESULT)0x887A0004;      /* DXGI_ERROR_UNSUPPORTED */
  *out = make(device_vtbl, adapter->idx); return 0;
}

/* user32: two active paths; fk_qdc_changes makes the query report a topology change that many times */
API int32_t GetDisplayConfigBufferSizes(uint32_t flags, uint32_t *np, uint32_t *nm) {
  if (flags != 2) return 87; *np = 2; *nm = 4; return 0;
}
API int32_t QueryDisplayConfig(uint32_t flags, uint32_t *np, PATH *paths, uint32_t *nm, void *modes, void *topo) {
  fk_qdc_calls++;
  if (flags != 2 || topo) return 87;
  if (fk_qdc_changes > 0) { fk_qdc_changes--; return 122; }
  if (*np < 2) return 122;
  memset(paths, 0, sizeof(PATH) * 2);
  paths[0].s.adapterId.LowPart = 0x4004; paths[0].t.outputTechnology = (int32_t)0x80000000; paths[0].t.targetAvailable = 1;
  paths[1].s.adapterId.LowPart = 0x2002; paths[1].t.outputTechnology = 5; paths[1].t.targetAvailable = 1;
  for (int i = 0; i < 2; i++) { paths[i].t.adapterId = paths[i].s.adapterId; paths[i].flags = 1; paths[i].t.rn = fk_refresh_num; paths[i].t.rd = fk_refresh_den; }
  *np = fk_qdc_overreport ? 9 : 2; *nm = 4; return 0;
}

/* setupapi + cfgmgr32: six devices */
static const struct { const char *inst, *parent, *hw, *desc, *cls; } DV[] = {
  {"PCI\\VEN_10DE&DEV_2204&SUBSYS_87AF1043&REV_A1\\4&1&0&0008", "PCI\\VEN_8086&DEV_A70D\\3&1&0&08",
   "PCI\\VEN_10DE&DEV_2204&SUBSYS_87AF1043&REV_A1", "NVIDIA GeForce RTX 3090", "Display"},
  {"PCI\\VEN_10DE&DEV_2204&SUBSYS_87AF1043&REV_A1\\4&2&0&0009", "PCI\\VEN_8086&DEV_A70D\\3&1&0&08",
   "PCI\\VEN_10DE&DEV_2204&SUBSYS_87AF1043&REV_A1", "NVIDIA GeForce RTX 3090", "Display"},
  {"HDAUDIO\\FUNC_01&VEN_10EC&DEV_0897&SUBSYS_14627D25&REV_1001\\4&5&0&0001", "PCI\\VEN_8086&DEV_7AD0\\3&1&0&FB",
   "HDAUDIO\\FUNC_01&VEN_10EC&DEV_0897&SUBSYS_14627D25&REV_1001", "Realtek(R) Audio", "MEDIA"},
  {"BTHENUM\\{0000110B-0000-1000-8000-00805F9B34FB}_VID&0001004C_PID&2002\\7&9&0&D8A35C1B2E4F_C00000000", "BTH\\MS_BTHBRB\\6&1",
   "BTHENUM\\{0000110B-0000-1000-8000-00805F9B34FB}_VID&0001004C_PID&2002", "FixtureOwner's AirPods", "AudioEndpointParent"},
  {"HID\\{00001124-0000-1000-8000-00805F9B34FB}_VID&0002046D_PID&B023\\8&1&0&0000",
   "BTHENUM\\{0000110B-0000-1000-8000-00805F9B34FB}_VID&0001004C_PID&2002\\7&9&0&D8A35C1B2E4F_C00000000",
   "HID\\{00001124-0000-1000-8000-00805F9B34FB}_VID&0002046D_PID&B023", "FixtureOwner's Keyboard fe80::1c2b:3cff:fe4d:5e6f", "Keyboard"},
  {"USB\\VID_0781&PID_5581\\4C530001234567", "USB\\ROOT_HUB30\\4&1&0&0", "USB\\VID_0781&PID_5581&REV_0100",
   "SanDisk at 2600:1700:abcd:1234::5", "USB"}};
#define NDV 6
static uint16_t *put(uint16_t *w, const char *s) { while (*s) *w++ = (uint8_t)*s++; *w++ = 0; return w; }

API void *SetupDiGetClassDevsW(const GUID *g, const uint16_t *e, void *hwnd, DWORD flags) { return (flags == 6 && !g && !e) ? (void *)0x1234 : (void *)-1; }
API BOOL SetupDiEnumDeviceInfo(void *h, DWORD i, SP_DEVINFO_DATA *d) {
  if (d->cbSize != sizeof(SP_DEVINFO_DATA)) { fk_last_error = 1784; return 0; }   /* ERROR_INVALID_USER_BUFFER */
  if ((int)i == fk_setup_err_at) { fk_last_error = 5; return 0; }               /* ERROR_ACCESS_DENIED */
  if (i >= NDV) { fk_last_error = 259; return 0; }                              /* ERROR_NO_MORE_ITEMS */
  d->DevInst = i + 1; return 1;
}
API BOOL SetupDiGetDeviceRegistryPropertyW(void *h, SP_DEVINFO_DATA *d, DWORD prop, DWORD *type, uint8_t *buf, DWORD size, DWORD *need) {
  int i = (int)d->DevInst - 1; uint16_t tmp[600]; uint16_t *e = tmp; DWORD t = 1;
  if (size > (DWORD)fk_max_prop_buf) fk_max_prop_buf = (int)size;
  if (prop == 1) { e = put(e, DV[i].hw); *e++ = 0; t = 7; }
  else if (prop == 0) { e = put(e, DV[i].desc); }
  else if (prop == 7) { e = put(e, DV[i].cls); }
  else { fk_last_error = 13; return 0; }                                         /* ERROR_INVALID_DATA: not present */
  DWORD bytes = (DWORD)((uint8_t *)e - (uint8_t *)tmp);
  if (i == 0 && prop == 0) {
    if (fk_prop_mode == 1) bytes -= 1;                                           /* odd length, no terminator */
    if (fk_prop_mode == 2) bytes = 100000;                                       /* claims a huge value */
    if (fk_prop_mode == 3) t = 4;                                                /* REG_DWORD */
  }
  if (type) *type = t;
  if (need) *need = bytes;
  if (!buf || size < bytes) { fk_last_error = 122; return 0; }
  memcpy(buf, tmp, bytes); return 1;
}
API BOOL SetupDiGetDevicePropertyW(void *h, SP_DEVINFO_DATA *d, const DEVPROPKEY *k, DWORD *type, uint8_t *buf, DWORD size, DWORD *need, DWORD flags) {
  uint16_t tmp[64]; uint16_t *e = put(tmp, k->pid == 3 ? "31.0.15.5222" : "NVIDIA");
  if ((int)d->DevInst - 1 >= 2) { fk_last_error = 1168; return 0; }             /* ERROR_NOT_FOUND */
  DWORD bytes = (DWORD)((uint8_t *)e - (uint8_t *)tmp); *type = 0x12; if (need) *need = bytes;
  if (size < bytes) { fk_last_error = 122; return 0; }
  memcpy(buf, tmp, bytes); return 1;
}
API BOOL SetupDiDestroyDeviceInfoList(void *h) { fk_destroyed++; return h == (void *)0x1234; }
static int inst_of(const char *s) { for (int i = 0; i < NDV; i++) if (!strcmp(DV[i].inst, s)) return i + 1; return 0; }
static const char *PARENTS[] = {"PCI\\VEN_8086&DEV_A70D\\3&1&0&08", "PCI\\VEN_8086&DEV_7AD0\\3&1&0&FB", "BTH\\MS_BTHBRB\\6&1", "USB\\ROOT_HUB30\\4&1&0&0"};
API uint32_t CM_Get_Device_IDW(DWORD inst, uint16_t *buf, uint32_t len, uint32_t flags) {
  const char *s = inst >= 1 && inst <= NDV ? DV[inst - 1].inst : (inst >= 100 && inst < 104 ? PARENTS[inst - 100] : NULL);
  if (!s || strlen(s) + 1 > len) return 0x1A;                                   /* CR_BUFFER_SMALL / no such */
  put(buf, s); return 0;
}
API uint32_t CM_Get_Parent(DWORD *parent, DWORD inst, uint32_t flags) {
  const char *p = DV[inst - 1].parent; int k = inst_of(p);
  if (k) { *parent = (DWORD)k; return 0; }
  for (int j = 0; j < 4; j++) if (!strcmp(PARENTS[j], p)) { *parent = 100 + j; return 0; }
  return 0x0D;
}
API uint32_t CM_Get_DevNode_Status(uint32_t *st, uint32_t *pr, DWORD inst, uint32_t flags) {
  *st = 0x8; *pr = 0; if (inst == 2) { *st = 0x400; *pr = 43; } return 0;
}
API int32_t PowerDeterminePlatformRoleEx(uint32_t version) { return version == 2 ? fk_role : -1; }
