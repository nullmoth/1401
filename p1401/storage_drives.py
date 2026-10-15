"""Known-difficult NVMe drives. macOS has no third-party NVMe driver: a drive either answers the generic one or it
does not appear in the installer at all. Several OEM (laptop/prebuilt) NVMe families either go unseen or stall the
install, and the person finds out only after the long download and build. This classifies the drive models the scan
recorded (Storage Drives section, carried on the raw report) so the build can warn before that time is spent, and
enable NVMeFix for the families a power-state fix is known to help.

Reads from the raw scan, not the compatibility-cleaned report: the Storage Drives section is 1401's own, so the
upstream schema drops it from the cleaned copy.
"""
import re

# OEM NVMe families reported unseen by the macOS installer (no disk in Disk Utility / "Recovery doesn't detect my
# drive"). There is no software fix; the install target has to be a different SSD.
_UNSEEN = (
    (re.compile(r"\bPM9C1a\b", re.I), "Samsung PM9C1a"),
)
# OEM NVMe that reaches the installer but stalls or drops out under macOS's power management; NVMeFix (bundled with
# OpenCore) applies the APST/power-state fix these need.
_NVMEFIX = (
    (re.compile(r"\bPM98[13]\b|\bPM981a\b", re.I), "Samsung PM981/PM983"),
    (re.compile(r"\bPM991\b", re.I), "Samsung PM991"),
    (re.compile(r"\bMicron\b.*\b(2200|2210|2450|3400)\b|\bMTFDHBA\b", re.I), "Micron OEM NVMe"),
    (re.compile(r"\bBC501\b|\bBC511\b|\bBC711\b", re.I), "SK hynix BC-series"),
    (re.compile(r"\bKBG4\d|\bKBG5\d|\bKXG\d", re.I), "Kioxia BG/XG-series"),
    (re.compile(r"\bOM[38]P[DG]P[34]\b", re.I), "Kingston OM-series"),
)


def _fixed_drives(raw_hardware):
    """(name, model) for every internal (non-USB) drive the scan recorded. USB is the install stick, never the target."""
    drives = (raw_hardware or {}).get("Storage Drives")
    if not isinstance(drives, dict):
        return []
    out = []
    for name, props in drives.items():
        if not isinstance(props, dict):
            continue
        if str(props.get("Bus Type") or "").upper() == "USB":
            continue
        model = str(props.get("Model") or name or "").strip()
        if model:
            out.append((str(name), model))
    return out


def _match(model, table):
    for pattern, label in table:
        if pattern.search(model):
            return label
    return None


def unseen_drives(raw_hardware):
    """Internal drives whose family the macOS installer does not show (model label, de-duplicated)."""
    seen = []
    for _, model in _fixed_drives(raw_hardware):
        label = _match(model, _UNSEEN)
        if label and label not in seen:
            seen.append(label)
    return seen


def wants_nvmefix(raw_hardware):
    return any(_match(model, _NVMEFIX) for _, model in _fixed_drives(raw_hardware))


def any_supported_fixed_drive(raw_hardware):
    """True when at least one internal drive is not in the unseen set, so a build still has a target."""
    fixed = _fixed_drives(raw_hardware)
    return any(_match(model, _UNSEEN) is None for _, model in fixed) if fixed else True


def warning(raw_hardware):
    """The one-line caution to show before the build, or '' when the drives raise nothing."""
    unseen = unseen_drives(raw_hardware)
    parts = []
    if unseen:
        where = "the only internal drive is" if not any_supported_fixed_drive(raw_hardware) else "an internal drive is"
        parts.append("The macOS installer does not detect " + ", ".join(unseen)
                     + " (" + where + " this family); install macOS to a different SSD if no disk appears.")
    if wants_nvmefix(raw_hardware):
        parts.append("This PC has an OEM NVMe drive that can drop out under macOS power management; the build enables "
                     "NVMeFix for it.")
    return " ".join(parts)
