"""Windows SDK ABI and actual read-only OS API verification for the packaged collector."""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
from p1401 import hwcapture as hc


def verify_capture_native(repo, output):
    if sys.platform != 'win32' or ctypes.sizeof(ctypes.c_void_p) != 8:
        raise RuntimeError('Native capture verification needs 64-bit Windows.')
    exe = Path(output).parent / 'capture-abi.exe'
    subprocess.run(['cl', '/nologo', '/O2', str(Path(repo) / 'tools/windows_capture_abi.c'), '/link', '/OUT:' + str(exe)],
                   cwd=exe.parent, check=True, capture_output=True, timeout=30)
    sdk = json.loads(subprocess.check_output([str(exe)], timeout=10))
    expected = {'trust_size': ctypes.sizeof(hc.TrustData), 'trust_file': hc.TrustData.pFile.offset,
                'trust_state': hc.TrustData.hWVTStateData.offset, 'file_size': ctypes.sizeof(hc.FileInfo),
                'file_handle': hc.FileInfo.hFile.offset, 'group_size': 16, 'processor_groups': 30,
                'processor_mask': 32, 'cache_mask': 40, 'numa_mask': 32}
    if sdk != expected: raise RuntimeError('Windows SDK capture layouts differ from the packaged bindings.')
    topology = hc.cpu_topology()
    if topology.get('status') != 'measured' or not topology['value']['cores']:
        raise RuntimeError('The actual Windows topology API did not produce measured cores.')
    k = hc._kernel32()
    k.GetActiveProcessorCount.argtypes = [ctypes.c_uint16]; k.GetActiveProcessorCount.restype = ctypes.c_uint32
    if k.GetActiveProcessorCount(0xFFFF) != topology['value']['logical_processors']:
        raise RuntimeError('Topology parsing disagrees with actual active logical processors.')
    k.GetSystemDirectoryW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]; k.GetSystemDirectoryW.restype = ctypes.c_uint32
    buf = ctypes.create_unicode_buffer(32768)
    n = k.GetSystemDirectoryW(buf, len(buf))
    if not 0 < n < len(buf): raise RuntimeError('System directory query failed.')
    signed = os.path.join(buf.value, 'WindowsPowerShell', 'v1.0', 'powershell.exe')
    with hc._system_file(signed) as handle:
        if not hc.authenticode_ok(signed, handle): raise RuntimeError('Actual Windows signed-system-file verification failed.')
    unsigned = Path(output).parent / 'unsigned-capture-test.bin'
    unsigned.write_bytes(b'capture verification fixture')
    with hc._system_file(str(unsigned)) as handle:
        if hc.authenticode_ok(str(unsigned), handle): raise RuntimeError('Unsigned fixture was accepted by WinVerifyTrust.')
    unsigned.unlink()
    result = hc._bounded_native()
    if result.get('cpu_topology', {}).get('status') != 'measured':
        raise RuntimeError('The actual packaged isolated collector did not return CPU topology.')
    return {'windows_sdk_layouts': sdk, 'real_topology_api': True, 'topology_matches_active_processors': True,
            'signed_system_file_accepted': True, 'unsigned_file_rejected': True, 'isolated_worker': True,
            'vendor_driver_hardware_qualified': False}
