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


def notes(report, disabled, explained=(), existing=()):
    """-> notes for every device still switched off after the driver passes.

    report: the full scan as the engine saw it (names and sections); disabled: the engine's disabled devices;
    explained: device IDs another notice already covers (community.reclaim); existing: notices so far (a device whose
    ID one of them already contains is skipped). Graphics are described by amd_gpu / intel_gpu / nullmoth, not here;
    fingerprint and face sensors are one note for all of them."""
    out, bio = [], []
    explained = {str(e).upper() for e in explained}
    wifi_ok = any(isinstance(p, dict) and _is_wifi(n, p) and n not in disabled for n, p in (report.get("Network") or {}).items())
    for name, props in (disabled or {}).items():
        props = props if isinstance(props, dict) else {}
        section, device = locate(report, name, props)
        if section is None or section == "GPU":
            continue
        name = device
        did = str(props.get("Device ID", "")).upper()
        if did and (did in explained or any(did in n.upper() for n in existing)):
            continue
        if section == "Biometric":
            bio.append(_label(name, props))
            continue
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
