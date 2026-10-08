#ifdef _WIN32
#define API __declspec(dllexport)
#else
#define API
#endif
/* Stand-in for the setupapi/cfgmgr32 exports fwres.pci_resources binds, with cfgmgr32.h's descriptor layouts. Handles
   are counted so a test can prove every log-conf and res-des handle is freed. Scenario switches are exported globals. */
#include <stdint.h>
#include <string.h>

typedef struct { uint32_t Data1; uint16_t Data2, Data3; uint8_t Data4[8]; } GUID;
typedef struct { uint32_t cbSize; GUID ClassGuid; uint32_t DevInst; size_t Reserved; } SP_DEVINFO_DATA;
typedef struct { uint32_t Count, Type; uint64_t Base, End; uint32_t Flags, Reserved; } MEM_DES;
typedef struct { uint32_t Count, Type; uint64_t Base, End; uint32_t DesFlags; } IO_DES;
typedef struct { uint32_t Count, Type, Flags, Alloc_Num; uint64_t Affinity; } IRQ_DES_64;

API int fk_live_handles = 0, fk_last_error = 0, fk_walk_err_at = -1, fk_wow64_at = -1, fk_huge_at = -1, fk_short_at = -1,
    fk_next_err_at = -1, fk_destroyed = 0, fk_enumerator_ok = 0;
API int fk_GetLastError(void) { return fk_last_error; }

/* three PCI functions: a GPU (memory_large + memory + irq), a NIC (io + memory), a bridge with no allocated config */
static const char *INST[] = {"PCI\\VEN_10DE&DEV_2204&SUBSYS_87AF1043&REV_A1\\4&1&0&0008",
                             "PCI\\VEN_10EC&DEV_8125&SUBSYS_7D251462&REV_05\\4&2&0&00E4",
                             "PCI\\VEN_8086&DEV_A70D&SUBSYS_7D251462&REV_01\\3&1&0&08"};
static const char *LOC[] = {"PCI bus 1, device 0, function 0", "PCI bus 4, device 0, function 0", "PCI bus 0, device 1, function 0"};
#define N 3
static uint16_t *put(uint16_t *w, const char *s) { while (*s) *w++ = (uint8_t)*s++; *w++ = 0; return w; }

API void *SetupDiGetClassDevsW(const GUID *g, const uint16_t *e, void *hwnd, uint32_t flags) {
  fk_enumerator_ok = e && e[0] == 'P' && e[1] == 'C' && e[2] == 'I' && e[3] == 0;
  return (flags == 6 && !g && fk_enumerator_ok) ? (void *)0x5678 : (void *)-1;
}
API int32_t SetupDiEnumDeviceInfo(void *h, uint32_t i, SP_DEVINFO_DATA *d) {
  if ((int)i == fk_walk_err_at) { fk_last_error = 5; return 0; }
  if (i >= N) { fk_last_error = 259; return 0; }
  d->DevInst = i + 1; return 1;
}
API int32_t SetupDiGetDeviceRegistryPropertyW(void *h, SP_DEVINFO_DATA *d, uint32_t prop, uint32_t *type, uint8_t *buf, uint32_t size, uint32_t *need) {
  uint16_t tmp[80]; uint16_t *e = put(tmp, LOC[d->DevInst - 1]); uint32_t bytes = (uint32_t)((uint8_t *)e - (uint8_t *)tmp);
  if (prop != 0xD) { fk_last_error = 13; return 0; }
  *type = 1; *need = bytes; if (size < bytes) { fk_last_error = 122; return 0; } memcpy(buf, tmp, bytes); return 1;
}
API int32_t SetupDiDestroyDeviceInfoList(void *h) { fk_destroyed++; return 1; }
API uint32_t CM_Get_Device_IDW(uint32_t inst, uint16_t *buf, uint32_t len, uint32_t f) { put(buf, INST[inst - 1]); return 0; }

/* handles: log conf = 0x1000 + dev, res des = 0x2000 + dev*16 + index */
API uint32_t CM_Get_First_Log_Conf(size_t *lc, uint32_t dev, uint32_t flags) {
  if (flags != 2) return 0x1F;
  if ((int)dev - 1 == fk_wow64_at) return 0x34;                  /* CR_CALL_NOT_IMPLEMENTED */
  if (dev == 3) return 0x0E;                                     /* CR_NO_MORE_LOG_CONF */
  *lc = 0x1000 + dev; fk_live_handles++; return 0;
}
static int count_for(int dev) { return dev == 1 ? 3 : 2; }
static int type_for(int dev, int k) { static const int T[2][3] = {{7, 1, 4}, {2, 1, 0}}; return T[dev - 1][k]; }
API uint32_t CM_Get_Next_Res_Des(size_t *out, size_t cur, uint32_t res, uint32_t *rid, uint32_t f) {
  int dev, k;
  if (res != 0 || f != 0 || !rid) return 0x1F;
  if (cur >= 0x2000) { dev = (int)((cur - 0x2000) / 16); k = (int)((cur - 0x2000) % 16) + 1; } else { dev = (int)(cur - 0x1000); k = 0; }
  if ((int)dev - 1 == fk_next_err_at && k == 1) return 0x06;    /* CR_INVALID_RES_DES */
  if (k >= count_for(dev)) return 0x0F;                          /* CR_NO_MORE_RES_DES */
  *out = 0x2000 + dev * 16 + k; *rid = (uint32_t)type_for(dev, k); fk_live_handles++; return 0;
}
static uint32_t size_of(int t) { return t == 2 ? sizeof(IO_DES) : t == 4 ? sizeof(IRQ_DES_64) : sizeof(MEM_DES); }
API uint32_t CM_Get_Res_Des_Data_Size(uint32_t *size, size_t rd, uint32_t f) {
  int dev = (int)((rd - 0x2000) / 16), k = (int)((rd - 0x2000) % 16);
  *size = size_of(type_for(dev, k)) + 16;                         /* header + one range record */
  if (dev - 1 == fk_huge_at) *size = 1 << 20;
  if (dev - 1 == fk_short_at) *size = 6;
  return 0;
}
API uint32_t CM_Get_Res_Des_Data(size_t rd, uint8_t *buf, uint32_t len, uint32_t f) {
  int dev = (int)((rd - 0x2000) / 16), k = (int)((rd - 0x2000) % 16), t = type_for(dev, k);
  uint8_t tmp[256]; memset(tmp, 0, sizeof tmp);
  if (t == 7) { MEM_DES m = {1, 7, 0x6000000000ULL, 0x67FFFFFFFFULL, 0, 0}; memcpy(tmp, &m, sizeof m); }
  if (t == 1) { MEM_DES m = {1, 1, dev == 1 ? 0xF6000000ULL : 0xFC500000ULL, dev == 1 ? 0xF6FFFFFFULL : 0xFC50FFFFULL, 0, 0}; memcpy(tmp, &m, sizeof m); }
  if (t == 4) { IRQ_DES_64 q = {1, 4, 0x0003 | (1u << 16), 4294967262u, 0xFFFF}; memcpy(tmp, &q, sizeof q); }
  if (t == 2) { IO_DES io = {1, 2, 0x3000, 0x30FF, 0}; memcpy(tmp, &io, sizeof io); }
  if (len > sizeof tmp) return 0x1F;
  memcpy(buf, tmp, len); return 0;
}
API uint32_t CM_Free_Res_Des_Handle(size_t rd) { if (rd < 0x2000) return 0x06; fk_live_handles--; return 0; }
API uint32_t CM_Free_Log_Conf_Handle(size_t lc) { if (lc < 0x1000 || lc >= 0x2000) return 0x06; fk_live_handles--; return 0; }
