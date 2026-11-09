"""Replays the builder over a Send-logs bundle that carries the firmware's ACPI tables.

Two bundle shapes are read:
  * a 1401 Probe folder or zip (report.json + acpi/tables/*.aml): converted with p1401.probe_report, which gives the
    full device list and the DSDT;
  * the app's acpi-bundle.zip (p1401.acpi_bundle) next to the scan-evidence or build log of the same Send: the hardware
    comes from that file's summary (tools/machine_replay.reconstruct), the tables from the zip.
The engine runs in plan mode (no downloads except the ACPI disassembler it fetches on first use) in its own process, because
it keeps module-level state. The result says whether the DSDT was read and what the builder decided.

    python3 tools/machine_bundle_replay.py <bundle.zip|folder> [--hardware scan-evidence.json] [--macos 24|25] [--build]
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


def config_facts(plist_path):
    """What the built config.plist decided: the settings a failing boot is traced to."""
    import plistlib
    with open(plist_path, "rb") as f:
        c = plistlib.load(f)
    nvram = (c.get("NVRAM", {}).get("Add", {}) or {}).get("7C436110-AB2A-4BBB-A880-FE41995C9F82", {})
    return {"booter": dict(c.get("Booter", {}).get("Quirks", {})), "kernel_quirks": dict(c.get("Kernel", {}).get("Quirks", {})),
            "uefi_quirks": dict(c.get("UEFI", {}).get("Quirks", {})),
            "boot_args": nvram.get("boot-args", ""), "acpi": [a.get("Path") for a in c.get("ACPI", {}).get("Add", []) if a.get("Enabled")],
            "kexts": [k.get("BundlePath") for k in c.get("Kernel", {}).get("Add", []) if k.get("Enabled")],
            "smbios": (c.get("PlatformInfo", {}).get("Generic", {}) or {}).get("SystemProductName")}


def replay_one(bundle, macos="24", hardware=None, build=False, report_override=None):
    """Run the builder over one bundle in a fresh process: plan mode, or a full build with the config's settings read back."""
    work = tempfile.mkdtemp(prefix="1401-bundle-")
    name = os.path.basename(bundle)
    try:
        try:
            report, acpi = prepare(bundle, work, hardware)
            if report_override:      # another source of the same PC's hardware (the Windows scan), the bundle's own ACPI
                shutil.copyfile(report_override, report)
        except Exception as e:  # noqa: BLE001 - an unreadable bundle is a result
            return {"bundle": name, "ok": False, "stage": "prepare", "error": f"{type(e).__name__}: {e}"[:300]}
        out = os.path.join(work, "efi")
        cmd = [sys.executable, os.path.join(HERE, "_bundle_build.py"), "build" if build else "plan", report, acpi] + ([out] if build else []) + \
              ["--json", "--macos", macos]
        p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=1800)
        try:
            d = json.loads(p.stdout[p.stdout.index("{"):])
        except ValueError:
            return {"bundle": name, "ok": False, "stage": "engine", "error": (p.stderr or p.stdout)[-300:]}
        result = {"bundle": name, "ok": d.get("ok"), "stage": "build" if build else "plan", "macos": d.get("macos_version"),
                  "smbios": d.get("smbios"), "kexts": d.get("kexts"), "error": (d.get("error") or "")[:300],
                  "acpi_diagnostics": [{k: x.get(k) for k in ("tool", "exit_code")} for x in d.get("acpi_diagnostics") or []][:4],
                  "storage_plan": (d.get("storage_plan") or {}).get("kind"), "validation_ok": (d.get("validation") or {}).get("ok"),
                  "config": None}
        if build and d.get("ok"):
            try:
                result["config"] = config_facts(os.path.join(out, "EFI", "OC", "config.plist"))
            except (OSError, ValueError) as e:
                result["config"] = {"error": str(e)[:100]}
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    macos, hardware, many, out, jobs, build, overrides = "24", None, None, None, 4, False, None
    it = iter(argv)
    paths = []
    for a in it:
        if a == "--macos":
            macos = next(it)
        elif a == "--hardware":
            hardware = next(it)
        elif a == "--overrides":
            overrides = next(it)
        elif a == "--build":
            build = True
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
            ov = {}
            if overrides:
                ov = {n[:-5]: os.path.join(overrides, n) for n in os.listdir(overrides) if n.endswith(".json")}
            results = list(ex.map(lambda p: replay_one(p, macos, None, build, ov.get(os.path.basename(p))), paths))
    else:
        results = [replay_one(p, macos, hardware, build) for p in paths]
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


def compare_to_stick_logs(results, records, min_seen=3, bad_rate=0.3, good_rate=0.1):
    """Booter quirks of full builds against what stick logs of the same CPU did with each quirk set.

    results: replay_one(build=True) dicts plus 'cpu' (the processor's brand string); records: tools/mine_known_machines.collect().
    -> {'matches': n, 'under-observed': n, 'no-evidence': n, 'known-bad': [bundle...], 'fails-often': [bundle...]}. known-bad is a
    build whose quirk set failed in >= bad_rate of its batches on this CPU while another set passed in >= 1 - good_rate of its own."""
    import collections
    import mine_known_machines as K
    keys = list(K.ABBR.values()) + ["DevirtualiseMmio"]

    def key(q):
        return tuple((k, bool(q.get(k))) for k in sorted(keys) if k in q)

    by = collections.defaultdict(lambda: collections.defaultdict(lambda: [set(), set()]))
    for r in records:
        if r["passed"]:
            by[r["cpu"]][key(r["quirks"])][0].add(r["batch"])
        elif r["failed"]:
            by[r["cpu"]][key(r["quirks"])][1].add(r["batch"])
    out = {"matches": 0, "under-observed": 0, "no-evidence": 0, "known-bad": [], "fails-often": []}
    for r in results:
        if not (r.get("config") and r.get("cpu")):
            continue
        stats = by.get(K.cpu_of("OCCPU: Found " + r["cpu"]))
        if not stats:
            out["no-evidence"] += 1
            continue
        mine = key(r["config"]["booter"])
        p, f = (len(x) for x in stats.get(mine, [set(), set()]))
        better = [q for q, v in stats.items() if q != mine and len(v[0]) >= min_seen and len(v[1]) / (len(v[0]) + len(v[1])) < good_rate]
        if p + f < min_seen:
            out["under-observed"] += 1
        elif f / (p + f) >= bad_rate:
            out["known-bad" if better else "fails-often"].append(r["bundle"])
        else:
            out["matches"] += 1
    return out
