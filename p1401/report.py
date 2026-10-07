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


def normalize(report):
    """Mutates and returns (report, notes). Each note names what was dropped and why."""
    notes = []
    # 10-07 (uploaded log NM-NX36531A): a Sniffer report with no "Input" section at all was rejected ("Root: Missing
    # required key 'Input'"). Input lists PS/2 and I2C keyboards/trackpads; the engine only uses it to pick their kexts and
    # reads a missing one as empty, so an empty section is the same build the engine would make - it just passes the check.
    if not isinstance(report.get("Input"), dict):
        report["Input"] = {}
        notes.append("Input: the report lists no keyboard/trackpad section - treated as none (no PS/2 or I2C input kexts)")
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
