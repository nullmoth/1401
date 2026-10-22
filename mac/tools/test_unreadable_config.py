#!/usr/bin/env python3
"""A stick's config.plist that macOS will not let 1401 read is reported as that, with the setting that fixes it, not as
an invalid plist (2.5.2 Mac setup log: "couldn't be opened because you don't have permission to view it", then "is not a
valid plist - fix it before installing"). Runs the setup script's own two lines against a readable good file, a
readable broken file, and an unreadable one."""
import os
import pathlib
import subprocess
import sys
import tempfile

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
src = (root / 'Resources/nullmoth-setup.sh').read_text()
start = src.index('cat "$C" >/dev/null 2>&1 || stop "macOS did not let 1401 read')
end = src.index('\n', src.index('plutil -lint "$C" >/dev/null || stop', start)) + 1
snippet = src[start:end]
fails = 0


def check(name, ok, detail=''):
    global fails
    print(('ok   ' if ok else 'FAIL ') + name + (f' ({detail})' if detail else ''))
    fails += not ok


def run(path):
    script = 'stop() { echo "STOP $*"; exit 1; }\nC=' + repr(str(path)) + '\n' + snippet + 'echo PASSED\n'
    return subprocess.run(['/bin/bash', '-c', script], capture_output=True, text=True, timeout=30).stdout


with tempfile.TemporaryDirectory() as d:
    d = pathlib.Path(d)
    good, bad, locked = d / 'good.plist', d / 'bad.plist', d / 'locked.plist'
    good.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict/></plist>\n')
    bad.write_text('<plist><dict><key>x</key></plist>')
    locked.write_text(good.read_text())
    os.chmod(locked, 0)
    check('a good config passes both checks', run(good).strip() == 'PASSED', run(good))
    out = run(bad)
    check('a broken config is still called an invalid plist', 'is not a valid plist' in out, out)
    if os.geteuid() == 0:
        print('skip the unreadable arm: root reads a mode-0 file')
    else:
        out = run(locked)
        check('an unreadable config says macOS did not let 1401 read it, and how to allow it',
              'macOS did not let 1401 read' in out and 'removable volumes' in out and 'not a valid plist' not in out, out)
    os.chmod(locked, 0o600)

print(f'{fails} failed')
sys.exit(1 if fails else 0)
