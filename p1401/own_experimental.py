"""NullMoth's own EFI drivers that have not run on enough hardware yet, put into the EFI switched off.

A driver OpenCore loads cannot be added by macOS afterwards without editing the EFI, so the build places each driver
that fits this PC in EFI/OC/Kexts with its Kernel > Add entry disabled. Nothing changes on the machine until the user
turns a driver on under Experimental drivers in the 1401 Mac app, which flips that one entry (and the boot argument the
driver waits for) and can flip it back.

  NMKbdBacklight  laptop keyboard backlight through VirtualSMC (boot argument nmkbl=1). Laptops whose EFI has VirtualSMC.
  NMHDA           HDMI and DisplayPort sound from an NVIDIA card through Apple's HD Audio driver, with volume and mute
                  (nmhdavol=1). PCs the NullMoth NVIDIA driver was selected for; macOS 15 only (macOS 26 has no Apple HD
                  Audio driver; NMXAudio serves it).

Both are built from the driver's source (kexts/NMKbdBacklight, kexts/NMHDA) against the same Lilu, VirtualSMC and
MacKernelSDK commits as the VirtualSMC set in own_virtualsmc.py, and hosted as one package on NullMoth's mirror. Any
problem (no network, a mismatching file) leaves the EFI as the engine wrote it, with a notice."""
import hashlib
import io
import os
import plistlib
import shutil
import tempfile
import zipfile

from . import mirror

PACKAGE = {
    "version": "2.9",
    "url": "https://nullmothsystems.com/mirror/41a627054f4af5f876ab2becb97f0eaa850f6a8714118e754de55eb84c018f96",
    "sha256": "41a627054f4af5f876ab2becb97f0eaa850f6a8714118e754de55eb84c018f96",
    "size": 35027,
}
COMMENT = "NullMoth experimental driver, off: turn it on in the 1401 Mac app (Experimental drivers)"
# name -> (kexts that must already be in the EFI, newest Darwin it applies to or "", what it is)
DRIVERS = {
    "NMKbdBacklight": (("Lilu", "VirtualSMC", "SMCBatteryManager"), "", "laptop keyboard backlight"),
    "NMHDA": (("Lilu",), "24.99.99", "NVIDIA HDMI and DisplayPort sound with volume on macOS 15"),
}
MAX_SIZE = 4 * 1024 * 1024


def wanted(kdir, nvidia):
    """The drivers that fit this EFI: every kext a driver needs is there, and NMHDA only beside the NVIDIA driver."""
    have = lambda k: os.path.isdir(os.path.join(kdir, k + ".kext"))  # noqa: E731
    return [n for n, (needs, _, _) in DRIVERS.items() if all(have(k) for k in needs) and (n != "NMHDA" or nvidia)]


def _unpack(data, workdir):
    if len(data) != PACKAGE["size"] or hashlib.sha256(data).hexdigest() != PACKAGE["sha256"]:
        raise ValueError("the package does not match its pinned SHA-256")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if any(n.startswith("/") or ".." in n.split("/") for n in z.namelist()):
            raise ValueError("the package holds a path outside itself")
        if sum(i.file_size for i in z.infolist()) > MAX_SIZE:
            raise ValueError("the package unpacks larger than expected")
        z.extractall(workdir)
    sums = {}
    with open(os.path.join(workdir, "SHA256SUMS"), encoding="utf-8") as fh:
        for line in fh:
            digest, _, name = line.strip().partition("  ")
            sums[name] = digest
    out = {}
    for k in DRIVERS:
        kext = os.path.join(workdir, "Kexts", k + ".kext")
        exe = os.path.join(kext, "Contents", "MacOS", k)
        if not os.path.isfile(exe) or os.path.islink(kext) or not os.path.isfile(os.path.join(kext, "Contents", "Info.plist")):
            raise ValueError(f"the package has no {k}.kext")
        with open(exe, "rb") as fh:
            if hashlib.sha256(fh.read()).hexdigest() != sums.get(k + ".kext"):
                raise ValueError(f"{k}.kext does not match the package's SHA256SUMS")
        out[k] = kext
    return out


def entry(name):
    return {"Arch": "x86_64", "BundlePath": name + ".kext", "Comment": COMMENT, "Enabled": False,
            "ExecutablePath": f"Contents/MacOS/{name}", "MaxKernel": DRIVERS[name][1], "MinKernel": "24.0.0",
            "PlistPath": "Contents/Info.plist"}


def place(out_dir, notices, nvidia=False, fetch=mirror.fetch):
    """Put the experimental drivers that fit into out_dir's EFI, each switched off. -> the names placed."""
    oc = os.path.join(out_dir, "EFI", "OC")
    kdir, cfg_path = os.path.join(oc, "Kexts"), os.path.join(oc, "config.plist")
    names = wanted(kdir, nvidia)
    if not names or not os.path.isfile(cfg_path):
        return []
    try:
        with open(cfg_path, "rb") as fh:
            cfg = plistlib.load(fh)
        add = cfg["Kernel"]["Add"]
        listed = {str(k.get("BundlePath", "")).split("/")[-1] for k in add}
        names = [n for n in names if n + ".kext" not in listed and not os.path.exists(os.path.join(kdir, n + ".kext"))]
        if not names:
            return []
        data = fetch(PACKAGE["url"])
        with tempfile.TemporaryDirectory() as tmp:
            ours = _unpack(data, tmp)
            staged = os.path.join(kdir, ".nullmoth-experimental")
            shutil.rmtree(staged, ignore_errors=True)
            os.makedirs(staged)
            for n in names:      # every copy first: a failure part-way leaves no half-placed driver
                shutil.copytree(ours[n], os.path.join(staged, n + ".kext"), symlinks=True)
            for n in names:
                os.replace(os.path.join(staged, n + ".kext"), os.path.join(kdir, n + ".kext"))
            shutil.rmtree(staged, ignore_errors=True)
        try:
            add.extend(entry(n) for n in names)      # after everything they depend on
            tmp_cfg = cfg_path + ".nullmoth-new"
            with open(tmp_cfg, "wb") as fh:
                plistlib.dump(cfg, fh, sort_keys=False)
            os.replace(tmp_cfg, cfg_path)
        except Exception:
            for n in names:      # a driver folder without its entry would fail validation: take them out again
                shutil.rmtree(os.path.join(kdir, n + ".kext"), ignore_errors=True)
            raise
    except Exception as e:  # noqa: BLE001 - an optional driver must never break a build
        notices.append(f"Experimental drivers were not added to this EFI ({type(e).__name__}: {e}); the build is otherwise complete.")
        return []
    notices.append("Experimental drivers placed in the EFI, switched off: "
                   + "; ".join(f"{n} ({DRIVERS[n][2]})" for n in names)
                   + ". Turn one on in the 1401 Mac app under Experimental drivers once macOS is running.")
    return names
