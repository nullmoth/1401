#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API
#endif
/* Stand-in for nvcuda.dll (cuda.h 12.9 attribute numbers). Same three devices as fake_nvml.c. */
static const int BUS[] = {0x01, 0x2a, 0x05}, SM[] = {82, 82, 22}, CCMAJ[] = {8, 8, 7}, CCMIN[] = {6, 6, 5};
API int cuInit(unsigned f) { return 0; }
API int cuDeviceGetCount(int *n) { *n = 3; return 0; }
API int cuDeviceGet(int *d, int i) { *d = i; return 0; }
API int cuDeviceGetAttribute(int *v, int a, int d) {
  switch (a) { case 1: *v = 1024; return 0; case 8: *v = 49152; return 0; case 10: *v = 32; return 0; case 12: *v = 65536; return 0;
    case 16: *v = SM[d]; return 0; case 18: *v = 0; return 0; case 33: *v = BUS[d]; return 0; case 34: *v = 0; return 0;
    case 37: *v = d == 2 ? 192 : 384; return 0; case 38: *v = d == 2 ? 1572864 : 6291456; return 0; case 39: *v = d == 2 ? 1024 : 1536; return 0;
    case 50: *v = 0; return 0; case 75: *v = CCMAJ[d]; return 0; case 76: *v = CCMIN[d]; return 0;
    case 81: *v = d == 2 ? 65536 : 102400; return 0; case 82: *v = 65536; return 0; case 97: *v = d == 2 ? 65536 : 101376; return 0;
    case 106: *v = d == 2 ? 16 : 16; return 0; }
  return 1; }
