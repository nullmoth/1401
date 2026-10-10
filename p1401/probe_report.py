"""Turn a 1401 Probe (the Linux USB probe) folder into the hardware report + ACPI folder the builder reads.

People who cannot run the Windows scan (no Windows, or a Windows install that will not finish the scan) send the Linux
probe instead. It measures the same hardware - PCI ids, OpenCore device paths, ACPI paths, BARs, the CPU, the board and
the ACPI tables - so the builder can make their EFI from it without a second scan. Only fields the probe measured are
filled; a section the probe has nothing for is an empty list, which the report normaliser already accepts.

    python3 -m p1401.probe_report <probe folder> <out folder>     -> <out>/report.json and <out>/ACPI/*.aml
"""
import json
import os
import re
import shutil
import sys

# SMBIOS chassis types that are portable machines (SMBIOS 3.x, 7.4.1): Portable, Laptop, Notebook, Sub Notebook,
# Convertible, Detachable. Everything else is treated as a desktop, as the Windows scan does.
LAPTOP_CHASSIS = {"8", "9", "10", "14", "31", "32"}

# AMD codenames by (family, first model): the CPU codename drives the AMD kernel patch set.
AMD_CODENAMES = [
    (0x1A, 0x40, 0x4F, "Granite Ridge"), (0x1A, 0x20, 0x2F, "Strix Point"), (0x1A, 0x60, 0x6F, "Krackan Point"),
    (0x19, 0x60, 0x6F, "Raphael"), (0x19, 0x70, 0x7F, "Phoenix"), (0x19, 0x20, 0x2F, "Vermeer"),
    (0x19, 0x50, 0x5F, "Cezanne"), (0x19, 0x40, 0x4F, "Rembrandt"), (0x17, 0x71, 0x71, "Matisse"),
    (0x17, 0x60, 0x6F, "Renoir"), (0x17, 0x08, 0x08, "Pinnacle Ridge"), (0x17, 0x01, 0x01, "Summit Ridge"),
]
AMD_CHIPSET = re.compile(r"\b([ABX]\d{3})E?\b")
INTEL_CHIPSET = re.compile(r"\b([BHQZW]\d{3})M?\b")


def _id(v):
    return (v or "").lower().replace("0x", "")[-4:].upper().rjust(4, "0")


def _pci_entry(d, name=None):
    e = {"name": name or d.get("device_name") or d.get("bdf"), "Bus Type": "PCI",
         "Device ID": f"{_id(d.get('vendor'))}-{_id(d.get('device'))}",
         "Subsystem ID": f"{_id(d.get('subsystem_device'))}{_id(d.get('subsystem_vendor'))}"}
    if d.get("oc_path"):
        e["PCI Path"] = d["oc_path"]
    if d.get("acpi_path"):
        e["ACPI Path"] = d["acpi_path"].replace("_SB_.", "_SB.")
    return e


def _codename(cpu):
    if cpu.get("vendor") != "AuthenticAMD":
        return "Unknown"
    fam, mod = cpu.get("family", 0), cpu.get("model", 0)
    for f, lo, hi, name in AMD_CODENAMES:
        if fam == f and lo <= mod <= hi:
            return name
    return "Unknown"


def convert(probe_dir, out_dir):
    rep = json.load(open(os.path.join(probe_dir, "report.json"), encoding="utf-8"))
    dmi, cpu, pci = rep.get("dmi") or {}, rep.get("cpu") or {}, rep.get("pci") or []
    amd = cpu.get("vendor") == "AuthenticAMD"
    board = " ".join(x for x in (dmi.get("board_vendor"), dmi.get("board_name")) if x)
    m = (AMD_CHIPSET if amd else INTEL_CHIPSET).search(dmi.get("board_name") or "")
    by_class = lambda pre: [d for d in pci if (d.get("class") or "").startswith(pre)]  # noqa: E731

    gpus = []
    for d in by_class("0x03"):
        vendor = {"0x10de": "NVIDIA", "0x1002": "AMD", "0x8086": "Intel"}.get(d.get("vendor"), "Unknown")
        e = _pci_entry(d)
        e.update({"Manufacturer": vendor, "Codename": "Unknown",
                  # the CPU's own graphics sits on the root complex's internal bus; a card has its own slot
                  "Device Type": "Integrated GPU" if (vendor in ("AMD", "Intel") and d.get("boot_vga") != "1"
                                                      and (vendor == "Intel" or "Radeon" in (d.get("device_name") or "")
                                                           or "Granite Ridge" in (d.get("device_name") or "")
                                                           or "Raphael" in (d.get("device_name") or "")))
                  else "Discrete GPU"})
        if vendor == "AMD" and e["Device Type"] == "Integrated GPU":
            e["Codename"] = _codename(cpu)
        # A BAR of 4 GB or more is only possible with Resizable BAR on (a card without it exposes 256 MB).
        big = [b for b in d.get("bars") or [] if b.get("prefetch") and (b.get("size") or 0) >= (4 << 30)]
        e["Resizable BAR"] = "Enabled" if big else "Disabled"
        gpus.append(e)

    report = {
        "Motherboard": {"Name": board, "Chipset": m.group(1) if m else "Unknown",
                        "Platform": "Laptop" if str(dmi.get("chassis_type")) in LAPTOP_CHASSIS else "Desktop"},
        "BIOS": {"Version": dmi.get("bios_version") or "", "Firmware Type": (rep.get("firmware") or {}).get("boot_mode", "UEFI"),
                 "Secure Boot": "Enabled" if (rep.get("firmware") or {}).get("SecureBoot") == 1 else "Disabled"},
        "CPU": {"Manufacturer": "AMD" if amd else "Intel", "Processor Name": cpu.get("brand", ""),
                "Codename": _codename(cpu), "Core Count": str(cpu.get("cores", "")).rjust(2, "0"),
                "CPU Count": str(cpu.get("packages", 1)).rjust(2, "0"),
                # same names and order as the Windows scan; SSE4a is AMD-only (the probe does not read that leaf)
                "SIMD Features": ", ".join(n for n, k in (("SSE", "sse2"), ("SSE2", "sse2"), ("SSE3", "sse3"), ("SSSE3", "ssse3"),
                                                         ("SSE4.1", "sse4_1"), ("SSE4.2", "sse4_2"), ("SSE4a", "svm"),
                                                         ("AVX", "avx"), ("AVX2", "avx2"))
                                           if (cpu.get("features") or {}).get(k) and (n != "SSE4a" or amd))},
        "GPU": gpus,
        "Network": [_pci_entry(d) for d in by_class("0x02")],
        "USB Controllers": [_pci_entry(d) for d in by_class("0x0c03")],
        "Storage Controllers": [_pci_entry(d) for d in pci if (d.get("class") or "")[:6] in ("0x0101", "0x0106", "0x0108", "0x0104")],
        "Sound": [{"name": a.get("codec", ""), "Bus Type": "HDAUDIO",
                   "Device ID": f"{a.get('vendor_id', '')[2:6].upper()}-{a.get('vendor_id', '')[6:10].upper()}"}
                  for a in rep.get("audio") or [] if isinstance(a, dict)],
        "Input": [],
        "Monitor": [],
        "Bluetooth": [],
    }
    # The Windows report keys each device section by device name (Hardware Sniffer layout); repeats get "_#n".
    for k, v in list(report.items()):
        if isinstance(v, list):
            keyed = {}
            for e in v:
                name = e.pop("name") or "Device"
                n, key = 0, name
                while key in keyed:
                    n += 1
                    key = f"{name}_#{n}"
                keyed[key] = e
            report[k] = keyed
    os.makedirs(out_dir, exist_ok=True)
    tmp = os.path.join(out_dir, "report.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    os.replace(tmp, os.path.join(out_dir, "report.json"))
    acpi = os.path.join(out_dir, "ACPI")
    os.makedirs(acpi, exist_ok=True)
    src = os.path.join(probe_dir, "acpi", "tables")
    n = 0
    for t in sorted(os.listdir(src)) if os.path.isdir(src) else []:
        if t.lower().endswith(".aml"):
            shutil.copyfile(os.path.join(src, t), os.path.join(acpi, t))
            n += 1
    if n == 0:
        raise RuntimeError(f"the probe has no ACPI tables under {src}")
    return os.path.join(out_dir, "report.json"), acpi


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    r, a = convert(sys.argv[1], sys.argv[2])
    print(r, a)
