"""Replays the builder over a Send-logs bundle that carries the firmware's ACPI tables.

Two bundle shapes are read:
  * a 1401 Probe folder or zip (report.json + acpi/tables/*.aml): converted with p1401.probe_report, which gives the
    full device list and the DSDT;
  * the app's acpi-bundle.zip (p1401.acpi_bundle) next to the scan-evidence or build log of the same Send: the hardware
    comes from that file's summary (tools/machine_replay.reconstruct), the tables from the zip.
The engine runs in plan mode (no downloads except the ACPI disassembler it fetches on first use) in its own process, because
it keeps module-level state. The result says whether the DSDT was read and what the builder decided.

    python3 tools/machine_bundle_replay.py <bundle.zip|folder> [--hardware scan-evidence.json] [--macos 24|25]
    python3 tools/machine_bundle_replay.py --many <folder of bundles> [--jobs N] [--json out.json]
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)


def _extract(path, dest):
    if os.path.isdir(path):
        return path
    with zipfile.ZipFile(path) as z:
        total = 0
        for i in z.infolist():
            total += i.file_size
            if total > 200 * 1024 * 1024 or ".." in i.filename.split("/") or i.filename.startswith("/"):
                raise ValueError("bundle too large or unsafe")
        z.extractall(dest)
    return dest


def _find(root, *tails):
    for dp, _, fs in os.walk(root):
        for f in fs:
            full = os.path.join(dp, f).replace("\\", "/")
            if any(full.lower().endswith(t) for t in tails):
                return os.path.join(dp, f)
    return None


def prepare(bundle, work, hardware=None):
    """-> (report.json path, ACPI dir) ready for the builder."""
    root = _extract(bundle, os.path.join(work, "src"))
    probe_report = _find(root, "/report.json")
    tables = _find(root, "/acpi/tables/dsdt.aml", "/acpi/dsdt.aml")
    if probe_report and tables:
        from p1401 import probe_report as pr
        base = os.path.dirname(os.path.dirname(os.path.dirname(tables))) if tables.lower().endswith("/acpi/tables/dsdt.aml") else os.path.dirname(os.path.dirname(tables))
        return pr.convert(base, os.path.join(work, "converted"))
    dsdt = _find(root, "/acpi/dsdt.aml")
    if dsdt and hardware:
        import machine_replay
        with open(hardware, encoding="utf-8") as f:
            summary = json.load(f).get("hardware_summary") or {}
        import machine_corpus
        rep = machine_replay.reconstruct(machine_corpus.clean(summary))
        out = os.path.join(work, "converted")
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "report.json"), "w") as f:
            json.dump(rep, f)
        shutil.copytree(os.path.dirname(dsdt), os.path.join(out, "ACPI"), dirs_exist_ok=True)
        return os.path.join(out, "report.json"), os.path.join(out, "ACPI")
    raise ValueError("no DSDT in this bundle, or an acpi-bundle without --hardware")


def replay_one(bundle, macos="24", hardware=None):
    """Run the builder in plan mode over one bundle in a fresh process. -> dict."""
    work = tempfile.mkdtemp(prefix="1401-bundle-")
    try:
        try:
            report, acpi = prepare(bundle, work, hardware)
        except Exception as e:  # noqa: BLE001 - an unreadable bundle is a result
            return {"bundle": os.path.basename(bundle), "ok": False, "stage": "prepare", "error": f"{type(e).__name__}: {e}"[:300]}
        p = subprocess.run([sys.executable, "-m", "p1401", "plan", report, acpi, "--json", "--macos", macos], cwd=REPO,
                           capture_output=True, text=True, timeout=900)
        try:
            d = json.loads(p.stdout[p.stdout.index("{"):])
        except ValueError:
            return {"bundle": os.path.basename(bundle), "ok": False, "stage": "engine", "error": (p.stderr or p.stdout)[-300:]}
        diag = d.get("acpi_diagnostics") or []
        return {"bundle": os.path.basename(bundle), "ok": d.get("ok"), "stage": "plan", "macos": d.get("macos_version"),
                "smbios": d.get("smbios"), "kexts": d.get("kexts"), "error": (d.get("error") or "")[:300],
                "dsdt_read": not any("no usable DSDT" in (d.get("error") or "") for _ in [0]),
                "acpi_diagnostics": [{k: x.get(k) for k in ("tool", "exit_code")} for x in diag][:4],
                "storage_plan": (d.get("storage_plan") or {}).get("kind")}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    macos, hardware, many, out, jobs = "24", None, None, None, 4
    it = iter(argv)
    paths = []
    for a in it:
        if a == "--macos":
            macos = next(it)
        elif a == "--hardware":
            hardware = next(it)
        elif a == "--many":
            many = next(it)
        elif a == "--json":
            out = next(it)
        elif a == "--jobs":
            jobs = int(next(it))
        else:
            paths.append(a)
    if many:
        paths = [os.path.join(many, n) for n in sorted(os.listdir(many))]
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(jobs) as ex:
            results = list(ex.map(lambda p: replay_one(p, macos), paths))
    else:
        results = [replay_one(p, macos, hardware) for p in paths]
    if out:
        with open(out, "w") as f:
            json.dump(results, f, indent=1)
    ok = sum(1 for r in results if r["ok"])
    print(f"{ok}/{len(results)} bundles planned")
    for r in results:
        if not r["ok"]:
            print(" ", r["bundle"], r["stage"], r["error"][:140])
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
