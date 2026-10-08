"""Check (and optionally fix) an OpenCore EFI that 1401 did not build - one a user assembled by hand or with another tool.

python -m p1401.efidoctor <EFI parent folder or stick root> [--report Report.json] [--boot-log opencore-*.txt ...] [--fix]

The same rules 1401 applies to its own builds, run against someone else's config:
  - files: every kext, SSDT, driver and tool the config names exists, Lilu loads first (validate.invariants)
  - kext order: Lilu before its plugins, VirtualSMC before its SMC plugins
  - NullMoth driver: when the PC has a supported NVIDIA card (from Report.json) or the config already carries the
    driver's boot-args, the tested boot-args, SIP value and installer BAR setting are present
  - laptops: the NVIDIA GPU's PCI path keeps acpi-wake-type = 1 (nullmoth.laptop_gpu_awake)
  - a failed boot's own log: bootfix.py
--fix writes the corrections to config.plist after keeping config.plist.1401-backup-<time>; without it nothing is
written. Prints one line per finding and a JSON summary on the last line.
"""
import json
import os
import plistlib
import shutil
import sys
import time
from types import SimpleNamespace

from . import bootfix, nullmoth, validate

SMC_PLUGINS = {"SMCProcessor.kext", "SMCSuperIO.kext", "SMCBatteryManager.kext", "SMCLightSensor.kext", "SMCDellSensors.kext",
               "SMCRadeonGPU.kext", "SMCAMDProcessor.kext"}


def find_oc(root):
    for cand in (os.path.join(root, "EFI", "OC", "config.plist"), os.path.join(root, "OC", "config.plist"),
                 os.path.join(root, "config.plist")):
        if os.path.isfile(cand):
            return cand
    return None


def order_problems(cfg):
    names = [k.get("BundlePath", "").split("/")[-1] for k in cfg.get("Kernel", {}).get("Add", []) if k.get("Enabled")]
    out = []

    def first(n):
        return names.index(n) if n in names else None
    lilu, smc = first("Lilu.kext"), first("VirtualSMC.kext")
    for i, n in enumerate(names):
        if lilu is not None and n in validate.LILU_PLUGINS and i < lilu:
            out.append(f"{n} loads before Lilu.kext (Lilu must be first)")
        if smc is not None and n in SMC_PLUGINS and i < smc:
            out.append(f"{n} loads before VirtualSMC.kext")
    return out


def reorder(cfg):
    """Stable move of Lilu, then VirtualSMC, to the front of Kernel > Add; everything else keeps its order."""
    add = cfg.get("Kernel", {}).get("Add", [])
    rank = {"Lilu.kext": 0, "VirtualSMC.kext": 1}
    cfg["Kernel"]["Add"] = sorted(add, key=lambda k: rank.get(k.get("BundlePath", "").split("/")[-1], 2))


def check(root, report=None, boot_logs=(), fix=False):
    cfg_path = find_oc(root)
    if not cfg_path:
        return {"ok": False, "problems": ["no EFI/OC/config.plist under " + root], "would_fix": [], "written": None}
    efi_parent = os.path.dirname(os.path.dirname(os.path.dirname(cfg_path)))
    with open(cfg_path, "rb") as fh:
        cfg = plistlib.load(fh)
    problems, fixes = [], []   # problems: only the user can fix (missing files); fixes: --fix writes them
    try:
        problems += validate.invariants(efi_parent)
    except Exception as error:  # a malformed config still gets the other checks
        problems.append(f"file check could not run: {type(error).__name__}: {error}")
    order = order_problems(cfg)
    if order:   # the order is a fix, not a problem: drop validate's own wording of it
        problems = [x for x in problems if "before Lilu" not in x]
    hw = {}
    if report:
        with open(report, encoding="utf-8") as fh:
            hw = json.load(fh)
        nullmoth.mark(hw)

    def change(rule, before, after, why):
        fixes.append(f"{rule}: {before or '(unset)'} -> {after} ({why})")

    target = cfg if fix else _plist_copy(cfg)
    result = SimpleNamespace(hardware=hw, disabled_devices={})
    nv_args = ((target.get("NVRAM", {}).get("Add", {}).get("7C436110-AB2A-4BBB-A880-FE41995C9F82", {}) or {}).get("boot-args") or "")
    if hw and nullmoth.cards(hw):
        target.setdefault("NVRAM", {}).setdefault("Add", {})
        target.setdefault("DeviceProperties", {}).setdefault("Add", {})
        if nullmoth.apply(target, result, change):
            q = target.setdefault("Booter", {}).setdefault("Quirks", {})
            if q.get("ResizeAppleGpuBars") != 0:
                change("nullmoth-installer-bar", str(q.get("ResizeAppleGpuBars")), "0", "keeps the installer's screen alive on a Resizable BAR NVIDIA card")
                q["ResizeAppleGpuBars"] = 0
    elif "nvaccel=1" in nv_args and not hw:
        problems.append("the config carries the NullMoth driver's boot-args; pass --report Report.json to check the rest")
    if boot_logs:
        bootfix.apply(target, result, bootfix.read_logs(boot_logs), change)
    if order:
        reorder(target)
        fixes += ["kext-order: " + o for o in order]
    written = None
    if fix and fixes:
        backup = cfg_path + ".1401-backup-" + time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(cfg_path, backup)
        tmp = cfg_path + ".tmp"
        with open(tmp, "wb") as fh:
            plistlib.dump(cfg, fh)
        os.replace(tmp, cfg_path)
        written = {"config": cfg_path, "backup": backup}
        problems = [x for x in problems if x.startswith("the config carries")]
        try:
            problems += validate.invariants(efi_parent)   # what is still wrong in the file as written
        except Exception as error:
            problems.append(f"file check could not run: {type(error).__name__}: {error}")
    return {"ok": not problems and (not fixes or bool(written)), "problems": problems,
            ("fixed" if written else "would_fix"): fixes, "written": written}


def _plist_copy(cfg):
    return plistlib.loads(plistlib.dumps(cfg))


def main(argv=None):
    import argparse  # noqa: PLC0415
    ap = argparse.ArgumentParser(prog="1401 efidoctor")
    ap.add_argument("root")
    ap.add_argument("--report")
    ap.add_argument("--boot-log", action="append", default=[])
    ap.add_argument("--fix", action="store_true")
    a = ap.parse_args(argv)
    out = check(a.root, a.report, a.boot_log, a.fix)
    for f in out["problems"]:
        print("  problem: " + f)
    for f in out.get("fixed") or out.get("would_fix") or []:
        print(("  fixed: " if out["written"] else "  needs fixing (run with --fix): ") + f)
    if not out["problems"] and not (out.get("fixed") or out.get("would_fix")):
        print("  no problems found")
    print(json.dumps(out))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
