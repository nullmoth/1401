#ifdef _WIN32
#define API __declspec(dllexport)
#else
#define API
#endif
/* Stand-in for nvml.dll (nvml.h, NVML_API_VERSION 12) for fwres.nvidia_detail. Device 0: a MIG-enabled data-centre GPU
   (Ampere); device 1: an RTX 3090 whose virtualization query is NOT_SUPPORTED. Built twice: full, and with -DOLD to
   drop exports an older driver lacks. nvmlDeviceGetUUID only counts calls: it must never be called. */
#include <stdio.h>
#include <string.h>
typedef struct { char busIdLegacy[16]; unsigned domain, bus, device, pciDeviceId, pciSubSystemId; char busId[32]; } pci_t;
API int uuid_calls = 0, init_calls = 0, shutdown_calls = 0;
static const struct { unsigned bus, did, sub, arch, cg, cw, mg, mw; int cm, vm; unsigned mig, maxmig; const char *vbios; } D[] = {
  {0x07, 0x20B510DE, 0x153310DE, 7, 4, 16, 4, 16, 0, 0, 1, 7, "92.00.25.00.08"},
  {0x01, 0x220410DE, 0x87AF1043, 7, 3, 8, 4, 16, 0, -1, 0, 0, "94.02.42.00.A9"}};
API int nvmlInit_v2(void) { init_calls++; return 0; }
API int nvmlShutdown(void) { shutdown_calls++; return 0; }
API int nvmlSystemGetDriverVersion(char *v, unsigned len) { snprintf(v, len, "581.42"); return 0; }
API int nvmlSystemGetCudaDriverVersion_v2(int *v) { *v = 13000; return 0; }
API int nvmlDeviceGetCount_v2(unsigned *n) { *n = 2; return 0; }
API int nvmlDeviceGetHandleByIndex_v2(unsigned i, void **h) { *h = (void *)(long)(i + 1); return 0; }
#define IX ((long)h - 1)
API int nvmlDeviceGetPciInfo_v3(void *h, pci_t *p) { memset(p, 0, sizeof *p); p->bus = D[IX].bus; p->pciDeviceId = D[IX].did;
  p->pciSubSystemId = D[IX].sub; snprintf(p->busId, 32, "00000000:%02X:00.0", D[IX].bus); return 0; }
API int nvmlDeviceGetVbiosVersion(void *h, char *v, unsigned len) { snprintf(v, len, "%s", D[IX].vbios); return 0; }
API int nvmlDeviceGetCurrPcieLinkGeneration(void *h, unsigned *g) { *g = D[IX].cg; return 0; }
API int nvmlDeviceGetCurrPcieLinkWidth(void *h, unsigned *w) { *w = D[IX].cw; return 0; }
API int nvmlDeviceGetMaxPcieLinkGeneration(void *h, unsigned *g) { *g = D[IX].mg; return 0; }
API int nvmlDeviceGetMaxPcieLinkWidth(void *h, unsigned *w) { *w = D[IX].mw; return 0; }
API int nvmlDeviceGetComputeMode(void *h, int *m) { *m = D[IX].cm; return 0; }
API int nvmlDeviceGetVirtualizationMode(void *h, int *m) { if (D[IX].vm < 0) return 3; *m = D[IX].vm; return 0; }
API int nvmlDeviceGetUUID(void *h, char *u, unsigned len) { uuid_calls++; snprintf(u, len, "GPU-12345678"); return 0; }
#ifndef OLD
API int nvmlDeviceGetArchitecture(void *h, unsigned *a) { *a = D[IX].arch; return 0; }
API int nvmlDeviceGetMigMode(void *h, unsigned *c, unsigned *p) { if (!D[IX].maxmig) return 3; *c = D[IX].mig; *p = D[IX].mig; return 0; }
API int nvmlDeviceGetMaxMigDeviceCount(void *h, unsigned *n) { if (!D[IX].maxmig) return 3; *n = D[IX].maxmig; return 0; }
#endif
