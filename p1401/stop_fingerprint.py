"""One record per build that names what the next report of a boot stop needs and the logs do not carry.

Boot stops with no cause in the data - the freeze at "PCI configuration", the second processor that never answers, the
freeze 34-58 seconds after the hand-off, no installer picture on a processor without graphics, a machine that boots only
with the stick replugged - all end with the same few facts missing: how the firmware describes its processors, which
tables it adds, which vendor methods it ships, what the stick's own log did last and when. This collects them, with no
serial numbers, paths or user names, and rides in the build result (so in the build log the app sends).

record(acpi_dir, boot_texts, hardware) -> dict, never raises: a part that cannot be read says why and the rest stays.
"""
import hashlib
import os
import re

from . import acpi_cpus, acpi_shims, dsdt_pass1, madt as madt_mod

_STAMP = re.compile(r"^(\d+):(\d+) (\d+):(\d+) ")
TABLES_MAX = 80


def _tables(acpi_dir):
    out = []
    for name in sorted(os.listdir(acpi_dir))[:TABLES_MAX]:
        if not name.lower().endswith(".aml"):
            continue
        try:
            with open(os.path.join(acpi_dir, name), "rb") as fh:
                d = fh.read(8 * 1024 * 1024)
        except OSError:
            continue
        if len(d) >= 36:
            out.append({"file": name, "sig": d[:4].decode("ascii", "replace"), "oem": d[10:16].decode("ascii", "replace").strip(),
                        "table_id": d[16:24].decode("ascii", "replace").strip(), "len": len(d), "sha": hashlib.sha256(d).hexdigest()[:12]})
    return out


def acpi_facts(acpi_dir):
    facts = {"tables": [], "notes": []}
    try:
        facts["tables"] = _tables(acpi_dir)
        def read(*names):
            p = next((os.path.join(acpi_dir, f) for f in sorted(os.listdir(acpi_dir)) if f.upper() in names), None)
            return open(p, "rb").read(8 * 1024 * 1024) if p else None
        m, d = read("APIC.AML", "MADT.AML"), read("DSDT.AML")
        if m:
            try:
                ents = madt_mod.entries(m)
                kinds = {}
                for t, e in ents:
                    kinds[t] = kinds.get(t, 0) + 1
                facts["madt"] = {"entry_types": {str(k): v for k, v in sorted(kinds.items())}, "enabled_uids": len(acpi_cpus.enabled_uids(m)),
                                 "x2apic_only": madt_mod.needs_rewrite(m)}
            except madt_mod.Unsupported as e:
                facts["notes"].append(f"MADT: {e}")
        if d:
            facts["dsdt"] = {"len": len(d), "processor_devices": len(acpi_cpus.devices(d)), "osi_calls": d.count(b"_OSI"),
                             "windows_osi": sorted({x.decode() for x in re.findall(rb"Windows 20\d\d(?: [A-Za-z0-9 .]*)?", d)})[:12],
                             "has_alib": b"ALIB" in d}
            try:
                facts["dsdt"]["pass1_failing_scopes"] = len(dsdt_pass1.failing_scopes(d))
            except dsdt_pass1.Unsupported as e:
                facts["notes"].append(f"DSDT pass 1: {e}")
        found, unread = acpi_shims.find_alib(acpi_dir)
        facts["alib_ssdts"] = [{"file": f["file"], "oem_table_id": acpi_shims.table_name(f["oem_table_id"])} for f in found]
        facts["notes"] += [f"ALIB unread: {u}" for u in unread]
        facts["dmar_present"] = any(t["sig"] == "DMAR" for t in facts["tables"])
        facts["ssdt_count"] = sum(1 for t in facts["tables"] if t["sig"] == "SSDT")
    except OSError as e:
        facts["notes"].append(f"ACPI folder: {type(e).__name__}")
    return facts


def log_facts(text):
    """The shape of one stick log: how far it got, and how long it sat on its last line."""
    lines = [l for l in text.splitlines() if l.strip()]
    stamps = [_STAMP.match(l) for l in lines]
    stamps = [m for m in stamps if m]
    out = {"lines": len(lines), "last": [re.sub(r"\s+", " ", l)[:160] for l in lines[-8:]]}
    if stamps:
        sec = lambda m: int(m.group(1)) + int(m.group(2)) / 1000.0
        out["first_s"], out["last_s"] = sec(stamps[0]), sec(stamps[-1])
        out["last_gap_ms"] = int(stamps[-1].group(3)) * 1000 + int(stamps[-1].group(4))
    out["eb_last"] = next((l[:160] for l in reversed(lines) if "EB|" in l or "AAPL:" in l), "")
    out["stop_codes"] = sorted(set(re.findall(r"STOP 0x[0-9A-Fa-f]+", text)))
    out["exitbs_reached"] = "EXITBS" in text
    found = re.search(r"OCCPU: Found (.+)", text)
    out["cpu_found"] = found.group(1).strip()[:80] if found else ""
    mp = re.search(r"OCCPU: MP services threads (\d+) \(enabled (\d+)\)", text)
    out["mp_threads"] = {"threads": int(mp.group(1)), "enabled": int(mp.group(2))} if mp else None
    return out


def hardware_facts(hardware):
    hw = hardware or {}
    cpu = (hw.get("CPU") or {})
    gpus = hw.get("GPU") or {}
    items = gpus.values() if isinstance(gpus, dict) else gpus
    kinds = sorted({str(g.get("Device Type") or "") for g in items if isinstance(g, dict)})
    return {"cpu": cpu.get("Processor Name"), "codename": cpu.get("Codename"), "cores": cpu.get("Core Count"),
            "platform": (hw.get("Motherboard") or {}).get("Platform"), "gpu_kinds": kinds,
            "cpu_without_igpu": bool(re.search(r"\b\d{4,5}[A-Z]*F\b", str(cpu.get("Processor Name") or ""))),
            "bios_above_4g": (hw.get("BIOS") or {}).get("Above 4G Decoding"), "bios_vtd": (hw.get("BIOS") or {}).get("VT-d")}


def record(acpi_dir, boot_texts, hardware):
    rec = {"schema": 1}
    for key, fn in (("acpi", lambda: acpi_facts(acpi_dir)), ("hardware", lambda: hardware_facts(hardware)),
                    ("stick_logs", lambda: [log_facts(t) for t in (boot_texts or [])[:4]])):
        try:
            rec[key] = fn()
        except Exception as e:  # noqa: BLE001 - a diagnostic must never stop a build
            rec[key] = {"error": type(e).__name__}
    return rec
