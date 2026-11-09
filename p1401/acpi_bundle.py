"""The ACPI tables a failed build or scan sends with its logs, so the next report can be replayed end to end.

Only the tables that describe how the firmware wires the machine are kept: the DSDT, the SSDTs and the system description
tables the builder reads. Tables that can carry something personal or licensed are never included: MSDM and SLIC (the
Windows product key and licence), BGRT (the boot logo image), and any table not on the list. The zip is size-capped; a
dump that would exceed the cap sends the DSDT and as many SSDTs as fit, smallest first, and says what it left out.

    python3 -m p1401.acpi_bundle <ACPI folder> <out.zip>
"""
import hashlib
import json
import os
import sys
import zipfile

# signature -> may it be sent. SSDT variants (SSDT, SSDT1, dynamic_SSDT3, ...) are matched by prefix below.
ALLOWED = {"DSDT", "APIC", "FACP", "FACS", "DMAR", "HPET", "MCFG", "LPIT", "FPDT", "FIDT", "WSMT", "NHLT", "TPM2", "DBG2", "DBGP",
           "CRAT", "CDIT", "SLIT", "SRAT", "IVRS", "ASF!", "BOOT", "ECDT", "SBST", "UEFI", "MSCT", "PCCT", "PPTT", "RSDT", "XSDT"}
NEVER = {"MSDM", "SLIC", "BGRT", "OEM1", "OEM2", "OEM3", "OEM4"}
MAX_TABLE = 4 * 1024 * 1024
MAX_TOTAL = 6 * 1024 * 1024


def signature(path):
    with open(path, "rb") as f:
        return f.read(4).decode("latin1")


def kept(sig):
    return sig not in NEVER and (sig in ALLOWED or sig == "SSDT")


def build(acpi_dir, out_zip):
    """-> {'sent': [...], 'left_out': [{'file', 'why'}], 'bytes': n}. Never raises for one bad table."""
    tables, left = [], []
    for name in sorted(os.listdir(acpi_dir))[:512]:
        p = os.path.join(acpi_dir, name)
        if os.path.islink(p) or not os.path.isfile(p) or not name.lower().endswith((".aml", ".dat")):
            continue
        try:
            size = os.path.getsize(p)
            sig = signature(p)
        except OSError:
            continue
        if not kept(sig):
            left.append({"file": name, "why": "not sent: " + ("personal or licensed" if sig in NEVER else "not on the list")})
        elif size > MAX_TABLE:
            left.append({"file": name, "why": "larger than one table may be"})
        else:
            tables.append((sig != "DSDT", size, name, p))     # DSDT first, then smallest first
    tables.sort()
    total, sent = 0, []
    tmp = out_zip + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for _, size, name, p in tables:
            if total + size > MAX_TOTAL:
                left.append({"file": name, "why": "size cap"})
                continue
            with open(p, "rb") as f:
                data = f.read()
            z.writestr("ACPI/" + name, data)
            sent.append({"file": name, "bytes": size, "sha256": hashlib.sha256(data).hexdigest()})
            total += size
        z.writestr("manifest.json", json.dumps({"schema": "nullmoth-acpi-bundle/1", "sent": sent, "left_out": left}, indent=1))
    os.replace(tmp, out_zip)
    return {"sent": [s["file"] for s in sent], "left_out": left, "bytes": total}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print(json.dumps(build(sys.argv[1], sys.argv[2]), indent=1))
