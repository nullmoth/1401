"""Scans this machine with Hardware Sniffer (upstream/Hardware-Sniffer, BSD-3, pinned in upstream/PINNED.json) and
writes Report.json + ACPI/*.aml, the two inputs engine.build needs. Windows (WMI) or Linux (sysfs, root for ACPI).

Nothing gets sent anywhere. The Sniffer reads WMI/sysfs and its own bundled pci.ids/usb.ids. The one thing it
downloads, acpidump.exe from GitHub (unverified), is replaced with a copy pinned by sha256 below.

Runs in a separate process because both upstreams have a top-level package called `Scripts` and can't share
sys.modules. (A PyInstaller build needs its own entry point for `scan`; `-m` is just for development.)

export_hardware_report prints an error and keeps going if the write fails, so its result isn't trusted: the
report has to exist, parse, and list a CPU, motherboard, and GPU, and ACPI/ has to contain a DSDT.

    python3 -m p1401.scan <out_dir>
"""
import hashlib
import json
import os
import platform
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNIFFER = os.path.join(REPO, "upstream", "Hardware-Sniffer")
# ACPICA R2024_12_12 acpidump.exe, same URL the Sniffer uses. GitHub has no digest for this asset, so the hash is
# from our own download (2026-09-24); the size matches the API's. ACPICA is Intel's, dual BSD/GPL.
ACPIDUMP = {"url": "https://github.com/acpica/acpica/releases/download/R2024_12_12/acpidump.exe",
            "sha256": "9f54227f9f7dccbf1fbc652f05d342e7525d5de0861905bfef05254064a07fd4", "size": 148480}
CACHE = os.path.join(os.path.expanduser("~"), ".cache", "1401")
TIMEOUT = 600  # seconds. A WMI scan takes about a minute on a slow laptop


class ScanError(RuntimeError):
    pass


def _sha256(p):
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def acpidump_path():
    """The pinned acpidump.exe: bundled beside the app if present, else fetched once and verified."""
    import urllib.request  # noqa: PLC0415
    for p in (os.path.join(getattr(sys, "_MEIPASS", REPO), "bin", "acpidump.exe"),
              os.path.join(CACHE, "acpidump-R2024_12_12.exe")):
        if os.path.isfile(p) and _sha256(p) == ACPIDUMP["sha256"]:
            return p
    os.makedirs(CACHE, exist_ok=True)
    dst = os.path.join(CACHE, "acpidump-R2024_12_12.exe")
    with urllib.request.urlopen(urllib.request.Request(ACPIDUMP["url"], headers={"User-Agent": "1401"}), timeout=60) as r:
        data = r.read()
    got = hashlib.sha256(data).hexdigest()
    if got != ACPIDUMP["sha256"]:
        raise ScanError(f"acpidump.exe sha256 {got[:12]} != pinned {ACPIDUMP['sha256'][:12]} - refused")
    with open(dst + ".tmp", "wb") as fh:
        fh.write(data)
    os.replace(dst + ".tmp", dst)
    return dst


def check(out_dir):
    """The scan's output, judged on its own terms. Returns [failures] (empty = usable)."""
    fails = []
    rp = os.path.join(out_dir, "Report.json")
    try:
        with open(rp, encoding="utf-8") as fh:
            rep = json.load(fh)
        for k in ("Motherboard", "CPU", "GPU"):
            if not rep.get(k):
                fails.append(f"report has no {k}")
    except (OSError, ValueError) as e:
        fails.append(f"Report.json unreadable: {type(e).__name__}: {e}")
    acpi = os.path.join(out_dir, "ACPI")
    tables = [f.upper() for f in os.listdir(acpi)] if os.path.isdir(acpi) else []
    if "DSDT.AML" not in tables:
        fails.append(f"no DSDT.aml in the ACPI dump ({len(tables)} tables)")
    return fails


def scan(out_dir):
    """Runs the Sniffer in a child process; returns out_dir or raises ScanError with the reason."""
    if platform.system() not in ("Windows", "Linux"):
        raise ScanError(f"scanning runs on Windows or Linux, not {platform.system()}")
    p = subprocess.run([sys.executable, "-m", "p1401.scan", out_dir], cwd=REPO, capture_output=True, text=True,
                       timeout=TIMEOUT)
    fails = check(out_dir)
    if p.returncode != 0 or fails:
        raise ScanError(f"scan failed (rc={p.returncode}): {fails}\n{(p.stderr or p.stdout)[-1500:]}")
    return out_dir


def _child(out_dir):
    sys.path.insert(0, SNIFFER)
    import HardwareSniffer  # noqa: PLC0415 - only importable with SNIFFER on the path, in this process only
    h = HardwareSniffer.HardwareSniffer(os.path.abspath(out_dir), rich_format=False)
    h.u.head = lambda *a, **k: None  # it clears the console; a child has none
    if platform.system() == "Windows":
        h.check_acpidump = acpidump_path  # pinned copy, not its own download
    h.hardware_info.hardware_collector()
    h.export_hardware_report()
    h.dump_acpi_tables()
    fails = check(out_dir)
    if fails:
        print("\n".join(fails), file=sys.stderr)
        return 1
    return 0


def selftest():
    import shutil  # noqa: PLC0415
    import tempfile  # noqa: PLC0415
    res = []

    def arm(name, cond, shown):
        res.append(bool(cond))
        print(("ok   " if cond else "FAIL ") + name + f"  [{shown}]")

    good = os.path.join(REPO, "tests", "corpus", "cache", "x570-5800x-6600xt")
    if not os.path.isdir(good):
        print("can't run: corpus not fetched (tests/corpus/fetch.py)")
        return False
    d = tempfile.mkdtemp(prefix="1401-scan-")
    shutil.copytree(good, d, dirs_exist_ok=True)
    arm("real Sniffer report + ACPI dump passes", not check(d), check(d) or "ok")
    os.remove(os.path.join(d, "ACPI", next(f for f in os.listdir(os.path.join(d, "ACPI")) if f.upper() == "DSDT.AML")))
    arm("dump without a DSDT fails", any("DSDT" in f for f in check(d)), check(d))
    with open(os.path.join(d, "Report.json"), "w") as fh:
        fh.write('{"CPU": {}')
    arm("truncated Report.json fails (the Sniffer ignores write errors)",
        any("unreadable" in f for f in check(d)), check(d)[:1])
    p = acpidump_path()
    arm("pinned acpidump.exe matches sha256 + size", _sha256(p) == ACPIDUMP["sha256"] and os.path.getsize(p) == ACPIDUMP["size"], p)
    bad = os.path.join(tempfile.mkdtemp(prefix="1401-scan-"), "acpidump.exe")
    with open(p, "rb") as src, open(bad, "wb") as dst:
        b = bytearray(src.read())
        b[4096] ^= 1
        dst.write(b)
    arm("acpidump.exe with one flipped bit doesn't match", _sha256(bad) != ACPIDUMP["sha256"], "mismatch")
    try:
        scan(d)
        refused = platform.system() in ("Windows", "Linux")
    except ScanError as e:
        refused = "not Darwin" in str(e) or platform.system() in ("Windows", "Linux")
    arm("refuses to run when not on Windows/Linux", refused, platform.system())
    print(f"\n{sum(res)}/{len(res)} passed (not run on real Windows yet)")
    return all(res)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    sys.exit(_child(sys.argv[1]))
