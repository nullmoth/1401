#!/usr/bin/env python3
"""Cancelling the Tahoe preparation on a Mac it never ran on ends "nothing to cancel" instead of a false "this driver has
no kexts for macOS 15" stop. Runs the setup script's own guard with stand-in config, NVRAM and pending file; a parked
driver or a pending file still goes on to the real cancel."""
import os
import pathlib
import subprocess
import sys
import tempfile

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
src = (root / 'Resources/nullmoth-setup.sh').read_text()
start = src.index('    # Cancel on a Mac the Tahoe preparation never ran on')
end = src.index('    . "$PEND" 2>/dev/null', start)
guard = src[start:end]
fails = 0


def check(name, ok, detail=''):
    global fails
    print(('ok   ' if ok else 'FAIL ') + name + (f' ({detail})' if detail else ''))
    fails += not ok


def run(upd, config_args, nvram_args, pending):
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        (d / 'bin').mkdir()
        (d / 'bin/nvram').write_text(f'#!/bin/bash\nprintf "boot-args\\t{nvram_args}\\n"\n')
        os.chmod(d / 'bin/nvram', 0o755)
        pend = d / 'update-pending'
        if pending:
            pend.write_text('FROM=15\n')
        script = (f'UPD={upd}; PEND="{pend}"; B=GUID\n'
                  f'get() {{ echo "{config_args}"; }}\nok() {{ echo "OK $*"; }}\ncleanup() {{ :; }}\n'
                  + guard + 'echo "WENT ON"\n')
        r = subprocess.run(['/bin/bash', '-c', script], capture_output=True, text=True,
                           env=dict(os.environ, PATH=f'{d}/bin:/usr/bin:/bin'), timeout=30)
        return r.stdout + r.stderr


out = run('cancel', 'nvfb=1 nvaccel=1', 'nvfb=1 nvaccel=1', pending=False)
check('cancel with nothing prepared ends cleanly and says so', 'nothing to cancel' in out and 'RESULT ok' in out
      and 'WENT ON' not in out, out.strip())
out = run('cancel', 'nvfb=1 nvaccel=1', 'nvfb=1 -nvoff', pending=False)
check('a driver parked in NVRAM still goes on to the real cancel', 'WENT ON' in out and 'nothing to cancel' not in out, out.strip())
out = run('cancel', 'nvfb=1 -nvoff', '', pending=False)
check('a driver parked in the config still goes on to the real cancel', 'WENT ON' in out, out.strip())
out = run('cancel', 'nvfb=1', 'nvfb=1', pending=True)
check('a pending update still goes on to the real cancel', 'WENT ON' in out, out.strip())
out = run('finish', 'nvfb=1', 'nvfb=1', pending=False)
check('finish is never skipped by this guard', 'WENT ON' in out, out.strip())
out = run('cancel', 'nvfb=1 -nvoffx', 'nvfb=1', pending=False)
check('a different argument that only starts with -nvoff does not count as parked', 'nothing to cancel' in out, out.strip())
sys.exit(1 if fails else 0)
