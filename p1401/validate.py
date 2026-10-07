"""Checks a built EFI two ways: OpenCore's own ocvalidate (from the same release the EFI was built with), plus
file-level checks that ocvalidate doesn't do.

If the validator can't run, that's a failure, never a pass. A missing ocvalidate, a hash mismatch, or an
unreadable config all fail with the reason attached.

ocvalidate is tied to its OpenCore version (1.0.8's ocvalidate checks a 1.0.8 config), so we download the same
release zip the engine used (URL + sha256 from the engine's download history) and take ocvalidate from it.
"""
import hashlib
import json
import os
import platform
import plistlib
import subprocess
import urllib.request
import zipfile
from . import tls
tls.install()   # downloads verify against the OS certificate store + certifi

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_CACHE = os.path.join(REPO, "upstream", "OpCore-Simplify", "OCK_Files")
CACHE = os.path.join(os.path.expanduser("~"), ".cache", "1401")
TIMEOUT = 120  # seconds

# Kexts that are Lilu plugins: Lilu must load before every one of them.
LILU_PLUGINS = {"WhateverGreen.kext", "AppleALC.kext", "VirtualSMC.kext", "NVMeFix.kext", "RestrictEvents.kext",
                "CpuTopologyRebuild.kext", "NootRX.kext", "NootedRed.kext", "BlueToolFixup.kext", "CPUFriend.kext",
                "IntelBTPatcher.kext", "ECEnabler.kext", "BrightnessKeys.kext", "FeatureUnlock.kext", "HibernationFixup.kext",
                "DebugEnhancer.kext", "RadeonSensor.kext", "SMCRadeonGPU.kext", "AMDRyzenCPUPowerManagement.kext"}


class ValidatorUnavailable(RuntimeError):
    pass


def _opencore_release():
    with open(os.path.join(ENGINE_CACHE, "history.json")) as fh:
        for x in json.load(fh):
            if x["product_name"] == "OpenCorePkg":
                return x["url"], x["sha256"]
    raise ValidatorUnavailable("engine download history names no OpenCorePkg")


def ocvalidate_path():
    url, sha = _opencore_release()
    if not sha:
        raise ValidatorUnavailable(f"OpenCorePkg {url} has no sha256 - refusing an unverifiable validator")
    zpath = os.path.join(CACHE, os.path.basename(url))
    os.makedirs(CACHE, exist_ok=True)
    if not os.path.exists(zpath) or _sha256(zpath) != sha:
        tmp = zpath + ".tmp"
        req = urllib.request.Request(url, headers={"User-Agent": "1401"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r, open(tmp, "wb") as fh:
            fh.write(r.read())
        got = _sha256(tmp)
        if got != sha:
            os.remove(tmp)
            raise ValidatorUnavailable(f"{url} sha256 {got[:12]} != recorded {sha[:12]}")
        os.replace(tmp, zpath)
    name = {"Windows": "ocvalidate.exe", "Linux": "ocvalidate.linux"}.get(platform.system(), "ocvalidate")
    out = os.path.join(CACHE, sha[:12] + "-" + name)
    if not os.path.exists(out):
        with zipfile.ZipFile(zpath) as z:
            member = next((m for m in z.namelist() if m.endswith("Utilities/ocvalidate/" + name)), None)
            if not member:
                raise ValidatorUnavailable(f"{os.path.basename(url)} has no Utilities/ocvalidate/{name}")
            with z.open(member) as src, open(out + ".tmp", "wb") as dst:
                dst.write(src.read())
        os.chmod(out + ".tmp", 0o755)
        os.replace(out + ".tmp", out)
    return out


def _sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_ocvalidate(config_path):
    """Returns (ok, issues:int, text)."""
    exe = ocvalidate_path()
    p = subprocess.run([exe, config_path], capture_output=True, text=True, timeout=TIMEOUT)
    text = (p.stdout + p.stderr).strip()
    # ocvalidate exits 0 only when it found nothing; its last line says how many issues otherwise.
    issues = 0
    for line in text.splitlines():
        if "Found" in line and "issue" in line:
            issues = int("".join(c for c in line.split("Found")[1].split("issue")[0] if c.isdigit()) or 0)
    return p.returncode == 0 and issues == 0, issues, text


def invariants(efi_dir):
    """Checks the files ocvalidate never looks at. Returns a list of failures (empty means fine)."""
    oc = os.path.join(efi_dir, "EFI", "OC")
    fails = []
    with open(os.path.join(oc, "config.plist"), "rb") as fh:
        cfg = plistlib.load(fh)
    order = []
    for k in cfg["Kernel"]["Add"]:
        if not k.get("Enabled"):
            continue
        bp = os.path.join(oc, "Kexts", k["BundlePath"])
        order.append(k["BundlePath"].split("/")[-1])
        if not os.path.isdir(bp):
            fails.append(f"kext missing on disk: {k['BundlePath']}")
            continue
        if k.get("ExecutablePath") and not os.path.isfile(os.path.join(bp, k["ExecutablePath"])):
            fails.append(f"kext executable missing: {k['BundlePath']}/{k['ExecutablePath']}")
        if not os.path.isfile(os.path.join(bp, k.get("PlistPath") or "Contents/Info.plist")):
            fails.append(f"kext Info.plist missing: {k['BundlePath']}")
    if "Lilu.kext" in order:
        li = order.index("Lilu.kext")
        fails += [f"{p} loads before Lilu" for p in order[:li] if p in LILU_PLUGINS]
    elif any(p in LILU_PLUGINS for p in order):
        fails.append(f"Lilu plugins enabled without Lilu: {[p for p in order if p in LILU_PLUGINS]}")
    for a in cfg["ACPI"]["Add"]:
        if a.get("Enabled") and not os.path.isfile(os.path.join(oc, "ACPI", a["Path"])):
            fails.append(f"SSDT missing on disk: {a['Path']}")
    for d in cfg["UEFI"]["Drivers"]:
        if d.get("Enabled") and not os.path.isfile(os.path.join(oc, "Drivers", d["Path"])):
            fails.append(f"UEFI driver missing on disk: {d['Path']}")
    for t in cfg["Misc"].get("Tools", []):
        if t.get("Enabled") and not os.path.isfile(os.path.join(oc, "Tools", t["Path"])):
            fails.append(f"tool missing on disk: {t['Path']}")
    gen = cfg["PlatformInfo"].get("Generic", {})
    for key in ("SystemSerialNumber", "MLB", "SystemUUID", "SystemProductName"):
        if not gen.get(key):
            fails.append(f"PlatformInfo.Generic.{key} is empty")
    if not os.path.isfile(os.path.join(efi_dir, "EFI", "BOOT", "BOOTx64.efi")):
        fails.append("EFI/BOOT/BOOTx64.efi missing - the firmware has nothing to boot")
    return fails


def validate(efi_dir):
    """Returns a dict: ok, ocvalidate {ok, issues, text}, invariants [..], error."""
    out = {"ok": False, "ocvalidate": None, "invariants": [], "error": ""}
    try:
        ok, n, text = run_ocvalidate(os.path.join(efi_dir, "EFI", "OC", "config.plist"))
        out["ocvalidate"] = {"ok": ok, "issues": n, "text": text[-2000:]}
        out["invariants"] = invariants(efi_dir)
        out["ok"] = ok and not out["invariants"]
    except Exception as e:  # couldn't validate, so not ok; keep the reason
        out["error"] = f"{type(e).__name__}: {e}"
    return out
