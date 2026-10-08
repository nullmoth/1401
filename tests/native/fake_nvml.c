#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API
#endif
/* Stand-in for nvml.dll with NVML API 12 signatures (nvml.h). Two RTX 3090s on different buses, plus a GTX 1660 whose
   core-count query is unsupported. nvmlDeviceGetUUID counts calls so a test can prove it is never used. */
#include <string.h>
#include <stdio.h>
typedef struct { char busIdLegacy[16]; unsigned domain, bus, device, pciDeviceId, pciSubSystemId; char busId[32]; } pci_t;
typedef struct { unsigned long long a, b, c; } mem_t;
static const struct { const char *name; unsigned bus, did, sub, cores; unsigned long long vram, bar1; } D[] = {
  {"NVIDIA GeForce RTX 3090", 0x01, 0x220410DE, 0x87AF1043, 10496, 25769803776ULL, 34359738368ULL},
  {"NVIDIA GeForce RTX 3090", 0x2a, 0x220410DE, 0x87AF1043, 10496, 25769803776ULL, 268435456ULL},
  {"NVIDIA GeForce GTX 1660", 0x05, 0x218410DE, 0x13261462, 0, 6442450944ULL, 268435456ULL}};
API int uuid_calls = 0;
API int nvmlInit_v2(void) { return 0; }
API int nvmlShutdown(void) { return 0; }
API int nvmlDeviceGetCount_v2(unsigned *n) { *n = 3; return 0; }
API int nvmlDeviceGetHandleByIndex_v2(unsigned i, void **h) { *h = (void *)(long)(i + 1); return 0; }
#define IX ((long)h - 1)
API int nvmlDeviceGetPciInfo_v3(void *h, pci_t *p) { memset(p, 0, sizeof *p); p->bus = D[IX].bus; p->pciDeviceId = D[IX].did;
  p->pciSubSystemId = D[IX].sub; snprintf(p->busId, 32, "00000000:%02X:00.0", D[IX].bus); return 0; }
API int nvmlDeviceGetName(void *h, char *n, unsigned len) { snprintf(n, len, "%s", D[IX].name); return 0; }
API int nvmlDeviceGetNumGpuCores(void *h, unsigned *c) { if (!D[IX].cores) return 3; *c = D[IX].cores; return 0; }
API int nvmlDeviceGetMaxPcieLinkGeneration(void *h, unsigned *g) { *g = 4; return 0; }
API int nvmlDeviceGetMaxPcieLinkWidth(void *h, unsigned *w) { *w = 16; return 0; }
API int nvmlDeviceGetMemoryInfo(void *h, mem_t *m) { m->a = D[IX].vram; m->b = m->c = 0; return 0; }
API int nvmlDeviceGetBAR1MemoryInfo(void *h, mem_t *m) { m->a = D[IX].bar1; m->b = m->c = 0; return 0; }
API int nvmlDeviceGetUUID(void *h, char *u, unsigned len) { uuid_calls++; snprintf(u, len, "GPU-00000000"); return 0; }
