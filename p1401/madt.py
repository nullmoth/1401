"""A MADT that lists its processors only as x2APIC entries is rewritten with ordinary Local APIC entries.

Some newer firmware (Arrow Lake: 24 logical CPUs on a Core Ultra 9 290HX) publishes every processor as MADT type 9
(Processor Local x2APIC) and none as type 0 (Processor Local APIC). macOS's ACPI platform counts the type 0 entries, finds
no processor and the kernel stops without a message (1401 #252, #64; a replacement type-0 table made one such laptop
start). The rewrite changes only the entry encoding:
  type 9  (16 bytes: x2APIC ID, flags, ACPI UID)    -> type 0 (8 bytes: ACPI UID, APIC ID, flags)
  type 10 (12 bytes: flags, ACPI UID, LINT)         -> type 4 (6 bytes: ACPI UID, flags, LINT); UID 0xFFFFFFFF becomes 0xFF
Every other entry (I/O APICs, overrides, NMI sources) is copied as it is, then the length and checksum are rewritten.
It applies only when the table has no type 0 entries at all and every ID and UID fits in one byte (below 0xFF, which
means "all processors" in the old format); otherwise the table is left to the firmware.
"""
import os
import plistlib

SHIM_FILE = "APIC-Type0.aml"
RULE = "madt-x2apic-to-lapic"
HEADER = 44   # 36-byte table header, local APIC address, flags


class Unsupported(Exception):
    pass


def entries(table):
    """[(type, bytes)] of the MADT's entries; raises Unsupported for a table that is not a well-formed MADT."""
    d = bytes(table)
    if d[:4] != b"APIC" or len(d) < HEADER or int.from_bytes(d[4:8], "little") != len(d):
        raise Unsupported("not a MADT")
    out, i = [], HEADER
    while i < len(d):
        if i + 2 > len(d) or d[i + 1] < 2 or i + d[i + 1] > len(d):
            raise Unsupported(f"entry at {i:#x} runs past the table")
        out.append((d[i], d[i:i + d[i + 1]]))
        i += d[i + 1]
    return out


def needs_rewrite(table):
    """True when the table lists processors only as x2APIC entries and they can be written as type 0."""
    ents = entries(table)
    if any(t == 0 for t, _ in ents):
        return False
    x2 = [e for t, e in ents if t == 9]
    if not x2 or any(len(e) != 16 for e in x2):
        return False
    return all(int.from_bytes(e[4:8], "little") < 0xFF and int.from_bytes(e[12:16], "little") < 0xFF for e in x2)


def rewrite(table):
    """(new table, number of processors written as type 0); (original, 0) when needs_rewrite() is false."""
    src = bytes(table)
    if not needs_rewrite(src):
        return src, 0
    body, n = bytearray(), 0
    for t, e in entries(src):
        if t == 9:
            apic, flags, uid = int.from_bytes(e[4:8], "little"), e[8:12], int.from_bytes(e[12:16], "little")
            body += bytes([0, 8, uid, apic]) + flags
            n += 1
        elif t == 10 and len(e) == 12:
            uid = int.from_bytes(e[4:8], "little")
            if uid != 0xFFFFFFFF and uid >= 0xFF:
                raise Unsupported("an x2APIC NMI entry names a processor above 254")
            body += bytes([4, 6, 0xFF if uid == 0xFFFFFFFF else uid]) + e[2:4] + e[8:9]
        else:
            body += e
    d = bytearray(src[:HEADER]) + body
    d[4:8] = len(d).to_bytes(4, "little")
    d[9] = 0
    d[9] = (-sum(d)) & 0xFF
    return bytes(d), n


def apply(acpi_dir, out_dir):
    """Ships the rewritten MADT (ACPI > Delete of the firmware's, ACPI > Add of ours) when the firmware's lists only
    x2APIC processors. Returns change records."""
    src = next((os.path.join(acpi_dir, f) for f in sorted(os.listdir(acpi_dir)) if f.upper() in ("APIC.AML", "MADT.AML")), None)
    if not src:
        return []
    try:
        with open(src, "rb") as fh:
            original = fh.read(1024 * 1024)
        fixed, n = rewrite(original)
    except Unsupported as e:
        return [{"rule": RULE, "before": "", "after": "unchanged", "why": f"MADT not checked: {e}"}]
    if not n:
        return []
    oc = os.path.join(out_dir, "EFI", "OC")
    cfgp = os.path.join(oc, "config.plist")
    with open(cfgp, "rb") as fh:
        cfg = plistlib.load(fh)
    os.makedirs(os.path.join(oc, "ACPI"), exist_ok=True)
    with open(os.path.join(oc, "ACPI", SHIM_FILE), "wb") as fh:
        fh.write(fixed)
    acpi = cfg.setdefault("ACPI", {})
    add, delete = acpi.setdefault("Add", []), acpi.setdefault("Delete", [])
    if not any((e.get("Path") or "").lower() == SHIM_FILE.lower() for e in add):
        add.append({"Comment": "MADT with the processors as Local APIC entries", "Enabled": True, "Path": SHIM_FILE})
    if not any(e.get("TableSignature") == b"APIC" and e.get("Enabled") for e in delete):
        delete.append({"All": False, "Comment": "firmware MADT lists x2APIC processors only", "Enabled": True,
                       "OemTableId": original[16:24], "TableLength": len(original), "TableSignature": b"APIC"})
    tmp = cfgp + ".tmp"
    with open(tmp, "wb") as fh:
        plistlib.dump(cfg, fh)
    os.replace(tmp, cfgp)
    return [{"rule": RULE, "before": f"{n} processor(s) only as x2APIC (MADT type 9)", "after": "the same processors as Local APIC (type 0)",
             "why": "macOS counts type 0 entries; with none the kernel stops without a message"}]
