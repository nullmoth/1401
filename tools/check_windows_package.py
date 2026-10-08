"""Run non-destructive checks with the exact Python and executable being packaged."""
import argparse
import contextlib
import hashlib
import importlib
import importlib.metadata
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import unittest
import zipfile


def failure_frames(text):
    """Keep actionable source locations while excluding paths, values and report contents."""
    frames = []
    for line in text.splitlines():
        match = re.match(r'\s*File "([^"]+)", line (\d+), in ([\w<>]+)', line)
        if match:
            filename = match[1].replace('\\', '/').rsplit('/', 1)[-1]
            frames.append({'file': filename, 'line': int(match[2]), 'function': match[3]})
    return frames


def require_firmware_navigation(gui):
    """A prior or incomplete executable smoke cannot qualify the new guide flow."""
    if gui.get('firmware_prerequisite_navigation') is not True or gui.get('firmware_navigation_fixture_phase') != 'complete':
        raise RuntimeError('Compiled prebuild firmware guidance and refusal-return navigation did not pass.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', required=True)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--cache', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if platform.system() != 'Windows':
        raise RuntimeError('Packaged startup verification requires Windows.')
    root = Path(args.stage).resolve() / '1401'
    repo, cache = Path(args.repo).resolve(), Path(args.cache).resolve()
    app = root / 'engine/app'
    python = root / 'engine/python/python.exe'
    if Path(sys.executable).resolve() != python.resolve():
        raise RuntimeError('This check must run with the packaged portable Python.')
    inputs = json.loads((repo / 'windows/release-inputs.json').read_text())
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['OPENCORE_TEST_ZIP'] = str(cache / 'fixtures/OpenCore-1.0.8-RELEASE.zip')
    result = {'ok': False, 'scope': 'Windows packaged startup, dependency imports, regression tests and one public planning fixture; no disk writes or GPU qualification.'}
    step = 'packaged module and dependency imports'
    try:
        modules = ['p1401.engine', 'p1401.acpi_diagnostics', 'p1401.dependency_cache', 'p1401.downloads',
                   'p1401.kernel_patches', 'p1401.report', 'p1401.hwcapture', 'p1401.machine_handoff', 'p1401.cpunative', 'p1401.peripheral_caps', 'p1401.panel_guard']
        imported = []
        for name in modules:
            module = importlib.import_module(name)
            relative = Path(module.__file__).resolve().relative_to(app.resolve()).as_posix()
            imported.append(relative)
        for name in ['wmi', 'win32api', 'certifi']:
            importlib.import_module(name)
        versions = {name: importlib.metadata.version(name) for name in inputs['runtime_packages']}
        if versions != inputs['runtime_packages'] or sys.version_info[:2] != (3, 12):
            raise RuntimeError('Packaged dependency versions differ from the verified baseline.')
        result['packaged_module_imports'] = imported
        result['runtime_packages'] = versions
        result['python_version'] = platform.python_version()
        native_spec = importlib.util.spec_from_file_location('capture_native_verification', repo / 'tools/check_capture_native.py')
        native_check = importlib.util.module_from_spec(native_spec)
        native_spec.loader.exec_module(native_check)
        step = 'Windows native capture ABI and isolated worker'
        result['native_capture'] = {}
        native_check.verify_capture_native(repo, args.output, result['native_capture'])
        fixture = cache / 'fixtures' / inputs['fixture_slug']
        suite = unittest.defaultTestLoader.discover(str(repo / 'tests'), pattern='test_*.py', top_level_dir=str(repo))
        step = 'packaged regression tests'
        log = io.StringIO()
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            checks = unittest.TextTestRunner(stream=log, verbosity=1).run(suite)
        # Tests import their sibling fixtures from the reviewed repository. The
        # already loaded regular p1401 package must continue resolving to the stage.
        for name, module in list(sys.modules.items()):
            if name == 'p1401' or name.startswith('p1401.'):
                filename = getattr(module, '__file__', None)
                if filename and not Path(filename).resolve().is_relative_to(app.resolve()):
                    raise RuntimeError('Regression imports left the packaged application boundary.')
        result['regression_tests'] = {'run': checks.testsRun, 'failures': len(checks.failures),
                                      'errors': len(checks.errors), 'skipped': len(checks.skipped)}
        result['test_failure_locations'] = [{'test_id': test.id(), 'kind': kind, 'frames': failure_frames(trace)}
                                            for kind, failures in [('failure', checks.failures), ('error', checks.errors)]
                                            for test, trace in failures]
        if not checks.wasSuccessful() or checks.skipped:
            raise RuntimeError('Packaged regression checks did not all pass.')
        from p1401 import usbwriter, nullmoth
        step = 'existing USB and NVIDIA policy checks'
        with contextlib.redirect_stdout(io.StringIO()):
            usb_ok = usbwriter.selftest()
            policy_ok = nullmoth.selftest() == 0
        result['usb_policy_checks'] = {'passed': usb_ok, 'writes_executed': False}
        result['nvidia_policy_and_update_checks'] = {'passed': policy_ok, 'hardware_qualification': False}
        if not usb_ok or not policy_ok:
            raise RuntimeError('Existing USB or NVIDIA policy checks failed.')
        command = [str(python), '-B', '-m', 'p1401', 'plan', str(fixture / 'Report.json'), str(fixture / 'ACPI'), '--json']
        step = 'public planning fixture with the packaged engine'
        planned = subprocess.run(command, cwd=app, capture_output=True, encoding='utf-8', timeout=180)
        plan = json.loads(planned.stdout)
        result['planning_fixture'] = {'slug': inputs['fixture_slug'], 'ok': plan.get('ok'),
                                      'macos_version': plan.get('macos_version'), 'smbios': plan.get('smbios'),
                                      'kexts': plan.get('kexts'), 'full_efi_build_executed': False}
        result['fixture_proof'] = json.loads((cache / 'fixtures/fixture-proof.json').read_text())
        if planned.returncode != 0 or plan.get('ok') is not True:
            raise RuntimeError('The packaged engine planning smoke did not pass.')
        gui_path = Path(args.output).with_name('gui-verification.json')
        step = 'actual packaged executable startup and version'
        process = subprocess.run([str(root / '1401.exe'), '--verify-package', str(gui_path)], cwd=root, timeout=30)
        gui = json.loads(gui_path.read_text())
        result['gui'] = gui
        result['version'] = gui.get('assembly_version')
        expected = (repo / 'windows/App/App.csproj').read_text().split('<Version>')[1].split('</Version>')[0]
        if process.returncode != 0 or gui.get('ok') is not True or gui.get('assembly_version') != expected:
            raise RuntimeError('The actual packaged application startup/version check failed.')
        if gui.get('scan_evidence_binding') is not True:
            raise RuntimeError('Compiled scan evidence binding did not pass.')
        if gui.get('fresh_upload_batches') is not True:
            raise RuntimeError('Compiled upload batches did not pass run-identity verification.')
        if gui.get('closed_form_log_collection_guard') is not True:
            raise RuntimeError('Log collection on a closed application window was not safely skipped.')
        if gui.get('support_notices_visible') is not True:
            raise RuntimeError('Laptop display and controller qualification notices were not shown in the build summary.')
        require_firmware_navigation(gui)
        if not (gui.get('product_version') or '').startswith(expected):
            raise RuntimeError('The packaged executable product version differs.')
        changed_runtime = []
        step = 'portable runtime integrity after verification'
        with zipfile.ZipFile(cache / 'baseline.zip') as baseline:
            for entry in baseline.infolist():
                if not entry.is_dir() and entry.filename.startswith('1401/engine/python/'):
                    current = root.parent / entry.filename
                    if not current.is_file() or hashlib.sha256(current.read_bytes()).digest() != hashlib.sha256(baseline.read(entry)).digest():
                        changed_runtime.append(entry.filename)
        if changed_runtime:
            raise RuntimeError('The verified portable Python runtime changed during verification.')
        result['portable_runtime_unchanged'] = True
        result['candidate_files'] = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                     for path in sorted(root.rglob('*')) if path.is_file()}
        result['ok'] = True
    except Exception as error:
        result['error_type'] = type(error).__name__
        result['failed_step'] = step
        import traceback
        result['failure_locations'] = failure_frames(traceback.format_exc())
        Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
        raise RuntimeError('Windows packaged verification failed: ' + type(error).__name__) from None
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print('Windows packaged verification passed; no hardware support qualification is implied.')


if __name__ == '__main__':
    main()
