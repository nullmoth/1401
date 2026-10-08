"""Atomic, bounded evidence for one explicit Check this PC run; no network or native API calls when reading."""
import hashlib
import json
import os
from pathlib import Path
import re
import uuid
from datetime import datetime, timezone
from . import hwcapture, report

RECEIPT = 'scan-evidence.json'
PARTIAL = 'scan-partial.json'
SCHEMA = 'nullmoth-scan-evidence/1'
MAX_BYTES = 2 * 1024 * 1024
RUN_ID = re.compile(r'^[0-9a-f]{32}$')


def _read(path, maximum=MAX_BYTES):
    path = Path(path)
    if path.is_symlink(): return None
    try:
        if not path.is_file() or path.stat().st_size > maximum: return None
        with path.open('rb') as stream:
            payload = stream.read(maximum + 1)
        if len(payload) > maximum: return None
        value = json.loads(payload)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError): return None


def _atomic(path, value):
    data = json.dumps(value, ensure_ascii=True).encode('utf-8')
    if len(data) > MAX_BYTES: raise ValueError('scan evidence exceeded its bounded size')
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        try: temporary.chmod(0o600)
        except OSError: pass
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def begin(directory, run_id=None):
    """Require a fresh output directory; previous reports or ACPI can never become this scan's inputs."""
    path = Path(directory)
    token = run_id or uuid.uuid4().hex
    if not isinstance(token, str) or not RUN_ID.fullmatch(token): raise ValueError('invalid scan run token')
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or any((path / name).exists() for name in ('Report.json', 'ACPI', RECEIPT, PARTIAL)):
        raise ValueError('scan output already contains evidence; use a fresh directory so prior hardware cannot be reused')
    value = {'schema': SCHEMA, 'run_id': token, 'phase': 'inventory', 'scan_status': 'in_progress',
             'started_utc': datetime.now(timezone.utc).isoformat(), 'identity_binding': 'one local scan run; not physical hardware qualification', 'report_sha256': None,
             'hardware_summary': {}, 'capture': hwcapture.empty_native('inventory has not completed'), 'acpi_fingerprints': []}
    _atomic(path / RECEIPT, value)
    return token


def _current(directory, token):
    value = _read(Path(directory) / RECEIPT)
    if value and value.get('schema') == SCHEMA and value.get('run_id') == token: return value
    raise ValueError('scan evidence run binding missing or changed')


def save_inventory(directory, token, capture):
    value = _current(directory, token)
    # Reserve space for the sanitized Sniffer evidence and run metadata, without silently discarding native facts.
    value['capture'] = hwcapture._bounded_payload(capture, maximum=MAX_BYTES - 256 * 1024)
    value['phase'] = 'sniffer'
    _atomic(Path(directory) / RECEIPT, value)


def save_partial(directory, token, hardware):
    """A failed upstream step may leave useful raw sections; export only the same privacy allow-list as build logs."""
    try:
        _current(directory, token)
        summary = report.diagnostic_hardware(hardware)
        value = {'schema': SCHEMA, 'run_id': token, 'hardware_summary': summary}
        while len(json.dumps(value, ensure_ascii=True).encode()) > 240 * 1024:
            lists = [key for key, section in summary.items() if isinstance(section, list) and section]
            if not lists:
                value['hardware_summary'] = {}
                break
            for key in lists: summary[key] = summary[key][:len(summary[key]) // 2]
            value['summary_status'] = 'partial; section lists truncated to the evidence size limit'
        _atomic(Path(directory) / PARTIAL, value)
    except (OSError, ValueError, TypeError):
        pass  # Diagnostics cannot alter the upstream scan outcome.


def finish(directory, token, ok, error_type=None):
    value = _current(directory, token)
    partial = _read(Path(directory) / PARTIAL)
    if partial and partial.get('schema') == SCHEMA and partial.get('run_id') == token:
        value['hardware_summary'] = partial.get('hardware_summary') or {}
        if partial.get('summary_status'): value['summary_status'] = partial['summary_status']
    report_path = Path(directory) / 'Report.json'
    if not report_path.is_symlink():
        try:
            if not report_path.is_file() or report_path.stat().st_size > 16 * 1024 * 1024: raise OSError('report not a bounded regular file')
            with report_path.open('rb') as stream: data = stream.read(16 * 1024 * 1024 + 1)
            if len(data) <= 16 * 1024 * 1024 and isinstance(json.loads(data), dict):
                value['report_sha256'] = hashlib.sha256(data).hexdigest()
        except (OSError, ValueError): pass
    value['acpi_fingerprints'] = report.acpi_fingerprints(Path(directory) / 'ACPI')
    value['completed_utc'] = datetime.now(timezone.utc).isoformat()
    value['scan_status'] = 'complete' if ok else 'failed'
    value['phase'] = 'complete'
    if error_type: value['failure_type'] = str(error_type)[:64]
    _atomic(Path(directory) / RECEIPT, value)
    return value


def load_for_report(report_path, raw_hardware=None):
    """No native calls. Imported or modified reports cannot inherit a different scan's live inventory."""
    path = Path(report_path)
    value = _read(path.parent / RECEIPT)
    valid = value and value.get('schema') == SCHEMA and RUN_ID.fullmatch(str(value.get('run_id', ''))) and value.get('phase') == 'complete'
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024: raise OSError('report not a bounded regular file')
        digest_value = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''): digest_value.update(chunk)
        digest = digest_value.hexdigest()
        valid = valid and value.get('report_sha256') == digest
    except OSError: valid = False
    capture = value.get('capture') if valid else None
    out = capture if isinstance(capture, dict) else hwcapture.empty_native('no exact scan-bound saved inventory for this report')
    out = dict(out)
    try: out['gpus'] = hwcapture.gpu_inventory(raw_hardware or {})
    except Exception: out['gpus'] = []
    out['scan_binding'] = {'status': 'same_scan_run' if valid else 'unavailable',
                           'meaning': 'saved Windows observations; not current-host or macOS driver qualification'}
    if valid: out['scan_binding'].update({'run_id': value['run_id'], 'scan_status': value.get('scan_status')})
    return out
