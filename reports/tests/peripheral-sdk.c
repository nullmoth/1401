#define COBJMACROS
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
/* No <initguid.h>: this file only asserts struct/offset/constant layouts, and with Windows SDK 10.0.22621
   initguid.h makes windot11.h's DEFINE_NWF_GUID expand to "0x6cb9a43e+(ord)", which MSVC rejects as a pp-number.
   The GUID checks are the separate C++ file, which uses __uuidof and needs no object definitions. */
#include <setupapi.h>
#include <hidsdi.h>
#include <hidpi.h>
#include <wlanapi.h>
#include <audioclient.h>
#include <mmdeviceapi.h>
#include <mmreg.h>
#include <stddef.h>
#define A(c,m) _Static_assert(c,m)

A(sizeof(HIDP_CAPS)==64,"HIDP_CAPS size");
A(offsetof(HIDP_CAPS,Usage)==0,"HIDP_CAPS.Usage offset");
A(offsetof(HIDP_CAPS,UsagePage)==2,"HIDP_CAPS.UsagePage offset");
A(offsetof(HIDP_CAPS,InputReportByteLength)==4,"HIDP_CAPS.InputReportByteLength offset");
A(offsetof(HIDP_CAPS,OutputReportByteLength)==6,"HIDP_CAPS.OutputReportByteLength offset");
A(offsetof(HIDP_CAPS,FeatureReportByteLength)==8,"HIDP_CAPS.FeatureReportByteLength offset");
A(offsetof(HIDP_CAPS,Reserved)==10,"HIDP_CAPS.Reserved offset");
A(offsetof(HIDP_CAPS,NumberLinkCollectionNodes)==44,"HIDP_CAPS.NumberLinkCollectionNodes offset");
A(offsetof(HIDP_CAPS,NumberInputButtonCaps)==46,"HIDP_CAPS.NumberInputButtonCaps offset");
A(offsetof(HIDP_CAPS,NumberInputValueCaps)==48,"HIDP_CAPS.NumberInputValueCaps offset");
A(offsetof(HIDP_CAPS,NumberInputDataIndices)==50,"HIDP_CAPS.NumberInputDataIndices offset");
A(offsetof(HIDP_CAPS,NumberOutputButtonCaps)==52,"HIDP_CAPS.NumberOutputButtonCaps offset");
A(offsetof(HIDP_CAPS,NumberOutputValueCaps)==54,"HIDP_CAPS.NumberOutputValueCaps offset");
A(offsetof(HIDP_CAPS,NumberOutputDataIndices)==56,"HIDP_CAPS.NumberOutputDataIndices offset");
A(offsetof(HIDP_CAPS,NumberFeatureButtonCaps)==58,"HIDP_CAPS.NumberFeatureButtonCaps offset");
A(offsetof(HIDP_CAPS,NumberFeatureValueCaps)==60,"HIDP_CAPS.NumberFeatureValueCaps offset");
A(offsetof(HIDP_CAPS,NumberFeatureDataIndices)==62,"HIDP_CAPS.NumberFeatureDataIndices offset");
A(sizeof(HIDP_LINK_COLLECTION_NODE)==24,"HIDP_LINK_COLLECTION_NODE size");
A(offsetof(HIDP_LINK_COLLECTION_NODE,LinkUsage)==0,"HIDP_LINK_COLLECTION_NODE.LinkUsage offset");
A(offsetof(HIDP_LINK_COLLECTION_NODE,LinkUsagePage)==2,"HIDP_LINK_COLLECTION_NODE.LinkUsagePage offset");
A(offsetof(HIDP_LINK_COLLECTION_NODE,Parent)==4,"HIDP_LINK_COLLECTION_NODE.Parent offset");
A(offsetof(HIDP_LINK_COLLECTION_NODE,NumberOfChildren)==6,"HIDP_LINK_COLLECTION_NODE.NumberOfChildren offset");
A(offsetof(HIDP_LINK_COLLECTION_NODE,NextSibling)==8,"HIDP_LINK_COLLECTION_NODE.NextSibling offset");
A(offsetof(HIDP_LINK_COLLECTION_NODE,FirstChild)==10,"HIDP_LINK_COLLECTION_NODE.FirstChild offset");
A(offsetof(HIDP_LINK_COLLECTION_NODE,UserContext)==16,"HIDP_LINK_COLLECTION_NODE.UserContext offset");
A(sizeof(SP_DEVICE_INTERFACE_DATA)==32,"SP_DEVICE_INTERFACE_DATA size");
A(offsetof(SP_DEVICE_INTERFACE_DATA,cbSize)==0,"SP_DEVICE_INTERFACE_DATA.cbSize offset");
A(offsetof(SP_DEVICE_INTERFACE_DATA,InterfaceClassGuid)==4,"SP_DEVICE_INTERFACE_DATA.InterfaceClassGuid offset");
A(offsetof(SP_DEVICE_INTERFACE_DATA,Flags)==20,"SP_DEVICE_INTERFACE_DATA.Flags offset");
A(offsetof(SP_DEVICE_INTERFACE_DATA,Reserved)==24,"SP_DEVICE_INTERFACE_DATA.Reserved offset");
A(sizeof(WLAN_INTERFACE_INFO)==532,"WLAN_INTERFACE_INFO size");
A(offsetof(WLAN_INTERFACE_INFO,InterfaceGuid)==0,"WLAN_INTERFACE_INFO.InterfaceGuid offset");
A(offsetof(WLAN_INTERFACE_INFO,strInterfaceDescription)==16,"WLAN_INTERFACE_INFO.strInterfaceDescription offset");
A(offsetof(WLAN_INTERFACE_INFO,isState)==528,"WLAN_INTERFACE_INFO.isState offset");
A(sizeof(WLAN_INTERFACE_CAPABILITY)==276,"WLAN_INTERFACE_CAPABILITY size");
A(offsetof(WLAN_INTERFACE_CAPABILITY,interfaceType)==0,"WLAN_INTERFACE_CAPABILITY.interfaceType offset");
A(offsetof(WLAN_INTERFACE_CAPABILITY,bDot11DSupported)==4,"WLAN_INTERFACE_CAPABILITY.bDot11DSupported offset");
A(offsetof(WLAN_INTERFACE_CAPABILITY,dwMaxDesiredSsidListSize)==8,"WLAN_INTERFACE_CAPABILITY.dwMaxDesiredSsidListSize offset");
A(offsetof(WLAN_INTERFACE_CAPABILITY,dwMaxDesiredBssidListSize)==12,"WLAN_INTERFACE_CAPABILITY.dwMaxDesiredBssidListSize offset");
A(offsetof(WLAN_INTERFACE_CAPABILITY,dwNumberOfSupportedPhys)==16,"WLAN_INTERFACE_CAPABILITY.dwNumberOfSupportedPhys offset");
A(offsetof(WLAN_INTERFACE_CAPABILITY,dot11PhyTypes)==20,"WLAN_INTERFACE_CAPABILITY.dot11PhyTypes offset");
A(sizeof(WAVEFORMATEX)==18,"WAVEFORMATEX size");
A(offsetof(WAVEFORMATEX,wFormatTag)==0,"WAVEFORMATEX.wFormatTag offset");
A(offsetof(WAVEFORMATEX,nChannels)==2,"WAVEFORMATEX.nChannels offset");
A(offsetof(WAVEFORMATEX,nSamplesPerSec)==4,"WAVEFORMATEX.nSamplesPerSec offset");
A(offsetof(WAVEFORMATEX,nAvgBytesPerSec)==8,"WAVEFORMATEX.nAvgBytesPerSec offset");
A(offsetof(WAVEFORMATEX,nBlockAlign)==12,"WAVEFORMATEX.nBlockAlign offset");
A(offsetof(WAVEFORMATEX,wBitsPerSample)==14,"WAVEFORMATEX.wBitsPerSample offset");
A(offsetof(WAVEFORMATEX,cbSize)==16,"WAVEFORMATEX.cbSize offset");
A(sizeof(WAVEFORMATEXTENSIBLE)==40,"WAVEFORMATEXTENSIBLE size");
A(offsetof(WAVEFORMATEXTENSIBLE,Format)==0,"WAVEFORMATEXTENSIBLE.Format offset");
A(offsetof(WAVEFORMATEXTENSIBLE,Samples.wValidBitsPerSample)==18,"WAVEFORMATEXTENSIBLE.wValidBitsPerSample offset");
A(offsetof(WAVEFORMATEXTENSIBLE,dwChannelMask)==20,"WAVEFORMATEXTENSIBLE.dwChannelMask offset");
A(offsetof(WAVEFORMATEXTENSIBLE,SubFormat)==24,"WAVEFORMATEXTENSIBLE.SubFormat offset");
A(sizeof(BOOLEAN)==1,"BOOLEAN width; HID APIs do not return BOOL");
A(sizeof(WCHAR)==2,"Windows UTF16 width");
A(sizeof(DWORD)==4 && sizeof(ULONG)==4 && sizeof(NTSTATUS)==4,"SDK32 widths");
A(WLAN_MAX_PHY_INDEX==64,"bounded SDK PHY array");
A(HIDP_STATUS_SUCCESS==0x00110000,"HID success status");
A(offsetof(SP_DEVICE_INTERFACE_DETAIL_DATA_W,DevicePath)==4,"UTF16 path offset");
A(sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA_W)==8,"interface detail header cbSize");
A(COINIT_APARTMENTTHREADED==2,"STA first audio use");
A(DEVICE_STATE_ACTIVE==1 && eRender==0 && eCapture==1,"active endpoint flow");
A(CLSCTX_INPROC_SERVER==1,"system COM activation");
A(sizeof(BOOLEAN)==1,"HidD_GetPreparsedData ctypes return width");
A(sizeof(BOOLEAN)==1,"HidD_FreePreparsedData ctypes return width");
A(sizeof(NTSTATUS)==4,"HidP_GetCaps ctypes return width");
A(sizeof(NTSTATUS)==4,"HidP_GetLinkCollectionNodes ctypes return width");
A(sizeof(HDEVINFO)==8,"SetupDiGetClassDevsW ctypes return width");
A(sizeof(BOOL)==4,"SetupDiEnumDeviceInterfaces ctypes return width");
A(sizeof(BOOL)==4,"SetupDiGetDeviceInterfaceDetailW ctypes return width");
A(sizeof(BOOL)==4,"SetupDiDestroyDeviceInfoList ctypes return width");
A(sizeof(DWORD)==4,"CM_Get_Device_IDW ctypes return width");
A(sizeof(HANDLE)==8,"CreateFileW ctypes return width");
A(sizeof(BOOL)==4,"CloseHandle ctypes return width");
A(sizeof(DWORD)==4,"WlanOpenHandle ctypes return width");
A(sizeof(DWORD)==4,"WlanEnumInterfaces ctypes return width");
A(sizeof(DWORD)==4,"WlanGetInterfaceCapability ctypes return width");
A(sizeof(DWORD)==4,"WlanCloseHandle ctypes return width");
A(sizeof(HRESULT)==4,"CoInitializeEx ctypes return width");
A(sizeof(HRESULT)==4,"CoCreateInstance ctypes return width");
A(offsetof(IUnknownVtbl,Release)/sizeof(void*)==2,"Release slot");
A(offsetof(IMMDeviceEnumeratorVtbl,EnumAudioEndpoints)/sizeof(void*)==3,"EnumAudioEndpoints slot");
A(offsetof(IMMDeviceCollectionVtbl,GetCount)/sizeof(void*)==3,"GetCount slot");
A(offsetof(IMMDeviceCollectionVtbl,Item)/sizeof(void*)==4,"Item slot");
A(offsetof(IMMDeviceVtbl,Activate)/sizeof(void*)==3,"Activate slot");
A(offsetof(IAudioClientVtbl,GetMixFormat)/sizeof(void*)==8,"GetMixFormat slot");
A(_Generic(&HidD_GetPreparsedData,BOOLEAN (__stdcall *)(HANDLE,PHIDP_PREPARSED_DATA*):1,default:0),"HID preparsed signature");
A(_Generic(&HidP_GetCaps,NTSTATUS (__stdcall *)(PHIDP_PREPARSED_DATA,PHIDP_CAPS):1,default:0),"HID caps signature");
A(_Generic(&HidP_GetLinkCollectionNodes,NTSTATUS (__stdcall *)(PHIDP_LINK_COLLECTION_NODE,PULONG,PHIDP_PREPARSED_DATA):1,default:0),"HID nodes signature");
A(_Generic(&WlanGetInterfaceCapability,DWORD (WINAPI *)(HANDLE,const GUID*,PVOID,PWLAN_INTERFACE_CAPABILITY*):1,default:0),"WLAN capability signature");
int check_link_flags(void) { HIDP_LINK_COLLECTION_NODE node={0};node.CollectionType=0xA5;node.IsAlias=1;
return (*(const ULONG*)((const char*)&node+12)&0x1FF)!=0x1A5; }
int main(void) { return check_link_flags(); }
