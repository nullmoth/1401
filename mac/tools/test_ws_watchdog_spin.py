#!/usr/bin/env python3
"""Send logs carries WindowServer's watchdog samples (.spin). The block is cut out of the real nullmoth-setup.sh and run
by bash against a fixture DiagnosticReports folder: the newest two samples are copied under fixed names, an older one
is left, a computer name with a space in it does not break the loop, only the first 512 KB is kept, and a Mac with no
sample collects nothing. The negative control runs the same fixture against the release branch's script, which has no
such block, and must collect nothing."""
import os
import pathlib
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
fails = 0


def arm(name, ok, detail=""):
    global fails
    print(("ok   " if ok else "FAIL ") + name + (f" ({detail})" if detail else ""))
    fails += not ok


def block_of(setup):
    start = setup.find("  ws_spin=0\n")
    if start < 0:
        return None
    end = setup.index("| head -n 2)\n", start) + len("| head -n 2)\n")
    return setup[start:end]


def run(block, reports, collect):
    script = ("n=0; collection_errors=0; note() { echo \"NOTE $*\"; }\nCOLLECT=%s\n" % collect
              + block.replace("/Library/Logs/DiagnosticReports", str(reports))
              + 'echo "n=$n errors=$collection_errors"\n')
    return subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=30)


def fixture(d):
    reports = d / "DiagnosticReports"
    (reports / "Retired").mkdir(parents=True)
    now = time.time()
    files = [
        (reports / "WindowServer_2026-10-30-053448_old-host.userspace_watchdog_timeout.spin", b"OLD\n", now - 300),
        (reports / "Retired" / "WindowServer_2026-10-30-134452_My Mac.userspace_watchdog_timeout.spin",
         b"Process: WindowServer\n" + b"x" * 600000, now - 100),
        (reports / "WindowServer_2026-10-30-135432_host.userspace_watchdog_timeout.spin", b"NEWEST\n", now - 10),
        (reports / "WindowServer-2026-10-30-135500.ips", b"{}\n", now),
    ]
    for p, data, t in files:
        p.write_bytes(data)
        os.utime(p, (t, t))
    return reports


setup = (ROOT / "Resources/nullmoth-setup.sh").read_text()
block = block_of(setup)
arm("the watchdog block is in Send logs' collector", block is not None)
if block:
    body = setup[setup.index('if [ -n "$COLLECT" ]; then'):]
    arm("it runs before the first log query (the 360 s limit cuts off what comes after)",
        body.index("  ws_spin=0\n") < body.index("lshow "))
    with tempfile.TemporaryDirectory() as t:
        d = pathlib.Path(t)
        reports = fixture(d)
        collect = d / "collect"; collect.mkdir()
        r = run(block, reports, collect)
        got = sorted(p.name for p in collect.iterdir())
        arm("the newest two samples are collected under fixed names",
            got == ["macos-WindowServer-watchdog-1.spin", "macos-WindowServer-watchdog-2.spin"], f"{got} {r.stderr[:200]}")
        one = (collect / "macos-WindowServer-watchdog-1.spin").read_bytes() if got else b""
        two = (collect / "macos-WindowServer-watchdog-2.spin").read_bytes() if len(got) > 1 else b""
        arm("the newest comes first", one == b"NEWEST\n", repr(one[:20]))
        arm("a computer name with a space is read, and only its first 512 KB is kept",
            two.startswith(b"Process: WindowServer\n") and len(two) == 524288, f"{len(two)} bytes")
        arm("the older third sample and the .ips are not taken here", b"OLD" not in one + two)
        arm("the count is added to the collected files and nothing failed", "n=2 errors=0" in r.stdout, r.stdout.strip())
        arm("the collected names pass the uploader's name rule",
            all(c.isalnum() or c in "._-" for n in got for c in n))
    with tempfile.TemporaryDirectory() as t:
        d = pathlib.Path(t)
        reports = d / "DiagnosticReports"; (reports / "Retired").mkdir(parents=True)
        collect = d / "collect"; collect.mkdir()
        r = run(block, reports, collect)
        arm("a Mac with no watchdog sample collects nothing and reports no error",
            not list(collect.iterdir()) and "n=0 errors=0" in r.stdout, r.stdout.strip() + r.stderr[:200])

# Negative control: the release branch's collector (before this change) has no block, so the fixture yields nothing.
# NM_OLD_SETUP names an exported copy where the tree has no git (a synced build host).
if os.environ.get("NM_OLD_SETUP"):
    old = subprocess.CompletedProcess([], 0, pathlib.Path(os.environ["NM_OLD_SETUP"]).read_text(), "")
else:
    old = subprocess.run(["git", "-C", str(ROOT), "show", "6cead22:mac/Resources/nullmoth-setup.sh"],
                         capture_output=True, text=True)
if old.returncode == 0:
    arm("control: the previous collector has no watchdog block (it sent .ips only)", block_of(old.stdout) is None
        and "WindowServer*.spin" not in old.stdout)
else:
    arm("control: the previous collector could be read", False, old.stderr[:200])
sys.exit(1 if fails else 0)
