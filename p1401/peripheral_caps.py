"""Read-only peripheral metadata for the isolated capture worker; no input, streams or RF scans."""
import ctypes as C
import time
from . import devicemap as d

P = C.POINTER
U8, U16, U32, I32, HANDLE = C.c_uint8, C.c_uint16, C.c_uint32, C.c_int32, C.c_void_p
MAX_HID, MAX_COLLECTIONS, MAX_WLAN, MAX_AUDIO, MAX_PATH_BYTES = 64, 256, 16, 32, 8192
WLAN_MAX_PHY_INDEX = 64
HIDP_STATUS_SUCCESS = 0x00110000
INVALID_HANDLE = C.c_void_p(-1).value


class HIDP_CAPS(C.Structure):
    _fields_ = [(x, U16) for x in ('Usage', 'UsagePage', 'InputReportByteLength', 'OutputReportByteLength', 'FeatureReportByteLength')]
    _fields_ += [('Reserved', U16 * 17)]
    _fields_ += [(x, U16) for x in ('NumberLinkCollectionNodes', 'NumberInputButtonCaps', 'NumberInputValueCaps',
                 'NumberInputDataIndices', 'NumberOutputButtonCaps', 'NumberOutputValueCaps', 'NumberOutputDataIndices',
                 'NumberFeatureButtonCaps', 'NumberFeatureValueCaps', 'NumberFeatureDataIndices')]


class HIDP_LINK_COLLECTION_NODE(C.Structure):
    _fields_ = [(x, U16) for x in ('LinkUsage', 'LinkUsagePage', 'Parent', 'NumberOfChildren', 'NextSibling', 'FirstChild')]
    # Exact ULONG bitfield allocation unit: CollectionType8, IsAlias1, Reserved23.
    _fields_ += [('Flags', U32), ('UserContext', C.c_void_p)]


class SP_DEVICE_INTERFACE_DATA(C.Structure):
    _fields_ = [('cbSize', U32), ('InterfaceClassGuid', d.GUID), ('Flags', U32), ('Reserved', C.c_size_t)]


class WLAN_INTERFACE_INFO(C.Structure):
    # Description is deliberately never decoded or serialized.
    _fields_ = [('InterfaceGuid', d.GUID), ('strInterfaceDescription', U16 * 256), ('isState', I32)]


class WLAN_INTERFACE_CAPABILITY(C.Structure):
    _fields_ = [('interfaceType', I32), ('bDot11DSupported', I32), ('dwMaxDesiredSsidListSize', U32),
                ('dwMaxDesiredBssidListSize', U32), ('dwNumberOfSupportedPhys', U32), ('dot11PhyTypes', I32 * WLAN_MAX_PHY_INDEX)]


class WAVEFORMATEX(C.Structure):
    _pack_ = 1
    _fields_ = [('wFormatTag', U16), ('nChannels', U16), ('nSamplesPerSec', U32), ('nAvgBytesPerSec', U32),
                ('nBlockAlign', U16), ('wBitsPerSample', U16), ('cbSize', U16)]


class WAVEFORMATEXTENSIBLE(C.Structure):
    _pack_ = 1
    _fields_ = [('Format', WAVEFORMATEX), ('wValidBitsPerSample', U16), ('dwChannelMask', U32), ('SubFormat', d.GUID)]


EXPORTS = [
    ('hid', 'HidD_GetHidGuid', None, [P(d.GUID)]),
    ('hid', 'HidD_GetPreparsedData', U8, [HANDLE, P(C.c_void_p)]),
    ('hid', 'HidD_FreePreparsedData', U8, [C.c_void_p]),
    ('hid', 'HidP_GetCaps', I32, [C.c_void_p, P(HIDP_CAPS)]),
    ('hid', 'HidP_GetLinkCollectionNodes', I32, [P(HIDP_LINK_COLLECTION_NODE), P(U32), C.c_void_p]),
    ('setupapi', 'SetupDiGetClassDevsW', HANDLE, [P(d.GUID), C.c_wchar_p, HANDLE, U32]),
    ('setupapi', 'SetupDiEnumDeviceInterfaces', I32, [HANDLE, P(d.SP_DEVINFO_DATA), P(d.GUID), U32, P(SP_DEVICE_INTERFACE_DATA)]),
    ('setupapi', 'SetupDiGetDeviceInterfaceDetailW', I32, [HANDLE, P(SP_DEVICE_INTERFACE_DATA), C.c_void_p, U32, P(U32), P(d.SP_DEVINFO_DATA)]),
    ('setupapi', 'SetupDiDestroyDeviceInfoList', I32, [HANDLE]),
    ('cfgmgr32', 'CM_Get_Device_IDW', U32, [U32, C.c_void_p, U32, U32]),
    ('kernel32', 'CreateFileW', HANDLE, [P(U16), U32, U32, C.c_void_p, U32, U32, HANDLE]),
    ('kernel32', 'CloseHandle', I32, [HANDLE]),
    ('wlanapi', 'WlanOpenHandle', U32, [U32, C.c_void_p, P(U32), P(HANDLE)]),
    ('wlanapi', 'WlanEnumInterfaces', U32, [HANDLE, C.c_void_p, P(C.c_void_p)]),
    ('wlanapi', 'WlanGetInterfaceCapability', U32, [HANDLE, P(d.GUID), C.c_void_p, P(C.c_void_p)]),
    ('wlanapi', 'WlanFreeMemory', None, [C.c_void_p]),
    ('wlanapi', 'WlanCloseHandle', U32, [HANDLE, C.c_void_p]),
    ('ole32', 'CoInitializeEx', I32, [C.c_void_p, U32]),
    ('ole32', 'CoUninitialize', None, []),
    ('ole32', 'CoCreateInstance', I32, [P(d.GUID), C.c_void_p, U32, P(d.GUID), P(C.c_void_p)]),
    ('ole32', 'CoTaskMemFree', None, [C.c_void_p]),
]
COM = {'Release': (2, U32, []),
       'EnumAudioEndpoints': (3, I32, [I32, U32, P(C.c_void_p)]),
       'GetCount': (3, I32, [P(U32)]), 'Item': (4, I32, [U32, P(C.c_void_p)]),
       'Activate': (3, I32, [P(d.GUID), U32, C.c_void_p, P(C.c_void_p)]),
       'GetMixFormat': (8, I32, [P(C.c_void_p)])}


class Native:
    def __init__(self, only, libraries=None, last_error=None):
        self.f = {}
        libraries = {} if libraries is None else libraries
        for dll, name, result, args in EXPORTS:
            if dll not in only:
                continue
            if dll not in libraries:
                libraries[dll] = C.WinDLL(dll + '.dll', use_last_error=True, winmode=d.LOAD_LIBRARY_SEARCH_SYSTEM32)
            fn = getattr(libraries[dll], name)
            fn.restype, fn.argtypes = result, args
            self.f[name] = fn
        self.last_error = last_error or (C.get_last_error if hasattr(C, 'get_last_error') else lambda: 0)

    @staticmethod
    def com(ptr, method):
        slot, result, args = COM[method]
        table = C.cast(ptr, P(P(C.c_void_p)))[0]
        if not table or not table[slot]:
            raise OSError('missing documented COM method')
        return d.FUNCTYPE(result, C.c_void_p, *args)(table[slot])

    def release(self, ptr):
        if ptr:
            self.com(ptr, 'Release')(ptr)


def hid_capabilities(nt, handle):
    pp = C.c_void_p()
    if not nt.f['HidD_GetPreparsedData'](handle, C.byref(pp)) or not pp.value:
        return d.unavailable('preparsed metadata unavailable', 'HidD_GetPreparsedData')
    try:
        caps = HIDP_CAPS()
        status = nt.f['HidP_GetCaps'](pp, C.byref(caps)) & 0xffffffff
        if status != HIDP_STATUS_SUCCESS:
            return d.unavailable('HID status %08X' % status, 'HidP_GetCaps')
        value = {'usage_page': caps.UsagePage, 'usage': caps.Usage,
                 'report_size_bytes': {'input': caps.InputReportByteLength, 'output': caps.OutputReportByteLength,
                                       'feature': caps.FeatureReportByteLength},
                 'descriptor_capability_counts': {name: getattr(caps, name) for name in
                     ('NumberInputButtonCaps', 'NumberInputValueCaps', 'NumberInputDataIndices',
                      'NumberOutputButtonCaps', 'NumberOutputValueCaps', 'NumberOutputDataIndices',
                      'NumberFeatureButtonCaps', 'NumberFeatureValueCaps', 'NumberFeatureDataIndices')}}
        value['contact_limit'] = d.unavailable('collection count is not maximum simultaneous contacts; feature/input reports are not read', 'descriptor metadata only')
        count = int(caps.NumberLinkCollectionNodes)
        value['declared_collection_count'] = count
        if count > MAX_COLLECTIONS:
            return d.partial(value, 'HidP_GetCaps', 'collection metadata exceeds bounded probe')
        if not count:
            value['collections'] = []
            value['declared_finger_collection_count'] = 0
            return d.measured(value, 'HidP_GetCaps')
        nodes = (HIDP_LINK_COLLECTION_NODE * count)()
        length = U32(count)
        status = nt.f['HidP_GetLinkCollectionNodes'](nodes, C.byref(length), pp) & 0xffffffff
        if status != HIDP_STATUS_SUCCESS or length.value > count:
            return d.partial(value, 'HidP_GetCaps + HidP_GetLinkCollectionNodes', 'bounded collection metadata unavailable')
        rows = []
        for i in range(length.value):
            node = nodes[i]
            if any(x >= length.value for x in (node.Parent, node.NextSibling, node.FirstChild)) or node.NumberOfChildren > length.value:
                return d.partial(value, 'HidP_GetCaps + HidP_GetLinkCollectionNodes', 'invalid collection index')
            rows.append({'collection': 'c%d' % i, 'usage_page': node.LinkUsagePage, 'usage': node.LinkUsage,
                         'type': node.Flags & 255, 'alias': bool(node.Flags & 256), 'parent_index': node.Parent,
                         'child_count': node.NumberOfChildren})
        value['collections'] = rows
        value['declared_finger_collection_count'] = sum(row['usage_page'] == 13 and row['usage'] == 34 and not row['alias'] for row in rows)
        value['contact_limit'] = d.unavailable('collection count is not maximum simultaneous contacts; feature/input reports are not read', 'descriptor metadata only')
        return d.measured(value, 'HidP_GetCaps + HidP_GetLinkCollectionNodes')
    finally:
        nt.f['HidD_FreePreparsedData'](pp)


def hid_interfaces(nt, raw_devices, deadline):
    interface = d.GUID()
    nt.f['HidD_GetHidGuid'](C.byref(interface))
    device_set = nt.f['SetupDiGetClassDevsW'](C.byref(interface), None, None, 0x12)
    if device_set in (None, 0, INVALID_HANDLE):
        return d.unavailable('interface enumeration unavailable', 'SetupAPI HID interfaces')
    # Exact same-capture PnP instance equality only; no exported instance tail or VID/PID/name join.
    labels = d._report_local_instances
    rows, errors = [], []
    try:
        for index in range(MAX_HID + 1):
            if time.monotonic() >= deadline or index == MAX_HID:
                errors.append('HID interface count or time bound reached'); break
            data = SP_DEVICE_INTERFACE_DATA(); data.cbSize = C.sizeof(data)
            if not nt.f['SetupDiEnumDeviceInterfaces'](device_set, None, C.byref(interface), index, C.byref(data)):
                if nt.last_error() != d.ERROR_NO_MORE_ITEMS:
                    errors.append('HID interface enumeration stopped early')
                break
            size = U32()
            ok = nt.f['SetupDiGetDeviceInterfaceDetailW'](device_set, C.byref(data), None, 0, C.byref(size), None)
            if ok or nt.last_error() != d.ERROR_INSUFFICIENT_BUFFER or not 8 <= size.value <= MAX_PATH_BYTES or size.value & 1:
                errors.append('HID interface detail size unavailable'); continue
            buffer = C.create_string_buffer(size.value)
            C.cast(buffer, P(U32))[0] = 8 if C.sizeof(C.c_void_p) == 8 else 6
            node = d.SP_DEVINFO_DATA(); node.cbSize = C.sizeof(node)
            capacity = size.value
            if not nt.f['SetupDiGetDeviceInterfaceDetailW'](device_set, C.byref(data), buffer, capacity, C.byref(size), C.byref(node)) or size.value > capacity or size.value < 6:
                errors.append('HID interface detail unavailable'); continue
            # UTF-16 device path at SDK offsetof(DevicePath)=4, kept only until CreateFileW returns.
            path = C.cast(C.byref(buffer, 4), P(U16))
            units = (size.value - 4) // 2
            if not any(path[i] == 0 for i in range(units)):
                errors.append('HID interface path not terminated'); continue
            handle = nt.f['CreateFileW'](path, 0, 3, None, 3, 0, None)
            if handle in (None, 0, INVALID_HANDLE):
                rows.append({'interface': 'h%d' % index, 'capabilities': d.unavailable('metadata open denied', 'CreateFileW desired access0')})
                errors.append('HID metadata open denied')
                continue
            try:
                instance = d._device_id(nt, node.DevInst)
                row = {'interface': 'h%d' % index, 'capabilities': hid_capabilities(nt, handle)}
                if instance in labels:
                    row['pnp_node'] = labels[instance]
                else:
                    row['pnp_link'] = 'unavailable: exact node not in this capture'
                rows.append(row)
                if row['capabilities']['status'] != 'measured': errors.append('HID descriptor metadata incomplete')
            finally:
                nt.f['CloseHandle'](handle)
        return d.partial(rows, 'SetupAPI + HID descriptor metadata', '; '.join(errors)) if errors else d.measured(rows, 'SetupAPI + HID descriptor metadata')
    finally:
        nt.f['SetupDiDestroyDeviceInfoList'](device_set)


def wifi_capabilities(nt, deadline):
    version, handle, listing = U32(), HANDLE(), C.c_void_p()
    code = nt.f['WlanOpenHandle'](2, None, C.byref(version), C.byref(handle))
    if code or not handle.value:
        return d.unavailable('Native Wi-Fi open error%d' % code, 'WlanOpenHandle')
    rows, errors = [], []
    try:
        code = nt.f['WlanEnumInterfaces'](handle, None, C.byref(listing))
        if code or not listing.value:
            return d.unavailable('Native Wi-Fi enumeration error%d' % code, 'WlanEnumInterfaces')
        count = C.cast(listing, P(U32))[0]
        if count > MAX_WLAN:
            return d.unavailable('interface count exceeds bounded probe', 'WlanEnumInterfaces')
        base = listing.value + 8
        for i in range(count):
            if time.monotonic() >= deadline:
                errors.append('Wi-Fi capability time bound reached'); break
            entry = WLAN_INTERFACE_INFO.from_address(base + i * C.sizeof(WLAN_INTERFACE_INFO))
            caps = C.c_void_p()
            try:
                code = nt.f['WlanGetInterfaceCapability'](handle, C.byref(entry.InterfaceGuid), None, C.byref(caps))
                if code or not caps.value:
                    errors.append('Wi-Fi interface capability unavailable')
                    rows.append({'interface': 'w%d' % i, 'capabilities': d.unavailable('capability error%d' % code, 'WlanGetInterfaceCapability')}); continue
                value = WLAN_INTERFACE_CAPABILITY.from_address(caps.value)
                if value.dwNumberOfSupportedPhys > WLAN_MAX_PHY_INDEX:
                    errors.append('Wi-Fi PHY count exceeds SDK bound')
                    rows.append({'interface': 'w%d' % i, 'capabilities': d.unavailable('PHY count exceeds SDK array', 'WlanGetInterfaceCapability')}); continue
                rows.append({'interface': 'w%d' % i, 'capabilities': d.measured(
                    {'interface_type': value.interfaceType, 'dot11d_supported': bool(value.bDot11DSupported),
                     'supported_phy_types': [value.dot11PhyTypes[j] for j in range(value.dwNumberOfSupportedPhys)]},
                    'WlanGetInterfaceCapability'), 'pnp_link': 'unavailable: capability API supplies no parent node'})
            finally:
                if caps.value:
                    nt.f['WlanFreeMemory'](caps)
        return d.partial(rows, 'Native Wi-Fi capability API', '; '.join(errors)) if errors else d.measured(rows, 'Native Wi-Fi capability API')
    finally:
        if listing.value:
            nt.f['WlanFreeMemory'](listing)
        nt.f['WlanCloseHandle'](handle, None)


CLSID_MMDeviceEnumerator = (0xBCDE0395, 0xE52F, 0x467C, 0x8E, 0x3D, 0xC4, 0x57, 0x92, 0x91, 0x69, 0x2E)
IID_IMMDeviceEnumerator = (0xA95664D2, 0x9614, 0x4F35, 0xA7, 0x46, 0xDE, 0x8D, 0xB6, 0x36, 0x17, 0xE6)
IID_IAudioClient = (0x1CB9AD4C, 0xDBFA, 0x4C32, 0xB1, 0x78, 0xC2, 0xF5, 0x68, 0xA7, 0x03, 0xB2)


def mix_format(pointer):
    wave = C.cast(pointer, P(WAVEFORMATEX))[0]
    if not 1 <= wave.nChannels <= 64 or not 1000 <= wave.nSamplesPerSec <= 768000 or wave.cbSize > 256:
        raise ValueError('mix format fields outside bounded probe')
    row = {'channels': wave.nChannels, 'sample_rate': wave.nSamplesPerSec, 'container_bits': wave.wBitsPerSample,
           'block_align': wave.nBlockAlign, 'format_tag': wave.wFormatTag}
    if wave.wFormatTag in (1, 3):
        row['sample_format'] = 'PCM' if wave.wFormatTag == 1 else 'IEEE float'
    elif wave.wFormatTag == 0xfffe:
        if wave.cbSize < 22:
            raise ValueError('extensible mix format is truncated')
        ext = C.cast(pointer, P(WAVEFORMATEXTENSIBLE))[0]
        g = ext.SubFormat
        if g.Data2 == 0 and g.Data3 == 0x10 and bytes(g.Data4) == bytes([0x80, 0, 0, 0xaa, 0, 0x38, 0x9b, 0x71]):
            row['sample_format'] = {1: 'PCM', 3: 'IEEE float'}.get(g.Data1, 'other extensible')
        else:
            row['sample_format'] = 'other extensible'
        if ext.wValidBitsPerSample > wave.wBitsPerSample:
            raise ValueError('valid sample bits exceed container')
        row.update(valid_bits=ext.wValidBitsPerSample, channel_mask=ext.dwChannelMask)
    else:
        row['sample_format'] = 'other'
    return row


def audio_capabilities(nt, deadline):
    # The documented first-use contract for IAudioClient requires STA on Windows8.
    initialized = nt.f['CoInitializeEx'](None, 2)
    if initialized < 0:
        return d.unavailable('COM initialization failed', 'CoInitializeEx')
    enumerator = C.c_void_p()
    rows, errors = [], []
    try:
        clsid, iid, audio_iid = d.guid(*CLSID_MMDeviceEnumerator), d.guid(*IID_IMMDeviceEnumerator), d.guid(*IID_IAudioClient)
        hr = nt.f['CoCreateInstance'](C.byref(clsid), None, 1, C.byref(iid), C.byref(enumerator))
        if hr < 0 or not enumerator.value:
            return d.unavailable('endpoint enumerator unavailable', 'CoCreateInstance')
        for flow in (0, 1):
            collection = C.c_void_p()
            try:
                hr = nt.com(enumerator, 'EnumAudioEndpoints')(enumerator, flow, 1, C.byref(collection))
                if hr < 0 or not collection.value:
                    errors.append('active audio endpoint enumeration unavailable'); continue
                count = U32()
                if nt.com(collection, 'GetCount')(collection, C.byref(count)) < 0 or count.value > MAX_AUDIO:
                    errors.append('audio endpoint count unavailable or exceeds bound'); continue
                for i in range(count.value):
                    if time.monotonic() >= deadline:
                        errors.append('audio capability time bound reached'); break
                    endpoint, client, wave = C.c_void_p(), C.c_void_p(), C.c_void_p()
                    row = {'endpoint': '%s%d' % ('render' if flow == 0 else 'capture', i),
                           'codec_link': 'unavailable: no endpoint identity or property-store names queried',
                           'physical_speaker_wiring': 'unobserved'}
                    try:
                        hr = nt.com(collection, 'Item')(collection, i, C.byref(endpoint))
                        if hr < 0 or not endpoint.value:
                            row['mix_format'] = d.unavailable('endpoint unavailable', 'IMMDeviceCollection::Item')
                        else:
                            hr = nt.com(endpoint, 'Activate')(endpoint, C.byref(audio_iid), 1, None, C.byref(client))
                            if hr < 0 or not client.value:
                                row['mix_format'] = d.unavailable('audio metadata activation unavailable', 'IMMDevice::Activate(IAudioClient)')
                            else:
                                hr = nt.com(client, 'GetMixFormat')(client, C.byref(wave))
                                if hr < 0 or not wave.value:
                                    row['mix_format'] = d.unavailable('mix format unavailable', 'IAudioClient::GetMixFormat')
                                else:
                                    row['mix_format'] = d.measured(mix_format(wave), 'IAudioClient::GetMixFormat: shared-engine default, not all physical formats')
                    except ValueError:
                        row['mix_format'] = d.unavailable('invalid bounded format metadata', 'IAudioClient::GetMixFormat')
                    finally:
                        if wave.value:
                            nt.f['CoTaskMemFree'](wave)
                        try:
                            nt.release(client)
                        finally:
                            nt.release(endpoint)
                    rows.append(row)
                    if row['mix_format']['status'] != 'measured':
                        errors.append('audio endpoint format metadata unavailable')
            finally:
                nt.release(collection)
        return d.partial(rows, 'WASAPI read-only endpoint mix format', '; '.join(errors)) if errors else d.measured(rows, 'WASAPI read-only endpoint mix format')
    finally:
        try:
            nt.release(enumerator)
        finally:
            nt.f['CoUninitialize']()


def collect(raw_devices=(), native_factory=Native, seconds=3, checkpoint=None):
    deadline = time.monotonic() + min(max(seconds, 0), 3)
    out = {}
    for key, libraries, fn in (
            ('hid', {'hid', 'setupapi', 'cfgmgr32', 'kernel32'}, lambda nt: hid_interfaces(nt, raw_devices, deadline)),
            ('audio', {'ole32'}, lambda nt: audio_capabilities(nt, deadline)),
            ('wifi', {'wlanapi'}, lambda nt: wifi_capabilities(nt, deadline))):
        if time.monotonic() >= deadline:
            out[key] = d.unavailable('peripheral metadata time bound reached', 'owned capture worker')
            if checkpoint: checkpoint(dict(out))
            continue
        try:
            out[key] = fn(native_factory(only=libraries))
        except Exception:
            # No endpoint/interface names, paths, GUIDs or driver-generated exception strings are exported.
            out[key] = d.unavailable('documented capability API unavailable', 'owned capture worker')
        if checkpoint: checkpoint(dict(out))
    errors = [key + ' metadata incomplete' for key, value in out.items() if value['status'] != 'measured']
    return out, errors
