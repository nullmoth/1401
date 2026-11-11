#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
int main(void) {
const GUID& g0 = __uuidof(MMDeviceEnumerator);
if (g0.Data1!=0xbcde0395u || g0.Data2!=0xe52f || g0.Data3!=0x467c) return 1;
if (g0.Data4[0]!=0x8e) return 1;
if (g0.Data4[1]!=0x3d) return 1;
if (g0.Data4[2]!=0xc4) return 1;
if (g0.Data4[3]!=0x57) return 1;
if (g0.Data4[4]!=0x92) return 1;
if (g0.Data4[5]!=0x91) return 1;
if (g0.Data4[6]!=0x69) return 1;
if (g0.Data4[7]!=0x2e) return 1;
const GUID& g1 = __uuidof(IMMDeviceEnumerator);
if (g1.Data1!=0xa95664d2u || g1.Data2!=0x9614 || g1.Data3!=0x4f35) return 1;
if (g1.Data4[0]!=0xa7) return 1;
if (g1.Data4[1]!=0x46) return 1;
if (g1.Data4[2]!=0xde) return 1;
if (g1.Data4[3]!=0x8d) return 1;
if (g1.Data4[4]!=0xb6) return 1;
if (g1.Data4[5]!=0x36) return 1;
if (g1.Data4[6]!=0x17) return 1;
if (g1.Data4[7]!=0xe6) return 1;
const GUID& g2 = __uuidof(IAudioClient);
if (g2.Data1!=0x1cb9ad4cu || g2.Data2!=0xdbfa || g2.Data3!=0x4c32) return 1;
if (g2.Data4[0]!=0xb1) return 1;
if (g2.Data4[1]!=0x78) return 1;
if (g2.Data4[2]!=0xc2) return 1;
if (g2.Data4[3]!=0xf5) return 1;
if (g2.Data4[4]!=0x68) return 1;
if (g2.Data4[5]!=0xa7) return 1;
if (g2.Data4[6]!=0x3) return 1;
if (g2.Data4[7]!=0xb2) return 1;
return 0; }
