"""Preserve disassembler failures that the upstream loader otherwise discards."""
import contextlib
import os
import re


def clean(text):
    text = str(text)
    home = os.path.expanduser('~')
    if len(home) > 3:
        text = text.replace(home, '%USERPROFILE%')
    text = re.sub(r'(?i)[A-Z]:\\Users\\[^\\\s]+', lambda m: '%USERPROFILE%', text)
    return text[:4096]


@contextlib.contextmanager
def capture(dsdt, records):
    runner = dsdt.r
    original = runner.run
    executable = os.path.normcase(os.path.abspath(dsdt.iasl))

    def run(command, *args, **kwargs):
        result = original(command, *args, **kwargs)
        argv = command.get('args', []) if isinstance(command, dict) else []
        if (argv and isinstance(argv[0], str) and
                os.path.normcase(os.path.abspath(argv[0])) == executable and
                isinstance(result, (list, tuple)) and len(result) >= 3 and result[2] != 0 and
                len(records) < 8):
            entry = {'tool': 'iasl', 'exit_code': result[2],
                     'tables': [os.path.basename(a) for a in argv[1:] if isinstance(a, str) and a.lower().endswith(('.aml', '.dat'))],
                     'stdout': clean(result[0]), 'stderr': clean(result[1])}
            records.append(entry)
            print('ACPI disassembler exit {}: {}'.format(entry['exit_code'], ', '.join(entry['tables'])))
            print(entry['stderr'] or entry['stdout'])
        return result

    runner.run = run
    try:
        yield
    finally:
        runner.run = original
