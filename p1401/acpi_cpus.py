"""Processor devices the firmware declares but the MADT does not enable are hidden from macOS.

A Core Ultra HX laptop (Legion Y7000P 255HX, 1401 #141, #110) declares 29 ACPI0007 processor devices in the DSDT while
the MADT enables 20 CPUs. macOS builds its CPU list from the DSDT, so it waits for CPUs that never start and panics in
lck_ticket_lock <- thread_setrun <- timer (cpus=1 panics too: the scheduler still knows the others).

Repair: each ACPI0007 device whose _UID is not an enabled processor in the MADT gets its _HID changed to a string no
driver matches (XCPI0007, same length), with one ACPI > Patch per device limited to the DSDT. A device is named in the
patch with its own 4-character name, so the bytes are unique. It applies only when the DSDT declares more processors than
the MADT enables AND every enabled MADT processor has a device with that _UID, which shows the two tables number the
CPUs the same way; otherwise nothing is touched.
"""
import os
import plistlib

from . import madt as madt_mod

RULE = "acpi-extra-processors"
HID = b"\x08_HID\x0dACPI0007\x00"
OFF = b"\x08_HID\x0dXCPI0007\x00"


def _int(d, i):
    b = d[i]
    if b in (0, 1):
        return b, i + 1
    if b == 0x0A:
        return d[i + 1], i + 2
    if b == 0x0B:
        return int.from_bytes(d[i + 1:i + 3], "little"), i + 3
    if b == 0x0C:
        return int.from_bytes(d[i + 1:i + 5], "little"), i + 5
    return None, i


def devices(dsdt):
    """[{'name', 'uid', 'find'}] for each Device whose first object is Name(_HID, "ACPI0007"); find = its name + that Name."""
    d, out, at = bytes(dsdt), [], 0
    while True:
        at = d.find(HID, at)
        if at < 0:
            return out
        name = d[at - 4:at]
        # 5B 82 <PkgLength (1 to 4 bytes)> <name> : the lead byte of the PkgLength says how many bytes it has
        k = next((k for k in (1, 2, 3, 4) if at - 4 - k - 2 >= 0 and d[at - 4 - k - 2:at - 4 - k] == b"\x5b\x82"
                  and (d[at - 4 - k] >> 6) + 1 == k), None)
        uid = None
        if k is not None:
            j = d.find(b"\x08_UID", at + len(HID), at + len(HID) + 24)
            if j >= 0:
                uid, _ = _int(d, j + 5)
        at += len(HID)
        if k is not None and uid is not None:
            out.append({"name": name, "uid": uid, "find": name + HID})


def enabled_uids(madt):
    ids = set()
    for t, e in madt_mod.entries(madt):
        if t == 0 and len(e) >= 8 and int.from_bytes(e[4:8], "little") & 1:
            ids.add(e[2])
        elif t == 9 and len(e) >= 16 and int.from_bytes(e[8:12], "little") & 1:
            ids.add(int.from_bytes(e[12:16], "little"))
    return ids


def plan(dsdt, madt):
    """The devices to hide: [] when the tables agree or cannot be matched up."""
    devs = devices(dsdt)
    on = enabled_uids(madt)
    have = {x["uid"] for x in devs}
    if not on or len(devs) <= len(on) or not on <= have:
        return []
    extra = [x for x in devs if x["uid"] not in on]
    return [x for x in extra if bytes(dsdt).count(x["find"]) == 1]


def apply(acpi_dir, out_dir):
    def read(*names):
        p = next((os.path.join(acpi_dir, f) for f in sorted(os.listdir(acpi_dir)) if f.upper() in names), None)
        return open(p, "rb").read(8 * 1024 * 1024) if p else None
    dsdt, madt = read("DSDT.AML"), read("APIC.AML", "MADT.AML")
    if not dsdt or not madt or dsdt[:4] != b"DSDT":
        return []
    try:
        hide = plan(dsdt, madt)
    except (madt_mod.Unsupported, IndexError):
        return []
    if not hide:
        return []
    cfgp = os.path.join(out_dir, "EFI", "OC", "config.plist")
    with open(cfgp, "rb") as fh:
        cfg = plistlib.load(fh)
    patches = cfg.setdefault("ACPI", {}).setdefault("Patch", [])
    for x in hide:
        find = x["find"]
        if any(p.get("Find") == find and p.get("TableSignature") == b"DSDT" for p in patches):
            continue
        patches.append({"Base": "", "BaseSkip": 0, "Comment": f"Hide processor {x['name'].decode()} (UID {x['uid']}): not enabled in the MADT",
                        "Count": 1, "Enabled": True, "Find": find, "Limit": 0, "Mask": b"", "OemTableId": dsdt[16:24],
                        "Replace": x["name"] + OFF, "ReplaceMask": b"", "Skip": 0, "TableLength": 0, "TableSignature": b"DSDT"})
    tmp = cfgp + ".tmp"
    with open(tmp, "wb") as fh:
        plistlib.dump(cfg, fh)
    os.replace(tmp, cfgp)
    return [{"rule": RULE, "before": f"{len(devices(dsdt))} processor devices, {len(enabled_uids(madt))} enabled in the MADT",
             "after": f"{len(hide)} device(s) hidden", "why": "macOS waits for processors that never start and panics in the scheduler"}]
