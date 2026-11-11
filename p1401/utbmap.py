"""A USB port map the user made (UTBMap.kext) replaces the generic one the builder ships.

The builder enables USBToolBox.kext with UTBDefault.kext, which turns on every port and assumes no port limit. A board
that needs its own map (a controller with more than 15 ports, or a boot USB port the default does not list: 1401 #3,
MSI B560M, port SS04) used to mean editing the EFI by hand: replace the map, order it after USBToolBox.kext, switch
UTBDefault.kext off. This does those three things for a map the user hands over.

A map is data. A folder is accepted only when it is a kext bundle with a readable Info.plist and personalities, holds no
executable and no link, and is small; anything else is named and left out, and the build keeps the default map.
"""
import os
import plistlib
import shutil

NAME = "UTBMap.kext"
MAX_BYTES = 1024 * 1024
RULE = "usb-map-import"


class Refused(Exception):
    pass


def map_status(kexts):
    """'mapped' when the build uses a UTBMap the user supplied, 'default' when UTBDefault is on with no map, 'none'
    when neither is selected. UTBDefault assumes every port is usable and no port limit; on a laptop that can make
    sleep/wake or a port unreliable, so the build says which case it is."""
    chosen = {getattr(k, "name", "") for k in (kexts or ()) if getattr(k, "checked", False)}
    if "UTBMap" in chosen:
        return "mapped"
    if "UTBDefault" in chosen:
        return "default"
    return "none"


def check(src):
    """Raises Refused with the reason when `src` is not a usable USBToolBox map; returns the bundle's Info.plist."""
    if not os.path.isdir(src) or os.path.islink(src):
        raise Refused("it is not a folder")
    total = 0
    for root, dirs, files in os.walk(src):
        for n in dirs + files:
            p = os.path.join(root, n)
            if os.path.islink(p):
                raise Refused(f"it contains a link ({os.path.relpath(p, src)})")
        for n in files:
            total += os.path.getsize(os.path.join(root, n))
    if total > MAX_BYTES:
        raise Refused("it is larger than 1 MB, which no port map is")
    if os.path.isdir(os.path.join(src, "Contents", "MacOS")) and os.listdir(os.path.join(src, "Contents", "MacOS")):
        raise Refused("it contains a program (Contents/MacOS); a port map is data only")
    plist = os.path.join(src, "Contents", "Info.plist")
    try:
        with open(plist, "rb") as fh:
            info = plistlib.load(fh)
    except (OSError, plistlib.InvalidFileException, ValueError):
        raise Refused("Contents/Info.plist is missing or unreadable") from None
    if not isinstance(info, dict) or not info.get("CFBundleIdentifier"):
        raise Refused("its Info.plist has no CFBundleIdentifier")
    if info.get("CFBundleExecutable"):
        raise Refused("its Info.plist names an executable; a port map has none")
    pers = info.get("IOKitPersonalities")
    if not isinstance(pers, dict) or not pers:
        raise Refused("its Info.plist has no IOKitPersonalities, so it maps no ports")
    return info


def apply(out_dir, src):
    """Copies the map into EFI/OC/Kexts and fixes the config. Returns change records; a refused map is a record that
    says why and changes nothing."""
    oc = os.path.join(out_dir, "EFI", "OC")
    try:
        check(src)
    except Refused as e:
        return [{"rule": RULE, "before": "", "after": "not used", "why": f"{src} was not used: {e}"}]
    cfgp = os.path.join(oc, "config.plist")
    with open(cfgp, "rb") as fh:
        cfg = plistlib.load(fh)
    add = cfg.setdefault("Kernel", {}).setdefault("Add", [])
    base = next((i for i, k in enumerate(add) if os.path.basename(k.get("BundlePath", "")) == "USBToolBox.kext"), None)
    if base is None:
        return [{"rule": RULE, "before": "", "after": "not used",
                 "why": "this build has no USBToolBox.kext, which a port map needs; the map was not added"}]
    dest = os.path.join(oc, "Kexts", NAME)
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(src, dest, symlinks=False)
    entry = {"Arch": "Any", "BundlePath": NAME, "Comment": "USB port map supplied by the user", "Enabled": True,
             "ExecutablePath": "", "MaxKernel": "", "MinKernel": "", "PlistPath": "Contents/Info.plist"}
    add[:] = [k for k in add if os.path.basename(k.get("BundlePath", "")) != NAME]
    at = next(i for i, k in enumerate(add) if os.path.basename(k.get("BundlePath", "")) == "USBToolBox.kext") + 1
    add.insert(at, entry)                                  # after USBToolBox.kext: it must load first
    off = []
    for k in add:
        if os.path.basename(k.get("BundlePath", "")) == "UTBDefault.kext" and k.get("Enabled"):
            k["Enabled"] = False
            off.append(k["BundlePath"])
    tmp = cfgp + ".tmp"
    with open(tmp, "wb") as fh:
        plistlib.dump(cfg, fh)
    os.replace(tmp, cfgp)
    return [{"rule": RULE, "before": "UTBDefault.kext (every port on)" if off else "no custom port map",
             "after": f"{NAME} after USBToolBox.kext" + (", UTBDefault.kext off" if off else ""),
             "why": "the board needs the user's own USB port map"}]
