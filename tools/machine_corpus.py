"""Collects every distinct PC hardware fingerprint the field has sent and writes the committed replay corpus.

Sources (all read-only): the Check this PC receipts ("*scan-evidence.json*") and the build logs ("*build-log*") in the
support intake folders. Both carry the same hardware summary (p1401/report.py diagnostic_hardware): device IDs, PCI
paths, CPU name and codename, board and chipset. Build logs also carry what the builder decided for that PC (macOS
version, kexts, disabled devices, error), which is what the replay compares against.

The corpus keeps device identity only: no names of monitors, drives, no serials, no upload ids, no dates finer than a day.
Two PCs with the same resolver-relevant hardware collapse to one row with a count.

    python3 tools/machine_corpus.py <intake folder>... [--write tests/corpus/machines.json.gz]
"""
import collections
import glob
import gzip
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "..", "tests", "corpus", "machines.json.gz")
LISTS = ("GPU", "Network", "USB Controllers", "Storage Controllers", "Input", "Sound", "Bluetooth", "SD Controller",
         "Biometric", "Monitor", "Storage Drives")
KEEP = {  # per section, the properties that matter to a resolver; everything else is dropped
    "GPU": ("name", "Manufacturer", "Device ID", "Subsystem ID", "Device Type", "Codename", "PCI Path", "ACPI Path", "Resizable BAR"),
    "Network": ("name", "Device ID", "Subsystem ID", "Bus Type", "PCI Path", "ACPI Path"),
    "USB Controllers": ("name", "Device ID", "Subsystem ID", "PCI Path", "ACPI Path", "Bus Type"),
    "Storage Controllers": ("name", "Device ID", "Subsystem ID", "Bus Type", "PCI Path", "ACPI Path"),
    "Input": ("name", "Device ID", "Bus Type", "ACPI Path", "PCI Path"),
    "Sound": ("name", "Device ID", "Subsystem ID", "Bus Type", "Codec ID", "PCI Path", "ACPI Path"),
    "Bluetooth": ("name", "Device ID", "Bus Type", "PCI Path", "ACPI Path"),
    "SD Controller": ("name", "Device ID", "Subsystem ID", "Bus Type", "PCI Path", "ACPI Path"),
    "Biometric": ("name", "Device ID", "Bus Type"),
    "Monitor": ("Connector Type",),
    "Storage Drives": ("Bus Type", "Media Type"),
}
CPU_KEYS = ("Manufacturer", "Processor Name", "Codename", "Core Count", "Thread Count", "CPU Count", "CPU Signature", "CPUID",
            "Family", "Model", "Stepping", "P-Core Count", "E-Core Count")
BOARD_KEYS = ("Name", "Manufacturer", "Chipset", "Platform", "Version")


def _json_after(text, marker):
    i = text.find(marker)
    if i < 0:
        return None
    try:
        return json.JSONDecoder().raw_decode(text[i:])[0]
    except ValueError:
        return None


def clean(summary):
    """The corpus form of one hardware summary: only the keep-listed properties."""
    out = {"CPU": {k: v for k, v in (summary.get("CPU") or {}).items() if k in CPU_KEYS},
           "Motherboard": {k: v for k, v in (summary.get("Motherboard") or {}).items() if k in BOARD_KEYS},
           "BIOS": {k: v for k, v in (summary.get("BIOS") or {}).items() if k in ("Firmware Type",)}}
    for section in LISTS:
        rows = summary.get(section)
        if not isinstance(rows, list):
            continue
        out[section] = [{k: v for k, v in r.items() if k in KEEP[section]} for r in rows if isinstance(r, dict)]
    return out


def key_of(c):
    """What makes two PCs the same machine for a resolver: every identity-bearing field, device names excluded."""
    def dev(rows, fields):
        return sorted(tuple(str(r.get(f, "")) for f in fields) for r in rows or [])
    return hashlib.sha256(json.dumps([
        c["CPU"].get("Processor Name"), c["CPU"].get("Codename"), c["CPU"].get("Core Count"),
        c["Motherboard"].get("Name"), c["Motherboard"].get("Chipset"), c["Motherboard"].get("Platform"),
        c["BIOS"].get("Firmware Type"),
        dev(c.get("GPU"), ("Device ID", "Subsystem ID", "Device Type", "Codename", "Resizable BAR")),
        dev(c.get("Network"), ("Device ID", "Bus Type")),
        dev(c.get("Sound"), ("Device ID", "Subsystem ID", "Bus Type", "Codec ID")),
        dev(c.get("Bluetooth"), ("Device ID", "Bus Type")),
        dev(c.get("Storage Controllers"), ("Device ID", "Bus Type")),
        dev(c.get("USB Controllers"), ("Device ID",)),
        dev(c.get("Input"), ("name", "Device ID", "Bus Type")),
        dev(c.get("SD Controller"), ("Device ID",)), dev(c.get("Biometric"), ("Device ID",)),
    ], sort_keys=True).encode()).hexdigest()[:16]


def verdict_of(result):
    """What the builder said about that PC in the field, from a build-log result object."""
    return {"ok": bool(result.get("ok")), "macos": result.get("macos_version", ""), "smbios": result.get("smbios", ""),
            "kexts": sorted(result.get("kexts") or []), "disabled": sorted(map(str, (result.get("disabled_devices") or {}).values())),
            "error": (result.get("error") or "")[:300]}


def collect(roots):
    rows = {}
    seen_files = 0
    for root in roots:
        for meta_path in glob.iglob(os.path.join(root, "*", "*.json")):
            try:
                meta = json.load(open(meta_path))
            except (OSError, ValueError):
                continue
            name = meta.get("original_name", "")
            is_scan = "scan-evidence" in name
            is_build = name.endswith("build-log.txt")
            if not (is_scan or is_build):
                continue
            try:
                text = open(meta_path[:-5] + ".txt", errors="replace").read()
            except OSError:
                continue
            seen_files += 1
            verdict = None
            if is_scan:
                try:
                    summary = json.loads(text).get("hardware_summary")
                except ValueError:
                    continue
            else:
                data = _json_after(text, '{\n  "ok"')
                if not isinstance(data, dict):
                    continue
                summary = data.get("hardware_summary")
                verdict = verdict_of(data)
            if not isinstance(summary, dict) or not summary.get("CPU") or not summary.get("GPU"):
                continue
            c = clean(summary)
            k = key_of(c)
            row = rows.setdefault(k, {"key": k, "hardware": c, "count": 0, "batches": set(), "field": collections.Counter(),
                                      "field_samples": {}})
            row["count"] += 1
            row["batches"].add(meta.get("batch"))
            if verdict:
                vk = json.dumps(verdict, sort_keys=True)
                row["field"][vk] += 1
    out = []
    for row in sorted(rows.values(), key=lambda r: (-r["count"], r["key"])):
        out.append({"key": row["key"], "machines": len(row["batches"]), "reports": row["count"], "hardware": row["hardware"],
                    "field_builds": [{"times": n, **json.loads(v)} for v, n in row["field"].most_common(5)]})
    return out, seen_files


def load(path=DEFAULT_OUT):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def main(argv):
    write = None
    roots = []
    it = iter(argv)
    for a in it:
        if a == "--write":
            write = next(it)
        else:
            roots.append(a)
    if not roots:
        print(__doc__)
        return 2
    rows, files = collect(roots)
    print(f"{files} receipts read, {len(rows)} distinct resolver-relevant machines, "
          f"{sum(r['machines'] for r in rows)} machine-batches")
    if write:
        doc = {"schema": 1, "about": "Distinct PC hardware fingerprints from Check this PC receipts and build logs. Device IDs "
               "only. field_builds is what the builder produced for that PC at the time (when a build log existed).",
               "machines": rows}
        data = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
        tmp = write + ".tmp"
        with gzip.GzipFile(tmp, "wb", mtime=0) as f:
            f.write(data)
        os.replace(tmp, write)
        print(f"wrote {write} ({os.path.getsize(write)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
