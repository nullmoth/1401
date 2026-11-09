"""Census of every component class seen in the field, and what the builder does for each device ID.

For each class (CPU codename, chipset, GPU, Ethernet and Wi-Fi, audio, Bluetooth, USB controller, storage, input, card
reader, fingerprint reader) it lists each distinct device with how many PCs reported it and what the REAL builder does
for it. The builder's answer is measured, not read from a table: a baseline PC that builds cleanly is replayed with and
without the device, and the difference (kexts added, macOS range, disabled, notices) is that device's resolution.

    python3 tools/machine_census.py [--out docs/machine-census.json] [--md docs/machine-census.md]
"""
import collections
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import machine_corpus  # noqa: E402
import machine_replay  # noqa: E402

CLASSES = ("GPU", "Network", "Sound", "Bluetooth", "Storage Controllers", "USB Controllers", "SD Controller", "Biometric", "Input")

BASELINE = {
    "CPU": {"Manufacturer": "Intel", "Processor Name": "12th Gen Intel(R) Core(TM) i7-12700F", "Codename": "Alder Lake-S",
            "Core Count": "12", "CPU Count": "01"},
    "Motherboard": {"Name": "BASELINE B660M", "Chipset": "B660", "Platform": "Desktop"},
    "BIOS": {"Firmware Type": "UEFI"},
    "GPU": [{"name": "NVIDIA GeForce RTX 3060", "Manufacturer": "NVIDIA", "Device ID": "10DE-2503", "Subsystem ID": "87F51043",
             "Device Type": "Discrete GPU", "Codename": "Unknown", "Resizable BAR": "Disabled",
             "PCI Path": "PciRoot(0x0)/Pci(0x1,0x0)/Pci(0x0,0x0)", "ACPI Path": "\\_SB.PC00.PEG1.PEGP"}],
    "Network": [{"name": "Realtek PCIe GbE Family Controller", "Device ID": "10EC-8168", "Subsystem ID": "86771043", "Bus Type": "PCI",
                 "PCI Path": "PciRoot(0x0)/Pci(0x1c,0x3)/Pci(0x0,0x0)", "ACPI Path": "\\_SB.PC00.RP04.PXSX"}],
    "Sound": [{"name": "Realtek(R) Audio", "Device ID": "10EC-0897", "Subsystem ID": "104387FB", "Bus Type": "HDAUDIO"}],
    "Storage Controllers": [{"name": "NVMe SSD Controller", "Device ID": "144D-A80A", "Subsystem ID": "A801144D", "Bus Type": "PCI",
                             "PCI Path": "PciRoot(0x0)/Pci(0x6,0x0)/Pci(0x0,0x0)", "ACPI Path": "\\_SB.PC00.PEG0.PEGP"}],
    "USB Controllers": [{"name": "Intel(R) USB 3.20 xHCI", "Device ID": "8086-7AE0", "Subsystem ID": "86941043", "Bus Type": "PCI",
                         "PCI Path": "PciRoot(0x0)/Pci(0x14,0x0)", "ACPI Path": "\\_SB.PC00.XHCI"}],
    "Input": [{"name": "PS/2 Standard Keyboard", "Bus Type": "ACPI"}],
}
OPTIONAL = {"Bluetooth", "SD Controller", "Biometric", "Input"}   # the baseline has none of these


def _probe(c, macos):
    return machine_replay.replay(c, macos=macos)


_BASE = {}


def baseline(mv):
    if mv not in _BASE:
        _BASE[mv] = _probe(BASELINE, mv)
    return _BASE[mv]


def diff(base, r):
    """What a device changed relative to the baseline replay."""
    return {"ok": r["ok"], "error": (r["refused"] or r["crash"])[:200],
            "kexts_added": sorted(set(r.get("kexts", [])) - set(base["kexts"])),
            "kexts_removed": sorted(set(base["kexts"]) - set(r.get("kexts", []))),
            "disabled": sorted(set(r.get("disabled", [])) - set(base["disabled"])),
            "macos_range": None}


def device_rows(machines):
    """{class: {device key: {name, ids, machines}}} over the corpus."""
    out = {cls: {} for cls in CLASSES}
    for m in machines:
        for cls in CLASSES:
            seen = set()
            for dev in m["hardware"].get(cls, []):
                key = dev.get("Device ID") or ("name:" + str(dev.get("name")))
                if key in seen:
                    continue
                seen.add(key)
                row = out[cls].setdefault(key, {"key": key, "name": dev.get("name"), "bus": dev.get("Bus Type"), "machines": 0,
                                                "sample": dev, "codenames": collections.Counter()})
                row["machines"] += m["machines"]
                row["codenames"][m["hardware"]["CPU"].get("Codename", "")] += m["machines"]
    return out


def resolve_device(cls, dev, macos_list=("24", "25")):
    """Replay the baseline with this device added (GPU: replaced) and report what changed."""
    base = {mv: baseline(mv) for mv in macos_list}
    c = copy.deepcopy(BASELINE)
    dev = {k: v for k, v in dev.items()}
    if cls == "GPU":
        c["GPU"] = [dev]
    else:
        c[cls] = list(c.get(cls, [])) + [dev]
    result = {}
    for mv in macos_list:
        r = _probe(c, mv)
        d = diff(base[mv], r)
        # per-device macOS range from the engine's own compatibility pass
        rng = [v for k, v in (r.get("compat") or {}).items() if k.split("|")[0] == cls and f"|{dev.get('Device ID')}|" in k]
        d["macos_range"] = rng[0] if rng else None
        d["new_notices"] = [n for n in r.get("notices", []) if n not in base[mv]["notices"] and not n.startswith("==")][:3]
        result[mv] = d
    return result


def census(machines, macos_list=("24", "25")):
    rows = device_rows(machines)
    table = {}
    for cls, devices in rows.items():
        table[cls] = []
        for key, row in sorted(devices.items(), key=lambda kv: -kv[1]["machines"]):
            res = resolve_device(cls, row["sample"], macos_list)
            table[cls].append({"key": key, "name": row["name"], "bus": row["bus"], "machines": row["machines"],
                               "top_cpu": row["codenames"].most_common(2), "resolution": res})
    return table


def cpu_table(machines, replays):
    """CPU codename x chipset x platform with the replay outcome per macOS target."""
    t = collections.defaultdict(lambda: {"machines": 0, "ok": collections.Counter()})
    for m in machines:
        cpu = m["hardware"]["CPU"]
        k = (cpu.get("Manufacturer"), cpu.get("Codename"), m["hardware"]["Motherboard"].get("Platform"))
        t[k]["machines"] += m["machines"]
        for mv, r in (replays.get(m["key"]) or {}).items():
            t[k]["ok"][mv] += m["machines"] if r["ok"] else 0
    return t


def status(res):
    if not res["ok"]:
        return "stops the build"
    if res["kexts_added"]:
        return "kext: " + ", ".join(res["kexts_added"])
    if res["disabled"]:
        return "no driver (switched off, noted)"
    return "native or none needed"


def markdown(machines, table):
    total = sum(m["machines"] for m in machines)
    out = [f"# Field machine census\n\n{len(machines)} distinct PCs ({total} reporting machines) from Check this PC receipts and "
           "build logs, 2026-10-22 to 2026-11-07. Device IDs only. Each device's resolution is measured by replaying a baseline PC "
           "with and without it through the real builder (tools/machine_census.py), for macOS 15; macOS 26 differs only where noted.\n"]
    cpus = collections.Counter()
    for m in machines:
        c = m["hardware"]["CPU"]
        cpus[(c.get("Manufacturer"), c.get("Codename"))] += m["machines"]
    out.append("## CPU\n\n" + ", ".join(f"{a} {b} {n}" for (a, b), n in cpus.most_common(30)) + ", ...\n")
    for cls, rows in table.items():
        by = collections.Counter()
        for r in rows:
            by[status(r["resolution"]["24"]).split(":")[0]] += r["machines"]
        out.append(f"## {cls}\n\n{len(rows)} distinct devices. PCs by outcome: " + ", ".join(f"{k} {v}" for k, v in by.most_common()) + ".\n")
        gaps = [r for r in rows if not r["resolution"]["24"]["ok"] or (r["resolution"]["24"]["disabled"] and not r["resolution"]["24"]["kexts_added"])]
        if gaps:
            out.append("| devices with no driver or that stop the build | PCs | device ID | outcome |\n|---|---|---|---|")
            for r in gaps[:25]:
                out.append(f"| {(r['name'] or '')[:60]} | {r['machines']} | {r['key']} | {status(r['resolution']['24'])} |")
            out.append("")
    return "\n".join(out) + "\n"


def main(argv):
    out = md = None
    it = iter(argv)
    for a in it:
        if a == "--out":
            out = next(it)
        elif a == "--md":
            md = next(it)
    machines = machine_corpus.load()["machines"]
    table = census(machines)
    if out:
        with open(out, "w") as f:
            json.dump(table, f, indent=1, sort_keys=True, ensure_ascii=False)
    if md:
        with open(md, "w") as f:
            f.write(markdown(machines, table))
    gaps = 0
    for cls, rows in table.items():
        for r in rows:
            for mv, res in r["resolution"].items():
                if not res["ok"]:
                    gaps += 1
    print(f"{sum(len(v) for v in table.values())} distinct devices censused; {gaps} device/macOS pairs fail the baseline build")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
