#!/usr/bin/env python3
"""The Mac app's verdict when all four kexts are loaded but macOS lists no NVIDIA Metal device: it says the driver is
loaded and what to do on a laptop without a MUX, not "installed but not running" (#98). Runs the production render()."""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
node = shutil.which('node')
if not node:
    raise SystemExit('Node.js is required for web view regression tests')
fixture = r'''
const fs = require('fs'), vm = require('vm');
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {textContent:'', innerHTML:'', disabled:false, hidden:false, value:'auto',
    options:[], classList:{toggle(){}}, insertAdjacentHTML(_w, t){this.innerHTML += t;}, querySelectorAll(){return [];}});
  return elements.get(id);
}
const context = {document:{getElementById:element, querySelectorAll(){return [];}},
  window:{webkit:{messageHandlers:{nm:{postMessage(){}}}}}, setTimeout};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), context);
const out = {};
for (const [name, kexts, metal] of [['loaded', 4, []], ['running', 4, ['NVIDIA GeForce RTX 3060 Laptop GPU']], ['off', 0, []]]) {
  elements.clear();
  context.render({version:'2.5.5', gpus:[{name:'RTX 3060 Laptop GPU', vendor:'10DE', supported:true, tested:false}],
    kexts, metal, files:true, major:26, macos:'26.7.1', arch:'x86_64', translated:false, opencore:'1.0.8',
    packages:[], hwModel:'MacBookPro16,1', gpuHiding:[], hiddenNvidia:[]});
  out[name] = {verdict: element('verdict').innerHTML, mac: element('mac').innerHTML};
}
console.log(JSON.stringify(out));
'''
fails = 0


def check(name, ok, detail=''):
    global fails
    print(('ok   ' if ok else 'FAIL ') + name + (f' ({detail})' if detail else ''))
    fails += 0 if ok else 1


with tempfile.TemporaryDirectory() as d:
    f = pathlib.Path(d) / 'fixture.js'
    f.write_text(fixture)
    r = subprocess.run([node, str(f), str(root / 'Resources/app.js')], capture_output=True, text=True, timeout=60)
    if r.returncode:
        print('FAIL the fixture ran (' + r.stderr.strip()[-400:] + ')')
        sys.exit(1)
    out = json.loads(r.stdout.strip().splitlines()[-1])

v = out['loaded']['verdict']
check('kexts loaded without a Metal device: says it is loaded', 'loaded, but macOS shows no NVIDIA Metal device' in v, v[:120])
check('... and names the no-MUX laptop case', 'no MUX switch' in v and "HDMI or DisplayPort" in v)
check('... and does not claim it is not running', 'installed but not running' not in v)
check('... and the status row says loaded', 'loaded, no NVIDIA Metal device yet' in out['loaded']['mac'])
check('control: nothing loaded keeps "installed but not running"', 'installed but not running' in out['off']['verdict'])
check('control: a running driver says it is running', 'components are loaded and an NVIDIA Metal device is visible'
      in out['running']['verdict'])
sys.exit(1 if fails else 0)
