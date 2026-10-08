"""Cleans up a Hardware Sniffer report before the engine's validator sees it.

Reports in the wild come from older Sniffer versions. Something the validator rejects only gets dropped here if
dropping it can't change the EFI; everything else still fails in the engine's validator.
Example from the corpus (z490-vision-g): a Focusrite USB interface with Bus Type FOCUSRITEUSB and no Device ID.
USB audio is class-compliant (macOS drives it without a kext), so it never ends up in the EFI anyway.
"""
import json
import os

# section -> can an entry with no Device ID be dropped? (only where the EFI can't depend on it)
DROPPABLE = {
    "Sound": lambda p: p.get("Bus Type") not in ("HDAUDIO", "PCI"),
}


PCI_VENDORS = {"10DE": "NVIDIA", "1002": "AMD", "8086": "Intel"}


def diagnostic_hardware(report):
    """Keep device identity in failed-build logs without exporting the complete scan."""
    fields = {
        "CPU": ("Manufacturer", "Processor Name", "Codename", "Core Count", "Thread Count"),
        "Motherboard": ("Name", "Manufacturer", "Chipset", "Platform"),
        "BIOS": ("Firmware Type", "Version"),
        "GPU": ("Manufacturer", "Device ID", "Subsystem ID", "Device Type", "Codename", "PCI Path"),
        "Network": ("Device ID", "Subsystem ID", "Bus Type", "PCI Path"),
        "USB Controllers": ("Device ID", "Subsystem ID", "PCI Path"),
        "Monitor": ("Connected GPU", "Connector Type"),
    }

    def select(props, allowed):
        return {key: value for key, value in props.items()
                if key in allowed and isinstance(value, (str, int, bool))}

    result = {}
    if not isinstance(report, dict):
        return result
    for section, allowed in fields.items():
        value = report.get(section)
        if not isinstance(value, dict):
            continue
        if section in ("CPU", "Motherboard", "BIOS"):
            result[section] = select(value, allowed)
        else:
            result[section] = [{"name": name, **select(props, allowed)} for name, props in value.items()
                               if isinstance(props, dict)]
    return result


def normalize(report):
    """Mutates and returns (report, notes). Each note names what was dropped and why."""
    notes = []
    # 10-07 (uploaded log NM-NX36531A): a Sniffer report with no "Input" section at all was rejected ("Root: Missing
    # required key 'Input'"). Input lists PS/2 and I2C keyboards/trackpads; the engine only uses it to pick their kexts and
    # reads a missing one as empty, so an empty section is the same build the engine would make - it just passes the check.
    if not isinstance(report.get("Input"), dict):
        report["Input"] = {}
        notes.append("Input: the report lists no keyboard/trackpad section - treated as none (no PS/2 or I2C input kexts)")
    # 10-07 (NM-WJBMSV8B): Hardware Sniffer asks PowerShell for $env:firmware_type, and a PowerShell profile that prints
    # a banner lands in the value ("Linux Rice loaded!\nUEFI"), so the schema rejected the whole report. Keep the real word.
    bios = report.get("BIOS") if isinstance(report.get("BIOS"), dict) else None
    ft = (bios or {}).get("Firmware Type")
    if isinstance(ft, str) and ft not in ("UEFI", "BIOS"):
        word = "UEFI" if "UEFI" in ft.upper() else "BIOS" if ("BIOS" in ft.upper() or "LEGACY" in ft.upper()) else None
        if word:
            bios["Firmware Type"] = word
            notes.append(f"BIOS: firmware type read as {ft!r} (extra text from PowerShell) - taken as {word}")
    # 10-07 (NM-S9BPDPZQ): a card Windows has no driver for shows up as "Microsoft Basic Display Adapter" with
    # Manufacturer 'Unknown', and the engine's schema rejects the whole report. The PCI vendor in its Device ID still
    # names the maker, so take it from there; a card with no usable ID is dropped if another GPU remains.
    gpus = report.get("GPU") or {}
    for name, props in list(gpus.items()):
        if not isinstance(props, dict) or props.get("Manufacturer") in PCI_VENDORS.values():
            continue
        vendor = PCI_VENDORS.get((props.get("Device ID") or "")[:4].upper())
        if vendor:
            props["Manufacturer"] = vendor
            notes.append(f"GPU: {name!r} has no Windows driver (maker read from its PCI ID {props['Device ID']}: {vendor}). "
                         "Installing the card's driver in Windows and scanning again gives a fuller report.")
        elif len(gpus) > 1:
            del gpus[name]
            notes.append(f"GPU: {name!r} names no maker and no PCI ID - left out; the other graphics card is used")
        else:
            raise RuntimeError(f"The only graphics card Windows reports is {name!r}, with no maker or PCI ID: Windows has no "
                               "driver for it. Install your graphics card's driver in Windows (from NVIDIA, AMD or Intel), "
                               "restart, and run Check this PC again.")
    for section, may_drop in DROPPABLE.items():
        for name, props in list((report.get(section) or {}).items()):
            if isinstance(props, dict) and "Device ID" not in props and may_drop(props):
                del report[section][name]
                notes.append(f"{section}: {name!r} (bus {props.get('Bus Type')}) has no Device ID in this report - "
                             "USB audio needs no kext; macOS drives it natively")
    return report, notes


def normalized_copy(report_path, dest_dir):
    with open(report_path, encoding="utf-8") as fh:
        report, notes = normalize(json.load(fh))
    out = os.path.join(dest_dir, "Report.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    return out, notes
