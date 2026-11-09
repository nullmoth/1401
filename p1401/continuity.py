"""What Apple's Continuity features can do on this PC, from the Wi-Fi driver the build picked and the Mac model it presents.

Most Continuity features (AirDrop, Handoff, Universal Clipboard, Universal Control, Sidecar, AirPlay to Mac, Continuity
Camera, iPhone Mirroring, Instant Hotspot) talk to the other device over Apple Wireless Direct Link, a peer-to-peer
Wi-Fi mode that macOS runs as the awdl0 interface. Only a Wi-Fi driver written for Apple's IO80211 family raises awdl0:
Apple's own Broadcom driver does, a third-party Wi-Fi driver does not unless it implements it. So the feature list is
set by the Wi-Fi driver, and the build tells the user before they install instead of leaving them to find out.

The second gate is the Mac model. Sidecar, AirPlay to Mac, Universal Control and Continuity Camera each check the
model identifier, and acidanthera's FeatureUnlock exists to unlock models that Apple excluded (its README lists them:
nothing newer than MacPro6,1, iMac16 and MacBookPro12 needs it). Every model 1401 picks is newer, so no unlock kext is
needed; model_needs_unlock() keeps that true if a hand-made EFI uses an older model.

Pure functions over kext names and a model string, so they run in tests without the engine.
"""
import re

# Wi-Fi driver class by kext name (the kexts the engine's Wi-Fi menu and the community lane can select).
APPLE_NATIVE = {"AirportBrcmFixup", "AirPortBrcmNIC-Tahoe", "AirPortBrcmNIC-MFiX", "AirportBrcmNIC"}
ITLWM = {"itlwm", "AirportItlwm"}
RTW89 = {"AirportRTW89", "RTW89Legacy", "RTW89Bridge"}
NO_AWDL = {"SimpleMtkWlan", "AirPortAtheros40-Tahoe", "Feixiao", "corecaptureElCap"}

FEATURES = (
    ("AirDrop", True), ("Handoff and Universal Clipboard", True), ("Universal Control", True), ("Sidecar", True),
    ("AirPlay to Mac", True), ("Continuity Camera", True), ("iPhone Mirroring", True), ("Instant Hotspot", True),
)
# Features that also work over a cable, so a missing awdl0 does not remove them (Apple's own wired modes).
WIRED = {"Universal Control": "an iPad connected by USB", "Sidecar": "an iPad connected by USB",
         "Continuity Camera": "an iPhone connected by USB"}

# FeatureUnlock README: the highest model generation in each family that Apple's own checks exclude and the kext unlocks.
_UNLOCK_MAX = {"MacBook": 8, "MacBookAir": 7, "MacBookPro": 12, "Macmini": 7, "MacPro": 6, "iMac": 16}


def wifi_class(kexts):
    names = set(kexts or ())
    if names & APPLE_NATIVE:
        return "apple"
    if names & RTW89:
        return "rtw89"
    if names & ITLWM:
        return "itlwm"
    if names & NO_AWDL:
        return "no-awdl"
    return None


def model_needs_unlock(model):
    """True when a model identifier is one Apple's Continuity checks exclude (so FeatureUnlock would be needed)."""
    m = re.match(r"^([A-Za-z]+)(\d+),(\d+)$", str(model or ""))
    if not m:
        return False
    family, major = m.group(1), int(m.group(2))
    return family in _UNLOCK_MAX and major <= _UNLOCK_MAX[family]


def expectations(kexts, model):
    """[(feature, status, why)] with status in yes / experimental / wired-only / no. Empty when no Wi-Fi driver is known."""
    cls = wifi_class(kexts)
    if cls is None:
        return []
    rows = []
    for name, _wireless in FEATURES:
        if cls == "apple":
            status, why = "yes", "Apple's own Wi-Fi driver raises awdl0"
        elif cls == "rtw89":
            status, why = "experimental", "the RTW89 driver raises awdl0, but its transmit path is not proven on a second device"
        else:
            if name in WIRED:
                status, why = "wired-only", "works with " + WIRED[name] + "; this Wi-Fi driver does not raise awdl0"
            else:
                status, why = "no", "this Wi-Fi driver does not raise awdl0"
        if model_needs_unlock(model) and status == "yes" and name in ("Sidecar", "AirPlay to Mac", "Universal Control",
                                                                       "Continuity Camera"):
            status, why = "no", f"the Mac model {model} is excluded by Apple's own check; use a newer model or FeatureUnlock"
        rows.append((name, status, why))
    return rows


def notice(kexts, model):
    """One line for the build report, or None when everything is expected to work (or nothing is known)."""
    rows = expectations(kexts, model)
    if not rows:
        return None
    none = [n for n, s, _ in rows if s == "no"]
    wired = [n for n, s, _ in rows if s == "wired-only"]
    shaky = [n for n, s, _ in rows if s == "experimental"]
    if not (none or wired or shaky):
        return None
    parts = []
    if none:
        parts.append(", ".join(none) + " will not work with this PC's Wi-Fi driver")
    if wired:
        parts.append(", ".join(wired) + " work only with a cable")
    if shaky:
        parts.append(", ".join(shaky) + " are experimental on this Wi-Fi driver")
    return ("Continuity: " + "; ".join(parts) + ". Apple's Continuity features run over a Wi-Fi mode (AWDL) that only "
            "Apple-compatible Wi-Fi cards provide.")
