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
from . import tls
from . import hwcapture, scan_evidence
tls.install()   # downloads verify against the OS certificate store + certifi

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
    tables = os.listdir(acpi) if os.path.isdir(acpi) else []
    if not dsdt_in(acpi):
        fails.append(f"no DSDT in the ACPI dump ({len(tables)} tables)")
    return fails


def dsdt_in(acpi):
    """The DSDT, found by its signature (the first 4 bytes), whatever acpidump named the file."""
    for f in (os.listdir(acpi) if os.path.isdir(acpi) else []):
        try:
            with open(os.path.join(acpi, f), "rb") as fh:
                if fh.read(4) == b"DSDT":
                    return f
        except OSError:
            pass
    return None


def windows_tables(acpi):
    """Fill in any ACPI table acpidump missed, read straight from Windows. Returns notes for the log.

    EnumSystemFirmwareTables lists the table signatures Windows exposes; each one acpidump did not write is fetched with
    GetSystemFirmwareTable and saved as <sig>.aml. Several tables share a signature (SSDT): Windows hands out only the
    first of those, so they are added only when acpidump wrote none at all, never on top of its numbered copies."""
    import ctypes  # noqa: PLC0415 - Windows only
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.EnumSystemFirmwareTables.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
    k32.EnumSystemFirmwareTables.restype = ctypes.c_uint32
    k32.GetSystemFirmwareTable.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
    k32.GetSystemFirmwareTable.restype = ctypes.c_uint32
    provider = int.from_bytes(b"ACPI", "big")
    n = k32.EnumSystemFirmwareTables(provider, None, 0)
    if not n:
        return [f"Windows lists no ACPI tables (error {ctypes.get_last_error()})"]
    ids = ctypes.create_string_buffer(n)
    n = k32.EnumSystemFirmwareTables(provider, ids, n)
    have = set()
    for f in (os.listdir(acpi) if os.path.isdir(acpi) else []):
        try:
            with open(os.path.join(acpi, f), "rb") as fh:
                have.add(fh.read(4))
        except OSError:
            pass
    notes = []
    os.makedirs(acpi, exist_ok=True)
    for i in range(0, n - n % 4, 4):
        sig = ids.raw[i:i + 4]
        if sig in have or not sig.isalnum():
            continue
        tid = int.from_bytes(sig, "little")
        size = k32.GetSystemFirmwareTable(provider, tid, None, 0)
        if not size:
            continue
        buf = ctypes.create_string_buffer(size)
        got = k32.GetSystemFirmwareTable(provider, tid, buf, size)
        if got >= 36 and buf.raw[:4] == sig:
            name = sig.decode("ascii", "replace") + ".aml"
            with open(os.path.join(acpi, name), "wb") as fh:
                fh.write(buf.raw[:got])
            have.add(sig); notes.append(f"{name} read from Windows directly ({got} bytes) - acpidump did not write it")
    return notes


def windows_dsdt(acpi):
    """Read the DSDT straight from Windows and write ACPI/DSDT.aml. Returns a note for the log.

    10-07: a user's scan dumped 44 tables and no DSDT. Windows lists the tables the XSDT points to, but the DSDT hangs
    off the FADT instead, so acpidump fetches it on a separate path that can come back empty. GetSystemFirmwareTable
    hands the DSDT out directly: provider 'ACPI', table id 'DSDT' passed byte-reversed as the API documents."""
    import ctypes  # noqa: PLC0415 - Windows only
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetSystemFirmwareTable.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
    k32.GetSystemFirmwareTable.restype = ctypes.c_uint32
    provider = int.from_bytes(b"ACPI", "big")
    table = int.from_bytes(b"DSDT", "little")
    size = k32.GetSystemFirmwareTable(provider, table, None, 0)
    if not size:
        return f"Windows has no DSDT to give (GetSystemFirmwareTable error {ctypes.get_last_error()})"
    buf = ctypes.create_string_buffer(size)
    got = k32.GetSystemFirmwareTable(provider, table, buf, size)
    data = buf.raw[:got]
    if got < 36 or data[:4] != b"DSDT":
        return f"Windows returned {got} bytes that are not a DSDT"
    os.makedirs(acpi, exist_ok=True)
    with open(os.path.join(acpi, "DSDT.aml"), "wb") as fh:
        fh.write(data)
    return f"DSDT read from Windows directly ({got} bytes) - acpidump did not write one"


def scan(out_dir):
    """Runs the Sniffer in a child process; returns out_dir or raises ScanError with the reason."""
    if platform.system() not in ("Windows", "Linux"):
        raise ScanError(f"scanning runs on Windows or Linux, not {platform.system()}")
    p = subprocess.run([sys.executable, "-m", "p1401.scan", out_dir], cwd=REPO, capture_output=True, text=True,
                       timeout=TIMEOUT + hwcapture.CAPTURE_TIMEOUT + 10)
    fails = check(out_dir)
    if p.returncode != 0 or fails:
        raise ScanError(f"scan failed (rc={p.returncode}): {fails}\n{(p.stderr or p.stdout)[-1500:]}")
    return out_dir


def _sniffer_body(out_dir, token):
    sys.path.insert(0, SNIFFER)
    import HardwareSniffer  # noqa: PLC0415 - only importable with SNIFFER on the path, in this process only
    h = HardwareSniffer.HardwareSniffer(os.path.abspath(out_dir), rich_format=False)
    h.u.head = lambda *a, **k: None  # it clears the console; a child has none
    if platform.system() == "Windows":
        h.check_acpidump = acpidump_path  # pinned copy, not its own download
    original_progress = h.hardware_info.utils.progress_bar
    def checkpoint_progress(*args, **kwargs):
        scan_evidence.save_partial(out_dir, token, getattr(h.hardware_info, "result", {}))
        return original_progress(*args, **kwargs)
    h.hardware_info.utils.progress_bar = checkpoint_progress
    try:
        h.hardware_info.hardware_collector()
    finally:
        scan_evidence.save_partial(out_dir, token, getattr(h.hardware_info, "result", {}))
    h.export_hardware_report()
    h.dump_acpi_tables()
    acpi = os.path.join(out_dir, "ACPI")
    if platform.system() == "Windows":
        for note in windows_tables(acpi):   # anything acpidump missed (FACP, MCFG, ...), straight from Windows
            print(note)
        if not dsdt_in(acpi):               # the DSDT is not in Windows' list of tables; it is fetched by name
            print(windows_dsdt(acpi))
    found = dsdt_in(acpi)
    if found and found.upper() != "DSDT.AML":   # the builder looks for the DSDT by name in places; give it the usual one
        os.replace(os.path.join(acpi, found), os.path.join(acpi, "DSDT.aml"))
        print(f"DSDT was saved as {found}; renamed to DSDT.aml")
    fails = check(out_dir)
    if fails:
        print("\n".join(fails), file=sys.stderr)
        return 1
    return 0


def _sniffer_child(out_dir, token):
    # Only the scan controller creates the fresh run receipt; this process adds sanitized partial sections.
    scan_evidence._current(out_dir, token)
    return _sniffer_body(out_dir, token)


def _child(out_dir, run_id=None):
    """GUI and CLI share this controller: independent inventory first, bounded upstream scan second."""
    token = scan_evidence.begin(out_dir, run_id)
    print("Scan run " + token, flush=True)
    try:
        scan_evidence.save_inventory(out_dir, token, hwcapture.collect({}))
    except Exception as error:
        # A diagnostic collector failure must not prevent Hardware Sniffer from checking the PC.
        print("Hardware inventory unavailable (" + type(error).__name__ + "); the ordinary scan continues.", flush=True)
    ok, failure = False, None
    try:
        p = subprocess.run([sys.executable, "-u", "-m", "p1401.scan", "--sniffer-worker", out_dir, token],
                           cwd=REPO, timeout=TIMEOUT)
        ok = p.returncode == 0 and not check(out_dir)
        if not ok: failure = "upstream_scan_failure"
    except subprocess.TimeoutExpired:
        failure = "upstream_scan_timeout"
        print("Hardware Sniffer exceeded its time limit; the saved CPU/device inventory and partial sections remain available.", file=sys.stderr)
    except Exception as error:
        failure = type(error).__name__
        print("Hardware scan could not finish (" + failure + ").", file=sys.stderr)
    finally:
        try:
            scan_evidence.finish(out_dir, token, ok, failure)
        except Exception as error:
            print("Scan evidence finalization unavailable (" + type(error).__name__ + ").", file=sys.stderr)
    return 0 if ok else 1


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
    if len(sys.argv) == 4 and sys.argv[1] == "--sniffer-worker":
        sys.exit(_sniffer_child(sys.argv[2], sys.argv[3]))
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("out_dir")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    sys.exit(_child(args.out_dir, args.run_id))
