"""Windows SDK ABI and actual read-only OS API verification for the packaged collector."""
import ctypes
import importlib.util
import base64
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
        script = "$ErrorActionPreference='Stop'; try { $s=Microsoft.PowerShell.Security\\Get-AuthenticodeSignature -LiteralPath $env:CAPTURE_SIGNATURE_FIXTURE; $type='unavailable'; if ($s.PSObject.Properties.Name -contains 'SignatureType') {$type=[string]$s.SignatureType}; @{status=[string]$s.Status;type=$type} | ConvertTo-Json -Compress } catch {exit 9}"
        encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
        try:
            info = json.loads(subprocess.check_output([os.path.join(buf.value, 'WindowsPowerShell', 'v1.0', 'powershell.exe'),
                             '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded], env=environment,
                             stderr=subprocess.DEVNULL, timeout=10))
            record['os_signature_status'] = str(info.get('status', 'unavailable'))[:48]
            record['os_signature_type'] = str(info.get('type', 'unavailable'))[:48]
        except Exception as error:
            record['os_signature_query'] = type(error).__name__
            if isinstance(error, subprocess.CalledProcessError):
                record['os_signature_query_exit'] = error.returncode
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
    # Compile the actual Windows SDK declarations for every device-map structure/slot/constant.
    specification = importlib.util.spec_from_file_location('device_map_abi_check', Path(repo) / 'tools/device_map_abi.py')
    abi = importlib.util.module_from_spec(specification); specification.loader.exec_module(abi)
    generated = Path(output).parent / 'device-map-abi.c'
    generated.write_text(abi.generate() + '\nint main(void) {return check_guids();}\n')
    native = Path(output).parent / 'device-map-abi.exe'
    subprocess.run(['cl', '/nologo', '/std:c11', '/O2', str(generated), '/link', '/OUT:' + str(native)],
                   cwd=native.parent, check=True, capture_output=True, timeout=30)
    subprocess.run([str(native)], check=True, capture_output=True, timeout=10)
    evidence['device_map_windows_sdk_abi'] = True
    firmware_spec = importlib.util.spec_from_file_location('firmware_abi_check', Path(repo) / 'tools/firmware_resources_abi.py')
    firmware_abi = importlib.util.module_from_spec(firmware_spec); firmware_spec.loader.exec_module(firmware_abi)
    generated = Path(output).parent / 'firmware-resource-abi.c'
    generated.write_text(firmware_abi.generate(True) + '\nint main(void) {return 0;}\n')
    native = Path(output).parent / 'firmware-resource-abi.exe'
    subprocess.run(['cl', '/nologo', '/std:c11', '/O2', str(generated), '/link', '/OUT:' + str(native)],
                   cwd=native.parent, check=True, capture_output=True, timeout=30)
    subprocess.run([str(native)], check=True, capture_output=True, timeout=10)
    evidence['firmware_resource_job_windows_sdk_abi'] = True
    from check_job_native import verify_job_native
    evidence['subprocess_containment'] = verify_job_native(repo)
    from check_peripheral_native import verify_peripheral_sdk, verify_cim_engine
    evidence['peripheral_sdk'] = verify_peripheral_sdk(repo, Path(output).parent)
    evidence['cim_engine'] = verify_cim_engine(repo, Path(output).parent)
    if evidence['cim_engine'].get('ok') is not True:raise RuntimeError('System PowerShell/CIM engine did not pass its fixed read-only query.')
    from check_cpu_native import verify_cpu_native
    evidence['cpu_native'] = {}
    verify_cpu_native(repo, Path(output).parent, evidence['cpu_native'])

    csc = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    compiled = Path(output).parent / 'scan-evidence-check.exe'
    subprocess.run([str(csc), '/nologo', '/target:exe', '/reference:System.Web.Extensions.dll', '/out:' + str(compiled),
                    str(Path(repo) / 'windows/App/ScanEvidence.cs'), str(Path(repo) / 'tools/ScanEvidenceCheck.cs')],
                   check=True, capture_output=True, timeout=30)
    gui_proof = Path(output).parent / 'scan-evidence-check.json'
    subprocess.run([str(compiled), str(gui_proof)], check=True, capture_output=True, timeout=10)
    evidence['compiled_scan_evidence_binding'] = json.loads(gui_proof.read_text()).get('scan_evidence_binding') is True
    if not evidence['compiled_scan_evidence_binding']: raise RuntimeError('Compiled scan receipt binding failed.')
    result = hc._bounded_native()
    if result.get('cpu_topology', {}).get('status') != 'measured':
        raise RuntimeError('The actual isolated collector did not return CPU topology.')
    device_map = result.get('device_map') or {}
    counts = {'measured': [], 'partial': [], 'unavailable': []}
    for stage in hc.DEVICE_STAGES:
        record = device_map.get(stage) or {}
        status = record.get('status')
        if status not in counts or not record.get('source'): raise RuntimeError('Device map stage lacks its status/source.')
        counts[status].append(stage)
        if status == 'measured' and record.get('error'): raise RuntimeError('Measured device map stage carries an error.')
        if status in ('partial', 'unavailable') and not record.get('error'): raise RuntimeError('Incomplete device map stage has no reason.')
        if status == 'unavailable' and 'value' in record: raise RuntimeError('Unavailable device map stage carries a value.')
    if 'devices' not in counts['measured'] + counts['partial']:
        raise RuntimeError('Actual Windows SetupAPI device inventory did not run.')
    serialized = json.dumps(device_map)
    for identifier in (os.environ.get('USERNAME', ''), os.environ.get('COMPUTERNAME', '')):
        if len(identifier) >= 3 and identifier.lower() in serialized.lower(): raise RuntimeError('Private identity appeared in the device map.')
    evidence['device_map_native_stages'] = counts
    evidence['device_map_stage_reasons'] = {stage: {'status':record.get('status'), 'reason':record.get('error'), 'source':record.get('source')} for stage in hc.DEVICE_STAGES for record in [device_map.get(stage) or {}] if record.get('status') != 'measured'}
    evidence['device_nodes'] = len(((device_map.get('devices') or {}).get('value') or {}).get('nodes') or [])
    evidence['graphics_adapters'] = len((device_map.get('graphics') or {}).get('value') or [])
    peripheral=(device_map.get('peripheral_caps') or {}).get('value') or {}
    evidence['peripheral_components']={key:{'status':record.get('status'),'reason':record.get('error'),'source':record.get('source'),'observed_count':len(record.get('value') or [])} for key,record in peripheral.items()}
    for key,record in peripheral.items():
        if key not in ('hid','audio','wifi') or record.get('status') not in ('measured','partial','unavailable') or not record.get('source'): raise RuntimeError('Peripheral component lacks its bounded status/source.')
        if record['status'] != 'measured' and not record.get('error'): raise RuntimeError('Incomplete peripheral metadata has no reason.')
    evidence.update({'unsigned_file_rejected': True, 'isolated_worker': True, 'vendor_driver_hardware_qualified': False})
    return evidence
