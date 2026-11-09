"""ACPI methods the firmware declares but macOS's interpreter cannot use, replaced by a table that answers.

AMD laptops carry a vendor SSDT (OEM Table ID "Vortex", "AmdTable" and others) whose Method ALIB is the platform
library call. On macOS it returns no value, the caller (ADP0._PSR and the PCI bring-up) reports AE_AML_NO_RETURN_VALUE,
retries without end, and the boot stops at "PCI configuration begin" (1401 #85, #129).

The repair is the usual OpenCore one, built from the machine's own tables so every rebuild keeps it:
  1. ACPI > Patch renames the ALIB declaration to XLIB (the Method opcode, its length and the name, so calls are left
     alone), limited to the SSDT that declares it (its signature and OEM Table ID); the firmware's own method is kept
     under a name nothing calls;
  2. a small SSDT declares ALIB again at the same path and returns Zero.
Nothing else in any table changes. A machine whose SSDTs do not declare ALIB is not touched.
"""
import os
import plistlib

from . import dsdt_pass1

OEM = b"NULMTH"
SHIM_FILE = "SSDT-ALIBFix.aml"
RULE = "acpi-alib-shim"


def _namepath(path):
    """AML NameString for an absolute path of 4-byte segments."""
    if not path:
        return b"\\\x00"
    if len(path) == 1:
        return b"\\" + path[0]
    if len(path) == 2:
        return b"\\\x2e" + path[0] + path[1]
    return b"\\\x2f" + bytes([len(path)]) + b"".join(path)


def _table(body, oem_table_id):
    d = bytearray(b"SSDT" + (36 + len(body)).to_bytes(4, "little") + b"\x02\x00" + OEM + oem_table_id[:8].ljust(8, b" ") +
                  (1).to_bytes(4, "little") + b"INTL" + (0x20230628).to_bytes(4, "little")) + body
    d[9] = (-sum(d)) & 0xFF
    return bytes(d)


def shim_table(path, argc):
    """SSDT that declares Method ALIB (argc arguments) at `path` (the container's path, e.g. (b'_SB_',)) returning Zero."""
    method_body = b"ALIB" + bytes([argc & 7]) + b"\xa4\x00"          # Return (Zero)
    method = b"\x14" + dsdt_pass1._encode_pkglen(len(method_body)) + method_body
    if path:
        scope_body = _namepath(path) + method
        method = b"\x10" + dsdt_pass1._encode_pkglen(len(scope_body)) + scope_body
    return _table(method, b"ALIBFIX")


def find_alib(acpi_dir):
    """[{'file', 'oem_table_id' (8 bytes), 'path' (container path), 'argc'}] for each SSDT that declares Method ALIB;
    a second list holds the files that mention ALIB but could not be read as AML (named in the build log)."""
    found, unread = [], []
    for name in sorted(os.listdir(acpi_dir)):
        if not name.lower().endswith(".aml") or name.upper() == "DSDT.AML":
            continue
        try:
            with open(os.path.join(acpi_dir, name), "rb") as fh:
                data = fh.read(8 * 1024 * 1024)
        except OSError:
            continue
        if data[:4] != b"SSDT" or b"ALIB" not in data:
            continue
        try:
            methods = dsdt_pass1.methods_defined(data)
        except (dsdt_pass1.Unsupported, IndexError, ValueError) as e:
            unread.append(f"{name}: {e}")
            continue
        for path, (argc, at) in methods.items():
            if path and path[-1] == b"ALIB":
                # the definition alone: opcode, PkgLength, name. Calls to ALIB inside the table stay ALIB and reach the shim.
                _, nl = dsdt_pass1._pkglen(data, at + 1)
                head = data[at:at + 1 + nl + 4]
                found.append({"file": name, "oem_table_id": data[16:24], "path": path[:-1], "argc": argc, "head": head})
    return found, unread


def apply(acpi_dir, out_dir):
    """Ships SSDT-ALIBFix.aml and the ALIB -> XLIB patch for each SSDT that declares ALIB. Returns change records."""
    if not os.path.isdir(acpi_dir):
        return []
    found, unread = find_alib(acpi_dir)
    changes = [{"rule": RULE, "before": "", "after": "unchanged", "why": f"ALIB seen but its table could not be read: {u}"}
               for u in unread]
    if not found:
        return changes
    oc = os.path.join(out_dir, "EFI", "OC")
    cfgp = os.path.join(oc, "config.plist")
    with open(cfgp, "rb") as fh:
        cfg = plistlib.load(fh)
    acpi = cfg.setdefault("ACPI", {})
    patches = acpi.setdefault("Patch", [])
    add = acpi.setdefault("Add", [])
    # one shim per container path; the same SSDT shape on a second table (a second OEM Table ID) only adds its patch
    shims = {}
    for f in found:
        shims.setdefault(f["path"], f["argc"])
    if len(shims) > 1:
        # two different paths would declare two ALIBs; keep the first and say so rather than guess which is called
        changes.append({"rule": RULE, "before": f"{len(shims)} different ALIB paths", "after": "first path only",
                        "why": "the SSDTs declare ALIB at different places; only the first is replaced"})
    path, argc = next(iter(shims.items()))
    os.makedirs(os.path.join(oc, "ACPI"), exist_ok=True)
    with open(os.path.join(oc, "ACPI", SHIM_FILE), "wb") as fh:
        fh.write(shim_table(path, argc))
    if not any((e.get("Path") or "").lower() == SHIM_FILE.lower() for e in add):
        add.append({"Comment": "ALIB answers Zero (the firmware's own ALIB returns no value in macOS)",
                    "Enabled": True, "Path": SHIM_FILE})
    for f in found:
        if f["path"] != path:
            continue
        find = f["head"]
        replace = find[:-4] + b"XLIB"
        have = any(p.get("Find") == find and p.get("OemTableId") == f["oem_table_id"] for p in patches)
        if not have:
            patches.append({"Base": "", "BaseSkip": 0, "Comment": f"ALIB to XLIB in {f['oem_table_id'].decode('ascii', 'replace').strip()}",
                            "Count": 0, "Enabled": True, "Find": find, "Limit": 0, "Mask": b"", "OemTableId": f["oem_table_id"],
                            "Replace": replace, "ReplaceMask": b"", "Skip": 0, "TableLength": 0, "TableSignature": b"SSDT"})
    tmp = cfgp + ".tmp"
    with open(tmp, "wb") as fh:
        plistlib.dump(cfg, fh)
    os.replace(tmp, cfgp)
    changes.append({"rule": RULE, "before": "ALIB in " + ", ".join(sorted({f['file'] for f in found})),
                    "after": f"ALIB renamed XLIB there, {SHIM_FILE} answers Zero",
                    "why": "the firmware's ALIB returns no value in macOS; the boot stops at PCI configuration"})
    return changes
