"""Cleans up a Hardware Sniffer report before the engine's validator sees it.

Reports in the wild come from older Sniffer versions. Something the validator rejects only gets dropped here if
dropping it can't change the EFI; everything else still fails in the engine's validator.
Example from the corpus (z490-vision-g): a Focusrite USB interface with Bus Type FOCUSRITEUSB and no Device ID.
USB audio is class-compliant (macOS drives it without a kext), so it never ends up in the EFI anyway.
"""
import json
import os
import hashlib
import copy

# section -> can an entry with no Device ID be dropped? (only where the EFI can't depend on it)
DROPPABLE = {
    "Sound": lambda p: p.get("Bus Type") not in ("HDAUDIO", "PCI"),
}


PCI_VENDORS = {"10DE": "NVIDIA", "1002": "AMD", "8086": "Intel"}
# makers as their cards' names spell them, for a card Windows reports with neither a maker nor a PCI ID
NAME_VENDORS = (("NVIDIA", ("nvidia", "geforce", "quadro", "tesla", "titan ")), ("AMD", ("radeon", "amd ", "ati ", "firepro")),
                ("Intel", ("intel", "iris", "uhd graphics", "hd graphics", "arc ")))


def vendor_from_name(name):
    low = " " + (name or "").lower() + " "
    return next((v for v, words in NAME_VENDORS if any(w in low for w in words)), None)


def acpi_fingerprints(directory):
    """Correlate a failed build with its probe without exporting ACPI contents or paths."""
    found = []
    try:
        names = sorted(os.listdir(directory))[:128]
    except OSError:
        return found
    for name in names:
        if not name.lower().endswith(('.aml', '.dat')):
            continue
        path = os.path.join(directory, name)
        if os.path.islink(path) or not os.path.isfile(path):
            continue
        try:
            with open(path, 'rb') as stream:
                signature = stream.read(4)
                if signature not in (b'DSDT', b'APIC'):
                    continue
                data = signature + stream.read(8 * 1024 * 1024)
                if len(data) > 8 * 1024 * 1024:
                    continue
        except OSError:
            continue
        record = {'signature': signature.decode('ascii'), 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        if record not in found:
            found.append(record)
        if len(found) == 8:
            break
    return found


def diagnostic_hardware(report):
    """Keep device identity in failed-build logs without exporting the complete scan."""
    fields = {
        "CPU": ("Manufacturer", "Processor Name", "Codename", "Core Count", "Thread Count", "CPU Count", "CPU Signature", "CPUID", "Family", "Model", "Stepping", "P-Core Count", "E-Core Count"),
        "Motherboard": ("Name", "Manufacturer", "Chipset", "Platform", "Version"),
        "BIOS": ("Firmware Type", "Version"),
        "GPU": ("Manufacturer", "Device ID", "Subsystem ID", "Device Type", "Codename", "PCI Path", "Resizable BAR", "ACPI Path", "Bus Type"),
        "Network": ("Device ID", "Subsystem ID", "Bus Type", "PCI Path", "ACPI Path"),
        "USB Controllers": ("Device ID", "Subsystem ID", "PCI Path", "ACPI Path", "Bus Type"),
        "Monitor": ("Connected GPU", "Connector Type"),
        "Storage Controllers": ("Device ID", "Subsystem ID", "Bus Type", "PCI Path", "ACPI Path"),
        "Storage Drives": ("Model", "Bus Type", "Media Type", "Size", "System"),
        "Input": ("Device ID", "Bus Type", "ACPI Path", "PCI Path"),
        "Sound": ("Device ID", "Subsystem ID", "Bus Type", "Codec ID", "PCI Path", "ACPI Path"),
        "Bluetooth": ("Device ID", "Bus Type", "PCI Path", "ACPI Path"),
        "SD Controller": ("Device ID", "Subsystem ID", "Bus Type", "PCI Path", "ACPI Path"),
        "Biometric": ("Device ID", "Bus Type"),
    }

    def select(props, allowed):
        return {key: value for key, value in props.items()
                if key in allowed and isinstance(value, (str, int, bool))
                and (not isinstance(value, str) or len(value) <= 512)}

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
            result[section] = [{"name": name[:512] if isinstance(name, str) else "unnamed device", **select(props, allowed)} for name, props in list(value.items())[:256]
                               if isinstance(props, dict)]
    if result:
        result["not_observed"] = ["USB port-to-connector routing", "BIOS setup options", "GPU BAR/VRAM size", "CPUID leaves",
                                  "fan and RGB wiring"]
    return result


def normalize(report):
    """Mutates and returns (report, notes). Each note names what was dropped and why."""
    notes = []
    # 10-07 (an uploaded log): a Sniffer report with no "Input" section at all was rejected ("Root: Missing
    # required key 'Input'"). Input lists PS/2 and I2C keyboards/trackpads; the engine only uses it to pick their kexts and
    # reads a missing one as empty, so an empty section is the same build the engine would make - it just passes the check.
    if not isinstance(report.get("Input"), dict):
        report["Input"] = {}
        notes.append("Input: the report lists no keyboard/trackpad section - treated as none (no PS/2 or I2C input kexts)")
    # 10-09 (14 uploaded logs, "hardware report rejected: Missing required key 'USB Controllers'/'Storage Controllers'"):
    # an older or partial scan can omit these whole sections. The engine reads a missing section as none - the same build
    # it would make with an empty one - so treat missing as empty and let the build proceed instead of refusing the report.
    # A machine with no Storage Controllers section just gets no storage-specific quirks (e.g. VMD is not detected from it);
    # the user can send a fuller scan to improve it. Keep this in step with the engine's required-key list.
    for sec in ("USB Controllers", "Storage Controllers"):
        if not isinstance(report.get(sec), dict):
            report[sec] = {}
            notes.append(f"{sec}: the report has no {sec.lower()} section - treated as none; the build continues "
                         "(a fuller scan adds the matching quirks)")
    # 10-07: Hardware Sniffer asks PowerShell for $env:firmware_type, and a PowerShell profile that prints
    # a banner lands in the value ("Linux Rice loaded!\nUEFI"), so the schema rejected the whole report. Keep the real word.
    bios = report.get("BIOS") if isinstance(report.get("BIOS"), dict) else None
    ft = (bios or {}).get("Firmware Type")
    if isinstance(ft, str) and ft not in ("UEFI", "BIOS"):
        word = "UEFI" if "UEFI" in ft.upper() else "BIOS" if ("BIOS" in ft.upper() or "LEGACY" in ft.upper()) else None
        if word:
            bios["Firmware Type"] = word
            notes.append(f"BIOS: firmware type read as {ft!r} (extra text from PowerShell) - taken as {word}")
    _field_gaps(report, notes)
    # 10-07: a card Windows has no driver for shows up as "Microsoft Basic Display Adapter" with
    # Manufacturer 'Unknown', and the engine's schema rejects the whole report. The PCI vendor in its Device ID still
    # names the maker, so take it from there; a card with no usable ID is dropped if another GPU remains.
    gpus = report.get("GPU") or {}
    for name, props in list(gpus.items()):
        if not isinstance(props, dict) or props.get("Manufacturer") in PCI_VENDORS.values():
            continue
        vendor = PCI_VENDORS.get((props.get("Device ID") or "")[:4].upper())
        if not vendor and vendor_from_name(name):
            # 1.10 builds 10-10 (5 times, one AMD PC): "The only graphics card Windows reports is 'NVIDIA GeForce GT 730',
            # with no maker or PCI ID" - the name says who made it. Without an ID it is not a card the driver can claim,
            # so the build goes on with macOS's basic display for it instead of stopping.
            props["Manufacturer"] = vendor_from_name(name)
            # the engine reads the GPU's Device ID (compatibility_checker slices it): device 0000 matches no card macOS or
            # the driver supports, so the plan is basic display - which is all an unidentified card can get
            props.setdefault("Device ID", {v: k for k, v in PCI_VENDORS.items()}[props["Manufacturer"]] + "-0000")
            notes.append(f"GPU: {name!r} reported no maker or PCI ID; its name says {props['Manufacturer']} - planned with "
                         "macOS's basic display. Installing the card's Windows driver and scanning again gives a fuller report.")
            continue
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


# Words that make a chassis a laptop when Windows gave no usable platform type.
_LAPTOP_WORDS = ("laptop", "notebook", "thinkpad", "ideapad", "legion", "zenbook", "vivobook", "macbook", "xps", "inspiron",
                 "latitude", "pavilion", "elitebook", "probook", "spectre", "envy", "swift", "aspire", "predator", "nitro",
                 "rog zephyrus", "rog strix g", "tuf gaming f", "tuf gaming a", "victus", "omen", "loq", "yoga", "surface",
                 "thin gf", "katana", "stealth", "vector", "raider", "titan gt", "blade")


def _field_gaps(report, notes):
    """Scans from the field that the engine's validator refuses although the EFI does not depend on the missing part
    (1.x to 2.8 build logs: Network 8 PCs, SD Controller 12, USB Controllers 2, Motherboard Platform 5, CPU maker 6)."""
    # A PC whose adapters are all disabled or driverless in Windows reports no Network section at all. The engine reads a
    # missing section as none; the build then says the installer has no network (netsupport) instead of refusing the scan.
    if not isinstance(report.get("Network"), dict):
        report["Network"] = {}
        notes.append("Network: Windows reported no network adapter - treated as none; the installer will need the offline "
                     "(local image) path, and Ethernet or Wi-Fi can be added later")
    # A card reader Windows lists only as the generic SD host class has no vendor or device ID to match; macOS has no
    # driver for it either way, so dropping the entry does not change the EFI.
    for name, props in list((report.get("SD Controller") or {}).items()):
        if isinstance(props, dict) and not props.get("Device ID"):
            del report["SD Controller"][name]
            notes.append(f"SD Controller: {name!r} has no device ID in this report - left out (macOS has no driver for a "
                         "generic card reader; a USB card reader works)")
    # The USB controller's bus is PCI whenever it has a PCI path; a missing Bus Type is a gap in the scan, not a different bus.
    for name, props in (report.get("USB Controllers") or {}).items():
        if isinstance(props, dict) and not props.get("Bus Type"):
            props["Bus Type"] = "PCI"
    board = report.get("Motherboard")
    if isinstance(board, dict) and board.get("Platform") not in ("Desktop", "Laptop"):
        low = str(board.get("Name", "")).lower()
        guess = "Laptop" if any(w in low for w in _LAPTOP_WORDS) else "Desktop"
        notes.append(f"Motherboard: the chassis type was read as {board.get('Platform')!r}; taken as {guess} from the board "
                     "name. If this is wrong, run Check this PC again.")
        board["Platform"] = guess
    cpu = report.get("CPU")
    if isinstance(cpu, dict) and cpu.get("Manufacturer") not in ("Intel", "AMD"):
        raise RuntimeError(f"This PC's processor reports its maker as {cpu.get('Manufacturer')!r} "
                           f"({cpu.get('Processor Name', 'unnamed')}). macOS runs only on Intel and AMD processors, and 1401 has "
                           "no tested setup for other x86 makers (Hygon, Zhaoxin and similar), so it cannot build an EFI for this PC.")


def normalized_copy(report_path, dest_dir, raw_hardware=None):
    """Normalize a private copy of the parsed input, or read a standalone imported report."""
    if raw_hardware is None:
        with open(report_path, encoding="utf-8") as fh:
            hardware = json.load(fh)
    else:
        hardware = copy.deepcopy(raw_hardware)
    report, notes = normalize(hardware)
    out = os.path.join(dest_dir, "Report.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    return out, notes
