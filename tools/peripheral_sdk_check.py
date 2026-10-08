#!/usr/bin/env python3
"""Generate SDK layout assertions and CPU-only constant checks; no native probes run."""
import ctypes
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from p1401 import peripheral_caps as p
if '--guid-cpp' in sys.argv:
    # MIDL declares these identifiers with __declspec(uuid); C libraries need not export IID objects.
    lines = ['#include <windows.h>', '#include <mmdeviceapi.h>', '#include <audioclient.h>', 'int main(void) {']
    for index, (name, value) in enumerate([('MMDeviceEnumerator', p.CLSID_MMDeviceEnumerator),
            ('IMMDeviceEnumerator', p.IID_IMMDeviceEnumerator), ('IAudioClient', p.IID_IAudioClient)]):
        first = value[0] ^ (1 if '--negative-audio-guid' in sys.argv and index == 0 else 0)
        lines.append('const GUID& g%d = __uuidof(%s);' % (index, name))
        lines.append(f'if (g{index}.Data1!={first:#x}u || g{index}.Data2!={value[1]:#x} || g{index}.Data3!={value[2]:#x}) return 1;')
        lines.extend(f'if (g{index}.Data4[{i}]!={byte:#x}) return 1;' for i, byte in enumerate(value[3:]))
    lines.append('return 0; }')
    Path(sys.argv[1]).write_text('\n'.join(lines)+'\n')
    sys.exit(0)
STRUCTS = {name: getattr(p, name) for name in ('HIDP_CAPS', 'HIDP_LINK_COLLECTION_NODE', 'SP_DEVICE_INTERFACE_DATA',
          'WLAN_INTERFACE_INFO', 'WLAN_INTERFACE_CAPABILITY', 'WAVEFORMATEX', 'WAVEFORMATEXTENSIBLE')}
rename = {'WAVEFORMATEXTENSIBLE.wValidBitsPerSample': 'Samples.wValidBitsPerSample'}
head = '''#define COBJMACROS
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <initguid.h>
#include <setupapi.h>
#include <hidsdi.h>
#include <hidpi.h>
#include <wlanapi.h>
#include <audioclient.h>
#include <mmdeviceapi.h>
#include <mmreg.h>
#include <stddef.h>
#define A(c,m) _Static_assert(c,m)
'''
lines = [head]
for name, structure in STRUCTS.items():
    lines.append(f'A(sizeof({name})=={ctypes.sizeof(structure)},"{name} size");')
    for field, *_ in structure._fields_:
        if name == 'HIDP_LINK_COLLECTION_NODE' and field == 'Flags':
            continue
        cfield = rename.get(name + '.' + field, field)
        lines.append(f'A(offsetof({name},{cfield})=={getattr(structure,field).offset},"{name}.{field} offset");')
lines += [
    'A(sizeof(BOOLEAN)==1,"BOOLEAN width; HID APIs do not return BOOL");',
    'A(sizeof(WCHAR)==2,"Windows UTF16 width");',
    'A(sizeof(DWORD)==4 && sizeof(ULONG)==4 && sizeof(NTSTATUS)==4,"SDK32 widths");',
    'A(WLAN_MAX_PHY_INDEX==64,"bounded SDK PHY array");',
    'A(HIDP_STATUS_SUCCESS==0x00110000,"HID success status");',
    'A(offsetof(SP_DEVICE_INTERFACE_DETAIL_DATA_W,DevicePath)==4,"UTF16 path offset");',
    f'A(sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA_W)=={8 if ctypes.sizeof(ctypes.c_void_p)==8 else 6},"interface detail header cbSize");',
    'A(COINIT_APARTMENTTHREADED==2,"STA first audio use");',
    'A(DEVICE_STATE_ACTIVE==1 && eRender==0 && eCapture==1,"active endpoint flow");',
    'A(CLSCTX_INPROC_SERVER==1,"system COM activation");',
]
return_types = {'HidD_GetPreparsedData':'BOOLEAN','HidD_FreePreparsedData':'BOOLEAN',
                'HidP_GetCaps':'NTSTATUS','HidP_GetLinkCollectionNodes':'NTSTATUS',
                'SetupDiGetClassDevsW':'HDEVINFO','SetupDiEnumDeviceInterfaces':'BOOL',
                'SetupDiGetDeviceInterfaceDetailW':'BOOL','SetupDiDestroyDeviceInfoList':'BOOL',
                'CM_Get_Device_IDW':'DWORD','CreateFileW':'HANDLE','CloseHandle':'BOOL',
                'WlanOpenHandle':'DWORD','WlanEnumInterfaces':'DWORD','WlanGetInterfaceCapability':'DWORD',
                'WlanCloseHandle':'DWORD','CoInitializeEx':'HRESULT','CoCreateInstance':'HRESULT'}
for _, name, result, _ in p.EXPORTS:
    if name in return_types:
        size = ctypes.sizeof(result)
        if '--negative-boolean' in sys.argv and name == 'HidD_GetPreparsedData':
            size = 4
        lines.append(f'A(sizeof({return_types[name]})=={size},"{name} ctypes return width");')
interfaces = {'EnumAudioEndpoints':'IMMDeviceEnumeratorVtbl', 'GetCount':'IMMDeviceCollectionVtbl',
              'Item':'IMMDeviceCollectionVtbl','Activate':'IMMDeviceVtbl','GetMixFormat':'IAudioClientVtbl','Release':'IUnknownVtbl'}
for method, (slot, _, _) in p.COM.items():
    lines.append(f'A(offsetof({interfaces[method]},{method})/sizeof(void*)=={slot},"{method} slot");')
lines += [
    'A(_Generic(&HidD_GetPreparsedData,BOOLEAN (__stdcall *)(HANDLE,PHIDP_PREPARSED_DATA*):1,default:0),"HID preparsed signature");',
    'A(_Generic(&HidP_GetCaps,NTSTATUS (__stdcall *)(PHIDP_PREPARSED_DATA,PHIDP_CAPS):1,default:0),"HID caps signature");',
    'A(_Generic(&HidP_GetLinkCollectionNodes,NTSTATUS (__stdcall *)(PHIDP_LINK_COLLECTION_NODE,PULONG,PHIDP_PREPARSED_DATA):1,default:0),"HID nodes signature");',
    'A(_Generic(&WlanGetInterfaceCapability,DWORD (WINAPI *)(HANDLE,const GUID*,PVOID,PWLAN_INTERFACE_CAPABILITY*):1,default:0),"WLAN capability signature");',
    'int check_link_flags(void) { HIDP_LINK_COLLECTION_NODE node={0};node.CollectionType=0xA5;node.IsAlias=1;',
    'return (*(const ULONG*)((const char*)&node+12)&0x1FF)!=0x1A5; }',
]
lines.append('int main(void) { return check_link_flags(); }')
target = Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).with_name('peripheral_sdk_check.c')
target.write_text('\n'.join(lines)+'\n')
print('Compile-only Windows SDK assertions written; actual SDK compiler result remains pending.')
