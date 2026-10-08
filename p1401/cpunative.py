"""Optional fixed packaged CPUID helper; no caller path, arguments, import-time queries or network."""
import hashlib
import json
from pathlib import Path
import re
import sys
from . import devicemap as dm, hwcapture, job_guard

SCHEMA = 'nm-cpuinfo/1'
SOURCE = 'nm_cpuinfo.exe documented read-only CPUID allow-list'
STAGE_TIMEOUT = 5.5
MAX_OUTPUT = 1024 * 1024
VENDORS = {'GenuineIntel', 'AuthenticAMD', 'HygonGenuine', 'CentaurHauls', '  Shanghai  ', 'VIA VIA VIA ', 'unknown'}
KEYS = {'schema','operation','sample_scope','basic','max_leaf','vendor','leaf1','signature','family','model','stepping','ecx','edx',
        'hypervisor_bit','hypervisor_meaning','leaf7','max_subleaf','subleaves','subleaf','eax','ebx','note','xcr0','value',
        'os_enabled_avx','os_enabled_avx512','cpu_reports_avx','cpu_reports_avx512f','topology','leaf','domains','type','shift',
        'logical','extended','e1_ecx','e1_edx','e8_eax','e8_ecx','amd_8000001E','per_logical_processor','groups','group','active',
        'mask','processors','bit','status','error','initial_apic_id','x2apic_id','core_type','raw','name','native_model_id',
        'max_basic_leaf','leaf1_ecx','leaf1_edx','max_extended_leaf','amd_leaf8000001e_raw','visited','affinity_refused',
        'stopped','affinity_restored','truncated','location_unavailable','partial'}
TEXT = {'fixed read-only CPUID allow-list', 'header is an unpinned helper-thread sample; per-processor records query their own capabilities',
        'CPUID reports a hypervisor present; an observation, not proof the hardware is virtual','measured','unavailable',
        'affinity refused','location unavailable','Intel Atom','Intel Core','reserved or unknown','max basic leaf below 1',
        'max basic leaf below 7','neither leaf 1FH nor 0BH present','topology leaves absent on this processor',
        'Intel leaf 1AH absent or zero on this processor','not executed: CPU reports no XSAVE','not executed: OSXSAVE clear',
        'XGETBV failed','subleaves above 2 not read','read per logical processor','not read (not AMD/Hygon, absent, or TopologyExtensions clear)',
        'processor groups not readable','current affinity not readable; no processor was visited','complete','time cap reached',
        'logical-processor cap reached','processor-group cap reached','output cap reached','topology subleaf cap reached'}


def validate(payload):
    """Only known keys and fixed messages, bounded numeric facts and hex bitfields leave this optional stage."""
    if not isinstance(payload, dict) or payload.get('schema') != SCHEMA or not isinstance(payload.get('basic'), dict) or not isinstance(payload.get('per_logical_processor'), dict) or type(payload.get('truncated')) is not bool:
        return False
    def visit(value, key='', depth=0):
        if depth > 12: return False
        if isinstance(value, dict): return all(k in KEYS and visit(v,k,depth+1) for k,v in value.items())
        if isinstance(value, list):
            cap = {'processors':512,'groups':32,'domains':8,'subleaves':3}.get(key,0)
            return len(value) <= cap and all(visit(v,key,depth+1) for v in value)
        if key == 'vendor': return value in VENDORS if isinstance(value,str) else False
        if key == 'schema': return value == SCHEMA
        if isinstance(value,str): return value in TEXT or bool(re.fullmatch(r'0x[0-9A-F]{1,16}',value))
        if type(value) is bool: return key in {'truncated','affinity_restored','os_enabled_avx','os_enabled_avx512','partial'}
        maximum={'group':65535,'bit':63,'shift':31,'active':64,'visited':512,'affinity_refused':512,'location_unavailable':512,'stepping':15,'family':4095,'model':4095,'hypervisor_bit':1,'cpu_reports_avx':1,'cpu_reports_avx512f':1}.get(key,0xffffffff)
        return type(value) is int and 0 <= value <= maximum
    return visit(payload)


def cpu_native():
    """Called only in the disposable Job-contained capture worker, using the adjacent packaged helper and pin."""
    if sys.platform != 'win32': raise dm.ObservationUnavailable('CPUID helper requires Windows')
    if not job_guard.ready(): raise dm.ObservationUnavailable('CPUID helper containment unavailable; not started')
    root = Path(__file__).resolve().parent.parent / 'bin'
    executable, pin = root / 'nm_cpuinfo.exe', root / 'cpu-helper.json'
    try:
        if pin.is_symlink() or not pin.is_file() or pin.stat().st_size > 4096: raise ValueError('missing bounded pin')
        metadata = json.loads(pin.read_bytes())
        expected = metadata.get('sha256')
        if metadata.get('schema') != 'nullmoth-cpu-helper/1' or not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected): raise ValueError('invalid pin')
        if not executable.is_file() or not 0 < executable.stat().st_size <= 4 * 1024 * 1024: raise ValueError('missing bounded executable')
        with hwcapture._system_file(str(executable)):
            with executable.open('rb') as stream: digest = hashlib.file_digest(stream,'sha256').hexdigest()
            if digest != expected: raise ValueError('hash mismatch')
            data, code, reason = job_guard.run_bounded([str(executable)], timeout=STAGE_TIMEOUT, maximum=MAX_OUTPUT)
        if reason: raise dm.ObservationUnavailable(reason)
        if code: raise dm.ObservationUnavailable('CPUID helper failed (exit %d)' % code)
        payload = json.loads(data)
        if not validate(payload): raise ValueError('output allow-list refusal')
    except dm.ObservationUnavailable: raise
    except Exception as error: raise dm.ObservationUnavailable('CPUID helper unavailable (%s)' % type(error).__name__) from None
    errors = []
    per = payload['per_logical_processor']
    if payload['truncated']: errors.append('CPUID output cap reached')
    if per.get('status') == 'unavailable': errors.append('Per-processor CPUID unavailable')
    if per.get('stopped') not in (None,'complete'): errors.append('CPUID sampling partial: '+per['stopped'])
    if per.get('affinity_refused'): errors.append('CPUID affinity refused for %d logical processors' % per['affinity_refused'])
    if per.get('location_unavailable'): errors.append('CPUID actual location unavailable for %d logical processors' % per['location_unavailable'])
    if payload.get('topology',{}).get('partial') or any(item.get('topology',{}).get('partial') for item in per.get('processors',[])): errors.append('CPUID topology subleaf cap reached')
    if per.get('affinity_restored') is False: errors.append('CPUID helper thread affinity restoration was not verified; helper has exited')
    return payload, errors
