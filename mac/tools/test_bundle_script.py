#!/usr/bin/env python3
"""Privileged.bundleScript runs a script from a private copy that was checked against the compiled-in hashes.

The shell it builds runs here for real, as this user, on a stand-in bundle. Arms: the script runs from the copy and not
from the bundle, bundle paths in its arguments become the copies, its exit code comes back, the copy is removed, and a
script or a sibling changed after the hashes were taken is refused without running (the case this exists for)."""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
fails = 0


def arm(name, ok, detail=''):
    global fails
    print(('ok   ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail and not ok else ''))
    fails += not ok


with tempfile.TemporaryDirectory() as td:
    td = pathlib.Path(td)
    probe = td / 'probe.swift'
    probe.write_text('''
import Foundation
let a = CommandLine.arguments
let table = try! JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: a[1]))) as! [String: String]
print(Privileged.bundleScript(a[2], Array(a[3...]), table: table))
''')
    main = td / 'main.swift'
    main.write_text(probe.read_text())
    exe = td / 'probe'
    built = subprocess.run(['xcrun', 'swiftc', '-Onone', str(ROOT / 'Sources/Privileged.swift'), str(ROOT / 'Sources/BundleHashes.swift'),
                            str(main), '-o', str(exe)], capture_output=True, text=True)
    arm('the shipping Privileged.swift compiles with a probe', built.returncode == 0, built.stderr[-400:])
    if built.returncode:
        sys.exit(1)
    res = td / 'Resources'
    res.mkdir(mode=0o755)
    os.chmod(td, 0o755)
    script = res / 'tool.sh'
    script.write_text('#!/bin/bash\nd=$(cd "$(dirname "$0")" && pwd -P); echo "ran from $d"; echo "arg $1"; cat "$1"; cat "$d/data.txt"; echo "$d" > "$2"; exit "$3"\n')
    (res / 'data.txt').write_text('sibling-good\n')
    (res / 'payload.efi').write_text('payload-good\n')

    def table():
        return {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in res.iterdir()}

    def go(tab, rc='7'):
        t = td / 'table.json'
        t.write_text(json.dumps(tab))
        where = td / 'where.txt'
        if where.exists():
            where.unlink()
        c = subprocess.run([str(exe), str(t), str(script), str(res / 'payload.efi'), str(where), rc], capture_output=True, text=True)
        assert c.returncode == 0, c.stderr
        shell = c.stdout.strip()
        return subprocess.run(['/bin/sh', '-c', 'set -C; { ' + shell + ' ; }; echo "rc=$?"'], capture_output=True, text=True), where

    good = table()
    r, where = go(good)
    arm('the script runs', 'sibling-good' in r.stdout, r.stdout + r.stderr)
    ran = next((l[9:] for l in r.stdout.splitlines() if l.startswith('ran from ')), '')
    arm('it runs from the private copy, not the bundle', ran.startswith(('/var/tmp/1401-run.', '/private/var/tmp/1401-run.')), ran)
    arm('a bundle path in its arguments points at the checked copy', f"arg {ran.replace('/private', '', 1)}/payload.efi" in r.stdout, r.stdout)
    arm('its exit code comes back', 'rc=7' in r.stdout, r.stdout)
    arm('the copy is removed afterwards', ran and not os.path.exists(ran), ran)

    script.write_text(script.read_text() + '# changed\n')
    r, where = go(good)
    arm('a script changed after the hashes were taken does not run', not where.exists() and 'were changed' in r.stdout, r.stdout + r.stderr)
    script.write_text(script.read_text().replace('# changed\n', ''))
    (res / 'payload.efi').write_text('payload-evil\n')
    r, where = go(good)
    arm('a changed file it would install stops it too', not where.exists() and 'payload-evil' not in r.stdout, r.stdout)
    (res / 'payload.efi').write_text('payload-good\n')
    r, where = go(good, '0')
    arm('negative control: put back, it runs again', where.exists() and 'rc=0' in r.stdout, r.stdout)
    r, where = go({})
    arm('a build with no hashes runs nothing', not where.exists() and 'no check for' in r.stdout, r.stdout)

print('FAILED' if fails else 'PASS')
sys.exit(1 if fails else 0)
