#!/usr/bin/env python3
"""Typed native-call fixtures only; no system libraries, HID reports, audio streams or radio operations."""
import ctypes as C
import importlib.util
import json
from pathlib import Path
import sys
import time
import types
import unittest

ROOT = Path(__file__).resolve().parent
from p1401 import devicemap as d, peripheral_caps as p


class Fixture:
    instances=[]
    def __init__(self, **options):
        self.instances.append(self);self.callback_errors=[]
        self.options = options; self.error = 0; self.calls = {}; self.keep = []; self.live = {}; self.free_count = 0
        self.caps = p.HIDP_CAPS(Usage=5, UsagePage=13, InputReportByteLength=64, NumberLinkCollectionNodes=2,
                               NumberInputButtonCaps=1, NumberInputValueCaps=4)
        self.nodes = (p.HIDP_LINK_COLLECTION_NODE*2)()
        self.nodes[0].LinkUsagePage=13; self.nodes[0].LinkUsage=5; self.nodes[0].NumberOfChildren=1; self.nodes[0].FirstChild=1; self.nodes[0].Flags=1
        self.nodes[1].LinkUsagePage=13; self.nodes[1].LinkUsage=34
        self.path='\\\\?\\HID#VID_1234&PID_5678#PRIVATE_INSTANCE'.encode('utf-16-le')+b'\0\0'
        self.wlan_list=C.create_string_buffer(8+C.sizeof(p.WLAN_INTERFACE_INFO))
        C.cast(self.wlan_list,C.POINTER(p.U32))[0]=options.get('wifi_count',1)
        info=p.WLAN_INTERFACE_INFO.from_buffer(self.wlan_list,8);info.InterfaceGuid.Data1=0x12345678
        for i,c in enumerate('PRIVATE_RENAMED_RADIO'):info.strInterfaceDescription[i]=ord(c)
        self.wlan_cap=p.WLAN_INTERFACE_CAPABILITY(interfaceType=2,bDot11DSupported=1,dwNumberOfSupportedPhys=3)
        self.wlan_cap.dot11PhyTypes[0]=7;self.wlan_cap.dot11PhyTypes[1]=8;self.wlan_cap.dot11PhyTypes[2]=9
        self.wave=p.WAVEFORMATEXTENSIBLE();self.wave.Format=p.WAVEFORMATEX(0xfffe,2,48000,384000,8,32,22)
        self.wave.wValidBitsPerSample=32;self.wave.dwChannelMask=3
        self.wave.SubFormat=d.guid(3,0,0x10,0x80,0,0,0xaa,0,0x38,0x9b,0x71)
        self._build_com()
        libraries={}
        for dll,name,result,args in p.EXPORTS:
            lib=libraries.setdefault(dll,types.SimpleNamespace())
            fn=d.FUNCTYPE(result,*args)(self.safe(name,self._export(name),result));setattr(lib,name,fn);self.keep.append(fn)
        self.native=p.Native({'hid','setupapi','cfgmgr32','kernel32','wlanapi','ole32'},libraries=libraries,last_error=lambda:self.error)

    def called(self,name):self.calls[name]=self.calls.get(name,0)+1
    def safe(self,name,fn,result):
        def wrapped(*args):
            try:return fn(*args)
            except BaseException as error:
                self.callback_errors.append((name,type(error).__name__,str(error)))
                return None if result is None else -1 if result==C.c_int32 else 0
        return wrapped
    def _export(self,name):
        def call(*args):
            self.called(name)
            if name=='HidD_GetHidGuid':args[0][0]=d.guid(0x4d1e55b2,0xf16f,0x11cf,0x88,0xcb,0,0x11,0x11,0,0,0x30)
            elif name=='HidD_GetPreparsedData':
                if self.options.get('preparsed_fail'):return 0
                args[1][0]=0x1000;return 1
            elif name=='HidD_FreePreparsedData':assert args[0]==0x1000;return 1
            elif name=='HidP_GetCaps':
                if self.options.get('caps_fail'):return C.c_int32(0xc0110001).value
                C.memmove(args[1],C.byref(self.caps),C.sizeof(self.caps));return p.HIDP_STATUS_SUCCESS
            elif name=='HidP_GetLinkCollectionNodes':
                if self.options.get('nodes_fail'):return C.c_int32(0xc0110001).value
                C.memmove(args[0],self.nodes,C.sizeof(self.nodes));args[1][0]=self.options.get('returned_nodes',2);return p.HIDP_STATUS_SUCCESS
            elif name=='SetupDiGetClassDevsW':assert args[3]==0x12;return 0x6000
            elif name=='SetupDiEnumDeviceInterfaces':
                if args[3]:self.error=259;return 0
                assert args[4][0].cbSize==C.sizeof(p.SP_DEVICE_INTERFACE_DATA);return 1
            elif name=='SetupDiGetDeviceInterfaceDetailW':
                required=4+len(self.path)
                if not args[2]:args[4][0]=self.options.get('detail_size',required);self.error=122;return 0
                if self.options.get('detail_fail'):return 0
                assert C.cast(args[2],C.POINTER(p.U32))[0]==(8 if C.sizeof(C.c_void_p)==8 else 6)
                assert args[3]>=required;C.memmove(args[2]+4,self.path,len(self.path));args[4][0]=required;args[5][0].DevInst=7;return 1
            elif name=='SetupDiDestroyDeviceInfoList':assert args[0]==0x6000;return 1
            elif name=='CM_Get_Device_IDW':
                text=('HID\\VID_1234&PID_5678\\PRIVATE_INSTANCE'+'\0').encode('utf-16-le')
                C.memmove(args[1],text,len(text))
                return 0
            elif name=='CreateFileW':assert args[1]==0 and args[2]==3 and args[4]==3 and args[5]==0;return p.INVALID_HANDLE if self.options.get('open_fail') else 0x7000
            elif name=='CloseHandle':assert args[0]==0x7000;return 1
            elif name=='WlanOpenHandle':
                if self.options.get('wifi_open_fail'):return 5
                args[2][0]=2;args[3][0]=0x8000;return 0
            elif name=='WlanEnumInterfaces':
                if self.options.get('wifi_enum_fail'):return 5
                args[2][0]=C.addressof(self.wlan_list);return 0
            elif name=='WlanGetInterfaceCapability':
                assert args[1][0].Data1==0x12345678 and args[2] is None
                if self.options.get('wifi_caps_fail'):return 5
                args[3][0]=C.addressof(self.wlan_cap);return 0
            elif name=='WlanFreeMemory':assert args[0] in (C.addressof(self.wlan_list),C.addressof(self.wlan_cap));self.free_count+=1
            elif name=='WlanCloseHandle':assert args[0]==0x8000;return 0
            elif name=='CoInitializeEx':assert args[1]==2;return self.options.get('coinit',0)
            elif name=='CoUninitialize':pass
            elif name=='CoCreateInstance':
                assert args[2]==1 and args[0][0].Data1==p.CLSID_MMDeviceEnumerator[0] and args[3][0].Data1==p.IID_IMMDeviceEnumerator[0]
                if self.options.get('cocreate_fail'):return -1
                args[4][0]=self.grant('enumerator');return 0
            elif name=='CoTaskMemFree':assert args[0]==C.addressof(self.wave);self.free_count+=1
            return None
        return call

    def grant(self,name):
        ptr=C.addressof(self.objects[name]);self.live[ptr]=self.live.get(ptr,0)+1;return ptr

    def _build_com(self):
        class Object(C.Structure):_fields_=[('table',C.POINTER(C.c_void_p))]
        self.objects={}
        for name,methods in {'enumerator':('EnumAudioEndpoints',),'collection':('GetCount','Item'),
                             'endpoint':('Activate',),'client':('GetMixFormat',)}.items():
            table=(C.c_void_p*9)()
            for method in ('Release',)+methods:
                slot,result,args=p.COM[method]
                callback=d.FUNCTYPE(result,C.c_void_p,*args)(self.safe(method,self._com(method),result));table[slot]=C.cast(callback,C.c_void_p).value;self.keep.append(callback)
            self.objects[name]=Object(table);self.keep.append(table)

    def _com(self,method):
        def call(ptr,*args):
            self.called(method)
            if method=='Release':assert self.live[ptr]>0;self.live[ptr]-=1;return 0
            if self.options.get('audio_fail')==method:return -1
            if method=='EnumAudioEndpoints':assert args[0] in (0,1) and args[1]==1;args[2][0]=self.grant('collection')
            elif method=='GetCount':args[0][0]=self.options.get('audio_count',1)
            elif method=='Item':assert args[0]==0;args[1][0]=self.grant('endpoint')
            elif method=='Activate':assert args[0][0].Data1==p.IID_IAudioClient[0] and args[1]==1 and args[2] is None;args[3][0]=self.grant('client')
            elif method=='GetMixFormat':args[0][0]=C.addressof(self.wave)
            return 0
        return call


class Tests(unittest.TestCase):
    def setUp(self):self.first_fixture=len(Fixture.instances)
    def tearDown(self):
        for f in Fixture.instances[self.first_fixture:]:self.assertFalse(f.callback_errors,'typed callback assertions must not be swallowed: '+repr(f.callback_errors))
    def test_fixed_width_layouts_and_exports(self):
        self.assertEqual(C.sizeof(p.HIDP_CAPS),64)
        self.assertEqual(C.sizeof(p.HIDP_LINK_COLLECTION_NODE),24 if C.sizeof(C.c_void_p)==8 else 20)
        self.assertEqual(C.sizeof(p.WLAN_INTERFACE_INFO),532)
        self.assertEqual(C.sizeof(p.WLAN_INTERFACE_CAPABILITY),276)
        self.assertEqual(C.sizeof(p.WAVEFORMATEX),18);self.assertEqual(C.sizeof(p.WAVEFORMATEXTENSIBLE),40)
        self.assertEqual(p.WLAN_MAX_PHY_INDEX,64)
        self.assertEqual(dict((name,result) for _,name,result,_ in p.EXPORTS)['HidD_GetPreparsedData'],C.c_uint8)
        forbidden={'ReadFile','WriteFile','HidD_GetFeature','HidD_GetInputReport','WlanScan','WlanGetAvailableNetworkList','WlanGetProfile','WlanQueryInterface'}
        self.assertFalse(forbidden.intersection(name for _,name,_,_ in p.EXPORTS))
        self.assertFalse({'Initialize','Start','GetService','GetBuffer','GetId','OpenPropertyStore'}.intersection(p.COM))

    def test_hid_metadata_and_no_events(self):
        f=Fixture();r=p.hid_capabilities(f.native,0x7000)
        self.assertEqual(r['status'],'measured');self.assertEqual(r['value']['declared_finger_collection_count'],1)
        self.assertEqual(r['value']['contact_limit']['status'],'unavailable')
        self.assertEqual(f.calls['HidD_FreePreparsedData'],1)

    def test_hid_failures_free_owned_metadata(self):
        for options,status in [({'preparsed_fail':True},'unavailable'),({'caps_fail':True},'unavailable'),({'nodes_fail':True},'partial'),({'returned_nodes':3},'partial')]:
            with self.subTest(options=options):
                f=Fixture(**options);r=p.hid_capabilities(f.native,0x7000);self.assertEqual(r['status'],status)
                self.assertEqual(f.calls.get('HidD_FreePreparsedData',0),0 if options.get('preparsed_fail') else 1)

    def test_hid_caps_and_index_bounds(self):
        f=Fixture();f.caps.NumberLinkCollectionNodes=257;r=p.hid_capabilities(f.native,0x7000)
        self.assertEqual(r['status'],'partial');self.assertNotIn('HidP_GetLinkCollectionNodes',f.calls)
        f=Fixture();f.nodes[1].Parent=2;r=p.hid_capabilities(f.native,0x7000);self.assertEqual(r['status'],'partial')
        f=Fixture();f.nodes[1].Flags=256;r=p.hid_capabilities(f.native,0x7000);self.assertEqual(r['value']['declared_finger_collection_count'],0)

    def test_hid_interface_identity_join_and_cleanup(self):
        f=Fixture();raw=[{'instance_id':'PCI\\VEN_8086&DEV_1111\\PRIVATE_PARENT'}, {'instance_id':'HID\\VID_1234&PID_5678\\PRIVATE_INSTANCE'}]
        d.build_device_map(raw)
        r=p.hid_interfaces(f.native,raw,time.monotonic()+1)
        self.assertEqual(r['status'],'measured');self.assertEqual(r['value'][0]['pnp_node'],'n1')
        self.assertNotIn('PRIVATE',json.dumps(r));self.assertEqual(f.calls['CloseHandle'],1);self.assertEqual(f.calls['SetupDiDestroyDeviceInfoList'],1)
        f=Fixture();raw[1]['instance_id']='HID\\VID_1234&PID_5678\\DIFFERENT_TAIL';d.build_device_map(raw);r=p.hid_interfaces(f.native,raw,time.monotonic()+1)
        self.assertNotIn('pnp_node',r['value'][0]);self.assertIn('pnp_link',r['value'][0])

    def test_hid_interface_error_bounds(self):
        for options in ({'detail_size':9000},{'detail_fail':True},{'open_fail':True}):
            f=Fixture(**options);r=p.hid_interfaces(f.native,[],time.monotonic()+1)
            self.assertEqual(f.calls['SetupDiDestroyDeviceInfoList'],1);self.assertNotIn('PRIVATE',json.dumps(r))
            self.assertNotIn('CloseHandle',f.calls)
        f=Fixture();r=p.hid_interfaces(f.native,[],time.monotonic()-1)
        self.assertEqual(r['status'],'partial');self.assertNotIn('SetupDiEnumDeviceInterfaces',f.calls)

    def test_duplicate_instance_cannot_silently_select_one_node(self):
        raw=[{'instance_id':r'HID\VID_1234&PID_5678\PRIVATE_INSTANCE'}]*2
        d.build_device_map(raw)
        f=Fixture();result=p.hid_interfaces(f.native,raw,time.monotonic()+1)
        self.assertNotIn('pnp_node',result['value'][0])
        self.assertIn('unavailable',result['value'][0]['pnp_link'])

    def test_unavailable_hid_descriptor_marks_the_interface_stage_partial(self):
        f=Fixture(preparsed_fail=True)
        result=p.hid_interfaces(f.native,[],time.monotonic()+1)
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['value'][0]['capabilities']['status'],'unavailable')
        self.assertEqual(f.calls['CloseHandle'],1)

    def test_component_checkpoints_precede_the_next_optional_probe(self):
        saved=[]
        result,errors=p.collect(native_factory=lambda only:Fixture().native,checkpoint=lambda value:saved.append(dict(value)))
        self.assertEqual([list(value) for value in saved],[['hid'],['hid','audio'],['hid','audio','wifi']])
        self.assertEqual(saved[0]['hid']['status'],'measured')

    def test_wifi_capabilities_and_privacy(self):
        f=Fixture();r=p.wifi_capabilities(f.native,time.monotonic()+1)
        self.assertEqual(r['value'][0]['capabilities']['value']['supported_phy_types'],[7,8,9])
        self.assertNotIn('PRIVATE',json.dumps(r));self.assertNotIn('12345678',json.dumps(r))
        self.assertEqual(f.free_count,2);self.assertEqual(f.calls['WlanCloseHandle'],1)

    def test_wifi_errors_and_bounds_cleanup(self):
        for options in ({'wifi_open_fail':True},{'wifi_enum_fail':True},{'wifi_count':17},{'wifi_caps_fail':True}):
            f=Fixture(**options);r=p.wifi_capabilities(f.native,time.monotonic()+1)
            self.assertEqual(f.calls.get('WlanCloseHandle',0),0 if options.get('wifi_open_fail') else 1)
            self.assertNotIn('PRIVATE',json.dumps(r))
        f=Fixture();f.wlan_cap.dwNumberOfSupportedPhys=65;r=p.wifi_capabilities(f.native,time.monotonic()+1)
        self.assertEqual(r['value'][0]['capabilities']['status'],'unavailable');self.assertEqual(f.free_count,2)
        f=Fixture();r=p.wifi_capabilities(f.native,time.monotonic()-1);self.assertEqual(r['status'],'partial');self.assertEqual(f.free_count,1)

    def test_audio_mix_format_and_com_cleanup(self):
        f=Fixture();r=p.audio_capabilities(f.native,time.monotonic()+1)
        self.assertEqual(len(r['value']),2);self.assertEqual(r['value'][0]['mix_format']['value']['sample_format'],'IEEE float')
        self.assertEqual(r['value'][0]['mix_format']['value']['channels'],2)
        self.assertEqual(f.free_count,2);self.assertTrue(all(n==0 for n in f.live.values()));self.assertEqual(f.calls['CoUninitialize'],1)

    def test_audio_failures_release_all_com(self):
        for method in ('EnumAudioEndpoints','GetCount','Item','Activate','GetMixFormat'):
            with self.subTest(method=method):
                f=Fixture(audio_fail=method);p.audio_capabilities(f.native,time.monotonic()+1)
                self.assertTrue(all(n==0 for n in f.live.values()));self.assertEqual(f.calls['CoUninitialize'],1)
        f=Fixture(coinit=-1);r=p.audio_capabilities(f.native,time.monotonic()+1);self.assertEqual(r['status'],'unavailable');self.assertNotIn('CoUninitialize',f.calls)
        f=Fixture(cocreate_fail=True);p.audio_capabilities(f.native,time.monotonic()+1);self.assertEqual(f.calls['CoUninitialize'],1)
        f=Fixture(audio_count=33);r=p.audio_capabilities(f.native,time.monotonic()+1);self.assertEqual(r['status'],'partial');self.assertNotIn('Item',f.calls)

    def test_audio_invalid_formats_no_overread(self):
        for change in ('channels','rate','extra','bits'):
            f=Fixture()
            if change=='channels':f.wave.Format.nChannels=65
            elif change=='rate':f.wave.Format.nSamplesPerSec=0
            elif change=='extra':f.wave.Format.cbSize=1
            else:f.wave.wValidBitsPerSample=33
            r=p.audio_capabilities(f.native,time.monotonic()+1)
            self.assertEqual(r['value'][0]['mix_format']['status'],'unavailable');self.assertEqual(f.free_count,2)
            self.assertTrue(all(n==0 for n in f.live.values()))

    def test_deadline_and_sensitive_errors_are_unavailable(self):
        def fail(**kwargs):raise OSError('PRIVATE_INTERFACE_NAME')
        r,errors=p.collect(native_factory=fail,seconds=0)
        self.assertEqual(len(errors),3);self.assertTrue(all(v['status']=='unavailable' for v in r.values()))
        r,errors=p.collect(native_factory=fail,seconds=1)
        self.assertNotIn('PRIVATE',json.dumps(r));self.assertTrue(all(v['status']=='unavailable' for v in r.values()))

    def test_isolated_worker_component_checkpoint_and_failure(self):
        raw=[{'instance_id':'HID\\VID_1234&PID_5678\\PRIVATE_INSTANCE'}];calls=[];saved=[]
        def peripherals(checkpoint=None):
            calls.append('metadata')
            checkpoint({'hid':d.measured([], 'fixture')})
            return {'hid':d.measured([], 'fixture'),'audio':d.unavailable('bounded','fixture'),'wifi':d.unavailable('bounded','fixture')},['metadata incomplete']
        backends={'platform_role':lambda:(1,[]),'devices':lambda:(raw,[]),'peripheral_caps':peripherals,
                  'display_paths':lambda:([],[]),'graphics':lambda:([],[])}
        result=d.collect(backends,checkpoint=lambda out:saved.append(json.loads(json.dumps(out))))
        self.assertEqual(calls,['metadata'])
        intermediate=next(value['peripheral_caps'] for value in saved if value.get('peripheral_caps',{}).get('error','').startswith('peripheral collection in progress'))
        self.assertEqual(intermediate['value']['hid']['status'],'measured')
        self.assertEqual(intermediate['value']['wifi']['status'],'unavailable')
        self.assertEqual(result['peripheral_caps']['status'],'partial');self.assertNotIn('PRIVATE',json.dumps(result))
        def fail(checkpoint=None):raise OSError('PRIVATE_API_PATH')
        backends['peripheral_caps']=fail;result=d.collect(backends)
        self.assertEqual(result['peripheral_caps']['status'],'unavailable');self.assertEqual(result['graphics']['status'],'measured')
        self.assertNotIn('PRIVATE_API_PATH',json.dumps(result))



if __name__=='__main__':unittest.main()
