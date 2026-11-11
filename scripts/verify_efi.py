#!/usr/bin/env python3
"""File-level verification of a built EFI against the scan and the Huawei expectations. Read-only.

    .venv/Scripts/python.exe scripts/verify_efi.py out/huawei-efi-final3 --json-out reports/hardware/efi-file-check.json

This checks what is on disk: required files, every kext/ACPI/driver entry resolves, the config's hardware choices match
the scan, and OpenCore's own ocvalidate passes. It does not claim a boot: a real Mac/macOS run is separate.
"""
import argparse
import hashlib
import json
import os
import plistlib
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from p1401 import validate  # noqa: E402


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("efi")
    parser.add_argument("--json-out")
    args = parser.parse_args()
    root = os.path.abspath(args.efi)
    oc = os.path.join(root, "EFI", "OC")
    cfg_path = os.path.join(oc, "config.plist")
    out = {"ok": False, "efi": root, "checks": [], "errors": []}

    def check(name, condition, detail=""):
        out["checks"].append({"check": name, "ok": bool(condition), "detail": detail})
        if not condition:
            out["errors"].append(name + (": " + detail if detail else ""))

    if not os.path.isfile(cfg_path):
        out["errors"].append("EFI/OC/config.plist is missing")
        print(json.dumps(out, indent=1))
        return 1
    with open(cfg_path, "rb") as fh:
        cfg = plistlib.load(fh)
    check("config has every OpenCore section", all(isinstance(cfg.get(k), dict) for k in
          ("ACPI", "Booter", "DeviceProperties", "Kernel", "Misc", "NVRAM", "PlatformInfo", "UEFI")))
    required = ["EFI/BOOT/BOOTx64.efi", "EFI/OC/OpenCore.efi", "EFI/OC/config.plist"]
    for rel in required:
        check("required file " + rel, os.path.isfile(os.path.join(root, *rel.split("/"))))
    for entry in cfg.get("Kernel", {}).get("Add", []):
        rel = os.path.join("EFI", "OC", "Kexts", entry.get("BundlePath", ""))
        check("kext entry resolves " + entry.get("BundlePath", "?"), os.path.exists(os.path.join(root, rel)))
    for entry in cfg.get("ACPI", {}).get("Add", []):
        rel = os.path.join("EFI", "OC", "ACPI", entry.get("Path", ""))
        check("ACPI entry resolves " + entry.get("Path", "?"), os.path.isfile(os.path.join(root, rel)))
    for entry in cfg.get("UEFI", {}).get("Drivers", []):
        rel = os.path.join("EFI", "OC", "Drivers", entry.get("Path", ""))
        check("driver entry resolves " + entry.get("Path", "?"), os.path.isfile(os.path.join(root, rel)))
    kexts = {os.path.basename(k.get("BundlePath", "")) for k in cfg.get("Kernel", {}).get("Add", [])
             if k.get("Enabled", True)}
    for want in ("WhateverXe.kext", "itlwm.kext", "USBToolBox.kext", "UTBDefault.kext", "VoodooI2C.kext",
                 "VoodooI2CHID.kext", "VoodooPS2Controller.kext", "Lilu.kext", "VirtualSMC.kext"):
        check("Huawei-relevant kext " + want, want in kexts, "present" if want in kexts else "missing")
    acpi = {a.get("Path") for a in cfg.get("ACPI", {}).get("Add", [])}
    for want in ("SSDT-PLUG-ALT.aml", "SSDT-PNLF.aml", "SSDT-GPI0.aml", "SSDT-USBX.aml", "SSDT-XOSI.aml"):
        check("ACPI table " + want, want in acpi, "present" if want in acpi else "missing")
    boot_args = (cfg.get("NVRAM", {}).get("Add", {}).get("7C436110-AB2A-4BBB-A880-FE41995C9F82", {})
                 .get("boot-args", ""))
    for arg in ("ctrsmt=full", "-vi2c-force-polling", "-ibtcompatbeta"):
        check("boot-arg " + arg, arg in boot_args, boot_args)
    emu = cfg.get("Kernel", {}).get("Emulate", {})
    data = bytes(emu.get("Cpuid1Data") or b"")
    mask = bytes(emu.get("Cpuid1Mask") or b"")
    check("Huawei topology CPUID byte 6 = 128", len(data) >= 7 and data[6] == 128, data.hex())
    check("Huawei topology CPUID mask byte 6 = 255", len(mask) >= 7 and mask[6] == 255, mask.hex())
    product = cfg.get("PlatformInfo", {}).get("Generic", {}).get("SystemProductName")
    check("SMBIOS MacBookPro16,2", product == "MacBookPro16,2", str(product))
    booter = cfg.get("Booter", {}).get("Quirks", {})
    check("DevirtualiseMmio is off", booter.get("DevirtualiseMmio") is False, str(booter.get("DevirtualiseMmio")))
    check("DisableIoMapper is on", cfg.get("Kernel", {}).get("Quirks", {}).get("DisableIoMapper") is True,
          str(cfg.get("Kernel", {}).get("Quirks", {}).get("DisableIoMapper")))
    try:
        validated = validate.validate(root)
        check("OpenCore ocvalidate", validated.get("ok") is True,
              json.dumps(validated.get("ocvalidate") or validated.get("error"))[:500])
    except Exception as e:  # noqa: BLE001 - the reason is the result
        check("OpenCore ocvalidate", False, f"{type(e).__name__}: {e}")
    out["ok"] = not out["errors"]
    out["sha256"] = {"EFI/OC/config.plist": sha256(cfg_path),
                     "EFI/OC/OpenCore.efi": sha256(os.path.join(oc, "OpenCore.efi"))}
    out["counts"] = {"kexts": len(cfg.get("Kernel", {}).get("Add", [])),
                     "acpi": len(cfg.get("ACPI", {}).get("Add", [])),
                     "drivers": len(cfg.get("UEFI", {}).get("Drivers", []))}
    out["note"] = ("File-level and ocvalidate verification only. Booting this EFI and installing macOS require the "
                   "real machine and were not performed in this project.")
    text = json.dumps(out, indent=1, ensure_ascii=False)
    print(text)
    if args.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
