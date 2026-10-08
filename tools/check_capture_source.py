"""Validate capture source with the actual Windows APIs, separately from release assets."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import platform
import subprocess
import re
import sys
import unittest


def frames(text):
    out = []
    for line in text.splitlines():
        m = re.match(r'\s*File "([^"]+)", line (\d+), in ([\w<>]+)', line)
        if m:
            out.append({'file': m[1].replace('\\', '/').rsplit('/', 1)[-1], 'line': int(m[2]), 'function': m[3]})
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = {'ok': False, 'scope': 'Windows source collector ABI, read-only OS APIs and synthetic vendor bindings; '
                                  'no packaged application, USB writes, installation or GPU workload qualification.'}
    step = 'runtime platform'
    try:
        if platform.system() != 'Windows' or sys.version_info[:2] != (3, 12):
            raise RuntimeError('This check requires installed Python 3.12 on Windows.')
        repo = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(repo))
        from check_capture_native import verify_capture_native
        step = 'native Windows ABI and OS APIs'
        result['native_capture'] = {}
        verify_capture_native(repo, args.output, result['native_capture'])
        step = 'capture regression and real ctypes stand-in tests'
        suite = unittest.defaultTestLoader.loadTestsFromNames([
            'tests.test_hwcapture', 'tests.test_capture_safety', 'tests.test_capture_completeness',
            'tests.test_devicemap', 'tests.test_devicemap_native', 'tests.test_scan_evidence', 'tests.test_fwres', 'tests.test_cpu_core', 'tests.test_cpunative', 'tests.test_peripherals',
            'tests.test_downloads', 'tests.test_downloads_diagnostics', 'tests.test_dependency_cache'])
        log = io.StringIO()
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            checked = unittest.TextTestRunner(stream=log, verbosity=1).run(suite)
        result['regression_tests'] = {'run': checked.testsRun, 'failures': len(checked.failures),
                                      'errors': len(checked.errors), 'skipped': len(checked.skipped)}
        result['failure_locations'] = [{'test_id': case.id(), 'kind': kind, 'frames': frames(trace)}
                                       for kind, failures in [('failure', checked.failures), ('error', checked.errors)]
                                       for case, trace in failures]
        if not checked.wasSuccessful() or checked.skipped:
            raise RuntimeError('Windows capture regressions did not all pass.')
        result['ok'] = True
    except Exception as error:
        result['failure'] = {'step': step, 'error_type': type(error).__name__,
                             'frames': frames(__import__('traceback').format_exc())}
        if isinstance(error, subprocess.CalledProcessError):
            diagnostics = []
            for stream in (error.stdout, error.stderr):
                if not stream: continue
                content = stream.decode('utf-8', 'replace') if isinstance(stream, bytes) else str(stream)
                for line in content.splitlines():
                    match = re.search(r'\b(?:fatal error|error|warning) ((?:C|CS|LNK)\d+): (.*)', line)
                    if not match: continue
                    # Source/compiler symbols only: never publish arbitrary diagnostic paths or command lines.
                    symbols = re.findall(r'\b(?:DXGI|D3D12|DISPLAYCONFIG|SP_|DEVPROP|LUID|GUID|IID_|IUnknown|IDXGI|ID3D12|DEVPKEY|POWER_|MAX_|ERROR_|REG_|LOAD_|CR_)[A-Za-z0-9_]*\b', match[2])
                    diagnostics.append({'code': match[1], 'symbols': symbols[:16]})
            result['failure']['compiler_diagnostics'] = diagnostics[:32]
            result['failure']['command_exit'] = error.returncode
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['ok'] else 1


if __name__ == '__main__': raise SystemExit(main())
