"""Windows SDK ABI and actual read-only OS API verification for the packaged collector."""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import shutil
from p1401 import hwcapture as hc


def verify_capture_native(repo, output, evidence=None):
    evidence = evidence if evidence is not None else {}
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
    evidence['windows_sdk_layouts'] = sdk
    if sdk != expected: raise RuntimeError('Windows SDK capture layouts differ from the packaged bindings.')
    topology = hc.cpu_topology()
    if topology.get('status') != 'measured' or not topology['value']['cores']:
        raise RuntimeError('The actual Windows topology API did not produce measured cores.')
    evidence['real_topology_api'] = True
    k = hc._kernel32()
    k.GetActiveProcessorCount.argtypes = [ctypes.c_uint16]; k.GetActiveProcessorCount.restype = ctypes.c_uint32
    if k.GetActiveProcessorCount(0xFFFF) != topology['value']['logical_processors']:
        raise RuntimeError('Topology parsing disagrees with actual active logical processors.')
    evidence['topology_matches_active_processors'] = True
    k.GetSystemDirectoryW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]; k.GetSystemDirectoryW.restype = ctypes.c_uint32
    buf = ctypes.create_unicode_buffer(32768)
    n = k.GetSystemDirectoryW(buf, len(buf))
    if not 0 < n < len(buf): raise RuntimeError('System directory query failed.')
    fixtures = [('system-powershell', os.path.join(buf.value, 'WindowsPowerShell', 'v1.0', 'powershell.exe')),
                ('installed-python', sys.executable), ('installed-msvc', shutil.which('cl'))]
    evidence['trust_fixtures'] = []
    accepted = False
    for label, fixture in fixtures:
        if not fixture: continue
        with hc._system_file(fixture) as handle:
            status = hc.authenticode_status(fixture, handle)
        record = {'label': label, 'winverifytrust_status': status, 'winverifytrust_hex': f'0x{status & 0xffffffff:08x}'}
        # OS diagnostics also recognize catalog signatures; CHOICE_FILE verifies embedded signatures only.
        # Labels and statuses are retained; file paths and certificate subject identities are omitted.
        environment = dict(os.environ, CAPTURE_SIGNATURE_FIXTURE=fixture)
        script = "$s=Get-AuthenticodeSignature -LiteralPath $env:CAPTURE_SIGNATURE_FIXTURE; @{status=$s.Status.ToString();type=$s.SignatureType.ToString()} | ConvertTo-Json -Compress"
        try:
            info = json.loads(subprocess.check_output([os.path.join(buf.value, 'WindowsPowerShell', 'v1.0', 'powershell.exe'),
                             '-NoProfile', '-NonInteractive', '-Command', script], env=environment, timeout=10))
            record['os_signature_status'] = str(info.get('status', 'unavailable'))[:48]
            record['os_signature_type'] = str(info.get('type', 'unavailable'))[:48]
        except Exception as error:
            record['os_signature_query'] = type(error).__name__
        evidence['trust_fixtures'].append(record)
        accepted = accepted or status == 0
    if not accepted: raise RuntimeError('No installed signed fixture passed actual embedded-signature verification.')
    evidence['signed_system_file_accepted'] = True
    unsigned = Path(output).parent / 'unsigned-capture-test.bin'
    unsigned.write_bytes(b'capture verification fixture')
    with hc._system_file(str(unsigned)) as handle:
        status = hc.authenticode_status(str(unsigned), handle)
        evidence['unsigned_status'] = status
        evidence['unsigned_status_hex'] = f'0x{status & 0xffffffff:08x}'
        if status == 0: raise RuntimeError('Unsigned fixture was accepted by WinVerifyTrust.')
    unsigned.unlink()
    result = hc._bounded_native()
    if result.get('cpu_topology', {}).get('status') != 'measured':
        raise RuntimeError('The actual packaged isolated collector did not return CPU topology.')
    evidence.update({'unsigned_file_rejected': True, 'isolated_worker': True, 'vendor_driver_hardware_qualified': False})
    return evidence
