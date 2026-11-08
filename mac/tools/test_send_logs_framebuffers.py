#!/usr/bin/env python3
"""Sent logs name the framebuffer behind WindowServer's one-time "Driver Error: FB: x of y opened" abort.

CoreDisplay's line says only "CGXMappedDisplayStart: IOServiceOpen failed(0xe00002c7), index(0)". IOGraphics logs the
failing framebuffer with its registry id and class, but that kernel line came from IOGraphicsFamily, which no
collector filter matched. The collector now keeps the graphics family's kernel lines in each crash window and lists
every framebuffer (class, registry id, dependent index, config) in driver-state.txt, so the two can be joined. The
census awk runs here on an ioreg fixture. The negative control is the collector before this change."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "Resources/nullmoth-setup.sh"
fails = 0


def arm(name, ok, detail=""):
    global fails
    fails += not ok
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f" ({detail.strip()[-300:]})"))


IOREG = '''+-o AMDFramebufferSI  <class AMDFramebuffer, id 0x100000775, registered, matched, active, busy 0 (8 ms), retain 16>
      "IOFBDependentIndex" = 0
      "IOFBDependentID" = 4294968404
      "IOFBTransform" = 0
      "IOFBGammaWidth" = 12
+-o display0  <class NVRMNVDAFramebuffer, id 0x1000009a1, registered, matched, active, busy 0 (2 ms), retain 12>
      "connected-displays" = 1
      "IOFBCurrentPixelCount" = 8294400
      "IOFBMemorySize" = 268435456
+-o display  <class IONDRVFramebuffer, id 0x100000412, registered, matched, active, busy 0 (0 ms), retain 9>
      "AAPL,ndrv-dev" = Yes
'''


def checks(src):
    out = {}
    out["census"] = "== framebuffers" in src and "<class [A-Za-z0-9_]+, id 0x[0-9a-f]+" in src
    out["family"] = 'sender == "IOGraphicsFamily"' in src and "newUserClient" in src
    out["wsloop"] = "nullmoth-ws-loop" in src
    return out


src = SRC.read_text()
got = checks(src)
arm("the framebuffer census names each one's class and registry id", got["census"])
arm("each crash window keeps the graphics family's kernel lines", got["family"])
arm("driver-state.txt says when the boot guard turned the driver off for a WindowServer loop", got["wsloop"])
arm("the script still parses", subprocess.run(["/bin/bash", "-n", str(SRC)]).returncode == 0)

start = src.index('echo; echo "== framebuffers (which driver owns each screen)"')
line = src[start:src.index("\n", src.index("\n", src.index("ioreg -r -c IOFramebuffer", start)) - 1)]
pat = line[line.index("grep -aoE '") + len("grep -aoE '"):line.rindex("'")]
p = subprocess.run(["/usr/bin/grep", "-aoE", pat], input=IOREG, capture_output=True, text=True, timeout=30, env={"LC_ALL": "C"})
o = p.stdout
arm("the census names each framebuffer's class and registry id",
    all(x in o for x in ("class AMDFramebuffer, id 0x100000775", "class NVRMNVDAFramebuffer, id 0x1000009a1",
                         "class IONDRVFramebuffer, id 0x100000412")), o + p.stderr)
arm("  with the properties that tell an offline or never-opened framebuffer",
    '"IOFBDependentIndex" = 0' in o and '"connected-displays" = 1' in o and '"AAPL,ndrv-dev" = Yes' in o, o)
arm("  and without the rest", "IOFBGammaWidth" not in o and "IOFBMemorySize" not in o, o)

old = subprocess.run(["git", "-C", str(ROOT), "show", "003c087:mac/Resources/nullmoth-setup.sh"], capture_output=True, text=True)
if old.returncode == 0:
    g = checks(old.stdout)
    arm("negative control: the 2.8 collector (003c087) has neither the class/id census nor the family lines",
        not g["census"] and not g["family"], str(g))
else:
    arm("negative control: 003c087's collector is readable", False, old.stderr)

print(f"{fails} failed")
sys.exit(1 if fails else 0)
