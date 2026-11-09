"""Plain-words notes for devices macOS cannot drive, with what to do instead.

The engine switches off a device it has no driver for and lists it as "Unsupported" in its compatibility transcript. That
line is easy to miss, and for a Wi-Fi card, a Bluetooth adapter or a card reader it is the whole story the owner gets:
macOS installs, then the radio or the slot is simply dead. This module writes one sentence per such device, naming it
and its ID, saying what will not work and what does work. It runs after every driver pass, so a device a driver was found
for (community.reclaim, netsupport) is never reported as lost.
"""
import re

WIFI_WORDS = ("wi-fi", "wifi", "wireless", "wlan", "802.11", "wi fi", "be200", "be201", "ax200", "ax201", "ax203", "ax210",
              "ax211", "ax411", "qca6", "qca9", "wcn", "fastconnect", "mt79", "mt76", "rtl88", "rtl81", "rtw8", "ar9", "bcm43",
              "bcm94")


def _is_wifi(name, props):
    low = f"{name} {props.get('Name', '')}".lower()
    return any(w in low for w in WIFI_WORDS)


def locate(report, key, props=None):
    """(section, device name) in the scan for one key of the engine's disabled set. The engine writes the key as
    "<category>: <device name>" with an optional " (audio endpoints)" suffix, so the name is looked up in every section and
    the device ID breaks a tie. -> (None, None) when the scan holds no such device."""
    name = key.split(": ", 1)[1] if ": " in key else key
    want = (props or {}).get("Device ID")
    for sec, devs in (report or {}).items():
        if not isinstance(devs, dict):
            continue
        for cand, p in devs.items():
            if (name == cand or name.startswith(cand + " (")) and isinstance(p, dict) and (want is None or p.get("Device ID") == want):
                return sec, cand
    return None, None


def _label(name, props):
    did = props.get("Device ID")
    return f"{name} ({did})" if did else name


def _text(section, name, props, wifi_ok):
    label = _label(name, props)
    if section == "Network":
        if _is_wifi(name, props):
            return (f"Wi-Fi: {label} has no macOS driver, so this PC will have no Wi-Fi in macOS. Use Ethernet, or an "
                    "iPhone's USB tethering; or replace the card with one macOS drives, such as an Intel AX200 or AX210 "
                    "(M.2, Key E).")
        return (f"Ethernet: {label} has no macOS driver, so this port will not connect in macOS. "
                + ("Wi-Fi works on this PC. " if wifi_ok else "")
                + "A USB Ethernet adapter based on a Realtek RTL8153 or ASIX AX88179 chip works.")
    if section == "Bluetooth":
        return (f"Bluetooth: {label} has no macOS driver, so Bluetooth keyboards, mice and headphones will not connect "
                "through it. Use a USB Bluetooth adapter built on a Broadcom chip, or wired or 2.4 GHz-dongle devices.")
    if section == "SD Controller":
        return (f"Card reader: {label} has no macOS driver, so the SD card slot will not work. A USB card reader does.")
    if section == "Storage Controllers":
        return (f"Drive: {label} is a storage device macOS is known not to work with, so 1401 leaves it out of the setup. "
                "Install macOS on another drive (a different SSD, a SATA SSD or a USB SSD); this one cannot hold macOS.")
    if section == "Sound":
        if str(props.get("Device ID", "")).upper().startswith("10DE"):
            return (f"Sound: {label} (audio over HDMI or DisplayPort from the graphics card) is not set up in macOS. "
                    "Use the motherboard's audio jacks or a USB audio device.")
        return (f"Sound: {label} has no macOS driver. Use the motherboard's main audio or a USB audio device; USB and "
                "Bluetooth audio need no driver.")
    if section == "Input":
        return f"Input: {label} has no macOS driver. A USB keyboard and mouse work."
    if section == "USB Controllers":
        return f"USB: {label} has no macOS driver, so ports on it will not work. Use ports on the other controllers."
    return None


def _darwin(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return None


def _darwin_range(props):
    """'macOS Darwin lowest to highest' for a device's engine compatibility, in words a person can read."""
    comp = props.get("Compatibility")
    if not isinstance(comp, (list, tuple)) or len(comp) < 2 or comp[0] is None:
        return "no macOS version"
    names = {"17": "macOS 10.13", "18": "10.14", "19": "10.15", "20": "11", "21": "12", "22": "13", "23": "14", "24": "15", "25": "26"}
    lo, hi = str(comp[-1]).split(".")[0], str(comp[0]).split(".")[0]
    return f"works with macOS {names.get(lo, lo)} to {names.get(hi, hi)}"


def has_driver(props, macos):
    """True when the engine's own compatibility range for this device contains the chosen macOS (the device is then switched
    off only because another device of its kind was picked), False when macOS has no driver for it on this version."""
    comp = props.get("Compatibility")
    want = _darwin(macos)
    if not isinstance(comp, (list, tuple)) or len(comp) < 2 or want is None:
        return False
    hi, lo = _darwin(comp[0]), _darwin(comp[-1])
    return bool(hi and lo and hi >= want >= lo)


def _names(section_devices):
    return ", ".join(sorted(section_devices)) if section_devices else ""


def _graphics(label, props, macos, kept):
    if has_driver(props, macos):
        return (f"Graphics: {label} is switched off in macOS because " + (f"{kept} drives the display instead" if kept else
                "another graphics adapter was chosen") + ". That is the usual setup for a PC with a graphics card.")
    drives = (f"{kept} drives the display" if kept else
              "macOS shows the picture through the firmware's basic display (the desktop and apps work, with no graphics acceleration)")
    return (f"Graphics: {label} has no macOS driver on this macOS version, so it is switched off; {drives}. "
            "The NullMoth driver covers GeForce GTX 16 series and newer.")


def _deselected(section, label, kept):
    kind = {"Network": "Wi-Fi card", "Bluetooth": "Bluetooth adapter"}.get(section, "device")
    return (f"{label} is left off: macOS uses one {kind}" + (f", {kept}" if kept else "") + ", and the other one is switched off.")


def notes(report, disabled, customization=None, macos=None, explained=(), existing=()):
    """-> notes for every device still switched off after the driver passes.

    report: the full scan as the engine saw it (names and sections); disabled: the engine's disabled devices;
    customization: the devices kept; macos: the Darwin version chosen; explained: device IDs another notice already
    covers (community.reclaim); existing: notices so far (a device whose ID one of them contains is skipped).
    A device with a driver that is off because another of its kind was picked is said so, not reported as lost."""
    out, bio = [], []
    explained = {str(e).upper() for e in explained}
    existing = [n for n in existing if "\n" not in n]     # the engine's multi-line transcripts print every ID; they explain nothing
    customization = customization or {}
    wifi_ok = any(isinstance(p, dict) and _is_wifi(n, p) and n not in disabled for n, p in (report.get("Network") or {}).items())
    for key, props in (disabled or {}).items():
        props = props if isinstance(props, dict) else {}
        section, name = locate(report, key, props)
        if section is None:
            continue
        did = str(props.get("Device ID", "")).upper()
        if did and (did in explained or any(did in n.upper() for n in existing)):
            continue
        label = _label(name, props)
        kept = _names(customization.get(section))
        if section == "GPU":
            out.append(_graphics(label, props, macos, kept))
        elif section == "Biometric":
            bio.append(label)
        elif has_driver(props, macos) and section in ("Network", "Bluetooth"):
            out.append(_deselected(section, label, kept))
        else:
            text = _text(section, name, props, wifi_ok)
            if text:
                out.append(text)
    if bio:
        out.append("Fingerprint or face sign-in: " + "; ".join(bio) + ". macOS does not support PC fingerprint or face "
                   "sensors (Touch ID needs Apple's own security chip), so sign in with the password.")
    return out


def explained_ids(notices):
    """Device IDs (VVVV-DDDD) named in a list of notices; the replay gate uses it to prove every dropped device is explained."""
    return {m.upper() for n in notices for m in re.findall(r"\b[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}\b", n)}
