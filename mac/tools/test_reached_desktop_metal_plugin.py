#!/usr/bin/env python3
"""The first-login report says whether the NVIDIA accelerator offers its Metal plugin (MetalPluginName), so a
"Metal device: no" report splits into "the accelerator withheld the plugin" (kernel side, headless check) and "the
plugin was offered and macOS refused it" (W2.3: ~220 hybrid laptops with the driver loaded and no Metal device)."""
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
fails = 0


def arm(name, ok, detail=""):
    global fails
    fails += not ok
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f" ({str(detail).strip()[-400:]})"))


harness_src = (ROOT / "tools/test_reached_desktop.py").read_text()
stubs = harness_src[harness_src.index("harness = r'''") + len("harness = r'''"):harness_src.index("// (a) no consent")]
checks = r'''
let named = "+-o NVAccel  <class NVAccel, id 0x10000042f, registered, matched, active, busy 0 (0 ms), retain 12>\n    {\n      \"MetalPluginName\" = \"../../../Library/GPUBundles/NVMTLDriver\"\n      \"MetalPluginClassName\" = \"NVMTLDevice\"\n    }\n"
let withheld = "+-o NVAccel  <class NVAccel, id 0x10000042f, registered, matched, active, busy 0 (0 ms), retain 12>\n    {\n      \"MetalPluginClassName\" = \"NVMTLDevice\"\n    }\n"
print("named=" + ReachedDesktop.metalPluginLine(ioreg: named))
print("withheld=" + ReachedDesktop.metalPluginLine(ioreg: withheld))
print("none=" + ReachedDesktop.metalPluginLine(ioreg: ""))
'''
with tempfile.TemporaryDirectory() as home:
    d = pathlib.Path(home)
    (d / "main.swift").write_text(stubs + checks)
    c = subprocess.run(["xcrun", "swiftc", "-Onone", str(ROOT / "Sources/ReachedDesktop.swift"), str(d / "main.swift"),
                        "-o", str(d / "t")], capture_output=True, text=True, timeout=600)
    out = subprocess.run([str(d / "t")], capture_output=True, text=True, timeout=60,
                         env={"HOME": str(d), "PATH": "/usr/bin:/bin"}).stdout if c.returncode == 0 else c.stderr
vals = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
arm("an accelerator naming its plugin reads offered", vals.get("named") == "NVIDIA Metal plugin offered: yes (MetalPluginName set)", out)
arm("a withheld plugin name reads withheld", vals.get("withheld") == "NVIDIA Metal plugin offered: no (MetalPluginName withheld)", out)
arm("no accelerator at all reads no accelerator, not withheld", vals.get("none") == "NVIDIA Metal plugin offered: no accelerator", out)
rd = (ROOT / "Sources/ReachedDesktop.swift").read_text()
arm("the summary carries the line right after the driver-loaded line",
    rd.index('NVIDIA driver loaded (com.nullmoth)') < rd.index('s += metalPluginLine(ioreg: sh("/usr/sbin/ioreg", ["-r", "-c", "NVAccel"'))
print(f"{fails} failed")
sys.exit(1 if fails else 0)
