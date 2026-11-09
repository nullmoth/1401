#!/usr/bin/env python3
"""Send logs on macOS 27 collects the macOS 27 driver's own sources, and says why for each one it cannot read.

macOS 27 runs the driver through a bring-up that 15 and 26 do not have (NVRM injected by OpenCore, an auxiliary kernel
collection, the display hand-over at boot, an Intel host for arm64-only programs). Before this change the collector read
none of it, so a macOS 27 report could not tell a failed display hand-over from a missing kernel collection.

The collector's macOS 27 functions run here, extracted from nullmoth-setup.sh, against two fixture Macs: a healthy one
and a broken one (go(2) failed, start guard struck, collection not immutable, no x86_64 dyld cache, an unreadable log,
missing logs). Every system command is a stub; one stub hangs to prove the commands are bounded. The negative control
is the collector before this change, which has no macOS 27 source at all."""
import os
import pathlib
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "Resources/nullmoth-setup.sh"
CAPTURE = ROOT / "Resources/nullmoth-log-capture.sh"
fails = 0


def arm(name, ok, detail=""):
    global fails
    fails += not ok
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f" ({str(detail).strip()[-400:]})"))


def between(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i) + len(end)]


src = SRC.read_text()
block = between(src, "# --- macOS 27 sources ---", "# --- end macOS 27 sources ---")
bounded = between(src, "lshow() {  # <seconds> <log show arguments...>", "  return $rc\n}\n")
bounded += between(src, "bounded() {  # <seconds> <command...>", "  return $rc\n}\n")

GOOD_IOREG = '''+-o NVRM  <class NVRM, id 0x1000002f5, registered, matched, active, busy 0 (0 ms), retain 9>
    "nvrm-autogo" = "up"
    "nvrm-autogo-settle-ms" = 500
    "nvrm-boot-raster" = "head0 60.019Hz"
'''
BAD_IOREG = GOOD_IOREG.replace('"up"', '"go(2) failed"')
BT = '''Bluetooth:

      Bluetooth Controller:
          Address: 11:22:33:44:55:66
          State: On
          Chipset: RTL8922AE
          Discoverable: Off
          Firmware Version: v0.1
          Transport: USB
          Vendor ID: 0x0BDA
      Not Connected:
          Kitchen Speaker:
              Address: AA:BB:CC:DD:EE:FF
'''
WIFI = '''Wi-Fi:

      Software Versions:
          CoreWLAN: 16.0
      Interfaces:
        en1:
          Card Type: Wi-Fi  (0x8086, 0x0094)
          Firmware Version: itlwm 2.4
          Status: Connected
          Supported PHY Modes: 802.11 a/b/g/n/ac/ax
          Current Network Information:
            HomeNetSSID:
              PHY Mode: 802.11ax
          Other Local Wi-Fi Networks:
            NeighbourNet:
              PHY Mode: 802.11n
'''


def stubs(kind):
    good = kind == "good"
    return f'''
sw_vers() {{ case "$1" in -productVersion) echo 27.2;; -buildVersion) echo 26B123;; esac; }}
ioreg() {{ {dict(good="printf '%s' \"$GOOD_IOREG\"", bad="printf '%s' \"$BAD_IOREG\"", hang="exec sleep 100")[kind]}; }}
sysctl() {{
  if [ "$1" = -a ]; then printf 'kern.ostype: Darwin\\na2xa.adopt_adopted: 412\\na2xa.adopt_refused_off: {0 if good else 1144}\\n'; return 0; fi
  echo "debug.nvaccel_heads_published: {1 if good else 0}"; echo "debug.nvaccelfb: {4 if good else 0}"; }}
nvram() {{ case "$1" in *nullmoth-nv-starts) printf '%s\\t%s\\n' "$1" "{'%01' if good else '%02'}";;
                       *nullmoth-nv-ok) printf '%s\\t1\\n' "$1";; *) echo "nvram: Error getting variable" >&2; return 1;; esac; }}
launchctl() {{ case "$1" in
  list) printf 'PID\\tStatus\\tLabel\\n471\\t0\\tcom.nullmoth.nvload\\n';;
  print) case "$2" in system/com.nullmoth.nvload) printf 'system/com.nullmoth.nvload = {{\\n\\tstate = running\\n\\tpid = 471\\n\\tlast exit code = 0\\n}}\\n';;
                      system/com.apple.bluetoothd) printf '\\tstate = running\\n\\tpid = 88\\n';;
                      *) echo "Could not find service" >&2; return 113;; esac;;
esac; }}
kmutil() {{ {"printf '  1 0 0xffffff8001 0x1 0x1 com.nullmoth.NVRM (3.0) AAAA <1>\\n  2 0 0xffffff8002 0x1 0x1 com.nullmoth.NVRMFB (3.0) BBBB <1>\\n  3 0 0xffffff8003 0x1 0x1 com.nullmoth.NVAccel (3.0) CCCC <1>\\n  4 0 0xffffff8004 0x1 0x1 com.nullmoth.NVRMAGDC (3.0) DDDD <1>\\n  5 0 0xffffff8005 0x1 0x1 com.nullmoth.NMXAudio (3.0) EEEE <1>\\n  6 0 0xffffff8006 0x1 0x1 com.nullmoth.a2x-exec-hook (1.0) FFFF <1>\\n'" if good else "echo 'Error: unsupported arch: x86_64' >&2; return 71"}; }}
kextstat() {{ printf '  1 0 0xffffff8001 0x1 0x1 com.nullmoth.NVRM (3.0) AAAA <1>\\n'; }}
m27_flags() {{ echo {"schg" if good else "-"}; }}
lshow() {{ {"echo 'Timestamp'" if good else "echo '2026-11-08 10:00:01 bluetoothd: kPermissionErr App ID not approved: .a2xhost-mac'"}; }}
system_profiler() {{ case "$1" in SPBluetoothDataType) printf '%s' "$BT";; SPAirPortDataType) printf '%s' "$WIFI";; esac; }}
networksetup() {{ printf 'Hardware Port: Wi-Fi\\nDevice: en1\\nEthernet Address: 11:22:33:44:55:77\\n'; }}
shasum() {{ echo "abc123  $2"; }}
id() {{ {"echo 0" if kind == "good" else "echo 501"}; }}
dmesg() {{ printf '[ 12.0]: NVRM: auto-go: go(2) -> 0x0\n[ 13.0]: unrelated line\n'; }}
'''


def fixture(root, good):
    r = pathlib.Path(root)
    for d in ["Library/LaunchDaemons", "Library/NullMoth/bringup", "Library/KernelCollections", "Library/Extensions",
              "var/tmp", "var/log", "System/Volumes/Preboot/Cryptexes/OS/System/Library/dyld",
              "System/Volumes/Preboot/Cryptexes/Rosetta/System/Library/dyld"]:
        (r / d).mkdir(parents=True, exist_ok=True)
    (r / "Library/LaunchDaemons/com.nullmoth.nvload.plist").write_text("<plist/>")
    (r / "Library/NullMoth/bringup/nvload.sh").write_text("#!/bin/bash\n")
    (r / "Library/KernelCollections/AuxiliaryKernelExtensions.kc").write_bytes(b"kc")
    (r / "System/Volumes/Preboot/Cryptexes/OS/System/Library/dyld/dyld_shared_cache_arm64e").write_bytes(b"c")
    if good:
        (r / "System/Volumes/Preboot/Cryptexes/Rosetta/System/Library/dyld/dyld_shared_cache_x86_64").write_bytes(b"c")
        (r / "var/tmp/nvload.log").write_text("2026-11-08 03:09:58 HEALTHY: WindowServer 471 steady 30 s\n")
        (r / "var/tmp/ws-gate.log").write_text("armed\n")
        (r / "var/log/lights.log").write_text("lights off\n")
        (r / "var/log/nvrm-boot.log").write_text("nvrm boot\n")
    else:
        os.symlink("/nonexistent/dyld_shared_cache_x86_64",
                   r / "System/Volumes/Preboot/Cryptexes/Rosetta/System/Library/dyld/dyld_shared_cache_x86_64h")
        (r / "var/tmp/nvload.log").write_text("secret\n")
        os.chmod(r / "var/tmp/nvload.log", 0)
        (r / "var/tmp/ws-gate.log").write_text("")


def run(kind, fn, budget=None):
    with tempfile.TemporaryDirectory() as td:
        fixture(td, kind == "good")
        script = "set -u\n" + bounded + block + stubs(kind) + f'M27_ROOT="{td}"\n'
        if budget:
            script += f"COLLECT_DEADLINE=$(( $(date +%s) + {budget} ))\n"
        script += fn + "\n"
        env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "GOOD_IOREG": GOOD_IOREG, "BAD_IOREG": BAD_IOREG, "BT": BT, "WIFI": WIFI, "LC_ALL": "C"}
        t0 = time.time()
        p = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=120, env=env)
        try:
            os.chmod(pathlib.Path(td) / "var/tmp/nvload.log", 0o600)
        except OSError:
            pass
        return p.stdout + p.stderr, time.time() - t0


arm("the script still parses", subprocess.run(["/bin/bash", "-n", str(SRC)]).returncode == 0)
call = between(src, 'if [ "$(m27_os_major)" -ge 27 ]; then', "  fi\n")
arm("the macOS 27 sources run only on 27 or later, right after driver-state.txt",
    src.index('} > "$COLLECT/driver-state.txt" 2>&1') < src.index(call) < src.index("kernel_log_since_boot 45 30")
    and all(f in call for f in ("macos27-state.txt", "macos27-bringup-logs.txt")), call)
arm("the host-identity query leaves out log's own lines (it logs its arguments, so it matched itself on a plain Mac)",
    'process != "log" AND eventMessage CONTAINS ".a2xhost"' in block)
arm("  in both scopes (the first-login report too, not only Send logs)", "want full" not in call, call)
arm("macos27-state.txt is uploaded first among the files, before the 48-file limit can drop it",
    "driver-state.txt macos27-state.txt driver-kernel-log.txt" in CAPTURE.read_text())

g, _ = run("good", "m27_state; m27_bringup_logs")
arm("healthy 27 Mac: auto-go up, one head, guard clear", all(x in g for x in (
    "macos27: display autogo up", "macos27: heads published 1", "macos27: nv-starts guard %01")), g)
arm("  bring-up daemon state, the bring-up folder and all five NullMoth kexts plus the a2x kext",
    "state = running" in g and "nvload.sh" in g and "kext not loaded" not in g and "macos27: a2x kexts loaded 1" in g, g)
arm("  aux collection immutable, x86_64 dyld cache present, no refusals",
    "aux collection present, immutable" in g and "dyld x86_64 cache present" in g and "interpreter route refusals" not in g, g)
arm("  Bluetooth and Wi-Fi controller facts", "Chipset: RTL8922AE" in g and "Card Type: Wi-Fi" in g
    and "Bluetooth controller not found" not in g and "Wi-Fi interface not found" not in g, g)
arm("  no device names, no network names", not any(x in g for x in ("Kitchen Speaker", "HomeNetSSID", "NeighbourNet")), g)
arm("  the bring-up logs and, as root, the kernel buffer's bring-up lines only", "HEALTHY: WindowServer 471" in g
    and "lights off" in g and 'auto-go: go(2) -> 0x0' in g and "unrelated line" not in g, g)
arm("  a log nothing wrote says so", "(/var/tmp/lw-gate.log)\n(not present" in g, g)

b, _ = run("bad", "m27_state; m27_bringup_logs")
arm("broken 27 Mac: the go(2) failure is named, with no head published",
    "macos27: display autogo go(2) failed" in b and "macos27: heads published 0" in b, b)
h, secs = run("hang", "m27_state", budget=90)
arm("  a hanging ioreg is stopped by its bound, the run finishes and says auto-go is absent, never silently skipped",
    "(ioreg stopped after" in h and "macos27: display autogo absent" in h and "Card Type: Wi-Fi" in h and secs < 60, f"{secs:.1f}s {h}")
arm("  start guard struck", "macos27: nv-starts guard struck (%02)" in b, b)
arm("  kmutil refusing x86_64 falls back to kextstat and names the missing kexts",
    "reading kextstat instead" in b and "macos27: kext not loaded com.nullmoth.NVAccel" in b
    and "macos27: kext not loaded com.nullmoth.NVRM\n" not in b, b)
arm("  aux collection not immutable", "aux collection present, NOT immutable" in b, b)
arm("  dangling dyld link and no x86_64 cache", "DANGLING dyld_shared_cache_x86_64h" in b
    and "dyld cache links dangling 1" in b and "dyld x86_64 cache MISSING" in b, b)
arm("  interpreter route refusals and the host identity", "interpreter route refusals a2xa.adopt_refused_off 1144" in b
    and "running under the host identity" in b, b)
arm("  an unreadable log says why and leaks nothing", "(not readable by this user" in b and "secret" not in b, b)
arm("  an empty log says so, and the kernel buffer outside root says why it is not read",
    "(empty)" in b and "== kernel buffer: display bring-up lines\n(not readable by this user" in b and "auto-go: go(2)" not in b, b)
arm("development-only captures (m27diag) are not collected", "m27diag" not in block and "m27_boot_captures" not in block)

old = subprocess.run(["git", "-C", str(ROOT), "show", "6474c03:mac/Resources/nullmoth-setup.sh"], capture_output=True, text=True)
if old.returncode == 0:
    arm("negative control: the 2.8.1 collector (6474c03) reads no macOS 27 source",
        not any(x in old.stdout for x in ("nvrm-autogo", "nvload.log", "macos27")))
else:
    arm("negative control: 6474c03's collector is readable", False, old.stderr)

print(f"{fails} failed")
sys.exit(1 if fails else 0)
