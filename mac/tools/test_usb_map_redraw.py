#!/usr/bin/env python3
"""The USB map's port table is redrawn only when the scan's answer changed. It used to be rebuilt every second while
watching, which closed an open plug-type list and reset plug choices on rows not yet ticked."""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
harness = r"""
const fs = require("fs"), vm = require("vm");
const draws = {};
function el(id) {
  const e = { id, textContent: "", hidden: false, disabled: false, value: "", classList: { toggle() {}, add() {}, remove() {} },
              dataset: {}, style: {}, querySelectorAll: () => [], querySelector: () => null, closest: () => null,
              addEventListener() {}, appendChild() {} };
  let html = "";
  Object.defineProperty(e, "innerHTML", { get: () => html, set: (v) => { html = v; draws[id] = (draws[id] || 0) + 1; } });
  return e;
}
const els = {};
const document = { getElementById: (id) => (els[id] = els[id] || el(id)), querySelectorAll: () => [], addEventListener() {},
                   createElement: () => el("x"), body: el("body") };
const window = { webkit: { messageHandlers: { nm: { postMessage() {} } } }, addEventListener() {} };
const ctx = { document, window, console, setTimeout, clearTimeout, setInterval, clearInterval, navigator: {}, location: {} };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[process.argv.length - 1], "utf8"), ctx);
const scan = (devs) => ({ event: "usb", data: { controllers: [{ key: "IOService:/a/XHC", controller: "XHC", vendor: "8086", device: "7AE0",
  ports: [{ name: "HS01", usb3: false, devices: devs }, { name: "SS01", usb3: true, devices: [] }] }], seen: { "IOService:/a/XHC": ["HS01"] } } });
ctx.window.NM.on(scan(["Keyboard"]));
const first = draws.ports || 0;
ctx.window.NM.on(scan(["Keyboard"]));
ctx.window.NM.on(scan(["Keyboard"]));
const same = (draws.ports || 0) - first;
ctx.window.NM.on(scan(["Keyboard", "Stick"]));
const changed = (draws.ports || 0) - first - same;
console.log(JSON.stringify({ first, same, changed }));
"""
out = subprocess.run(["node", "-e", harness, str(ROOT / "Resources/app.js")], capture_output=True, text=True, timeout=60)
fails = 0


def arm(name, ok, detail):
    global fails
    fails += not ok
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f" ({detail.strip()[-400:]})"))


try:
    import json
    r = json.loads(out.stdout.strip().splitlines()[-1])
except Exception:  # noqa: BLE001
    arm("the page script runs in the harness", False, out.stdout + out.stderr)
    sys.exit(1)
arm("the first scan draws the table", r["first"] == 1, str(r))
arm("an unchanged scan does not redraw it", r["same"] == 0, str(r))
arm("a scan with a new device redraws it", r["changed"] == 1, str(r))
print(f"{fails} failed")
sys.exit(1 if fails else 0)
