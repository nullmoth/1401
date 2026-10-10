"""Make a firmware DSDT loadable by macOS's ACPI interpreter (ACPICA 20160930).

macOS loads AML in two passes. Pass 1 skips every If/Else/While body and every Method body, but a Scope() still needs
its target to exist at that moment; when it does not, ACPICA 20160930 discards the WHOLE DSDT ("AE_NOT_FOUND, [DSDT]
table load failed", 0 objects) and macOS runs with no DSDT at all. Newer ACPICA executes the table as one term list, so
the same firmware loads fine on Windows and Linux. Measured 10-10 with acpiexec built from ACPICA R09_30_16: the DSDTs
of all three Arrow Lake H laptops users sent (HONOR 225H, ASUS GU605CW 285H, Lenovo 255H) fail to load this way, at
\\_SB_.PC00.HDAS, a Device the firmware creates inside a top-level If.

Repair: every top-level Scope() whose target does not exist yet in pass 1 is wrapped in If (One). Pass 1 then skips it
like the firmware's own top-level Ifs, and it runs as module-level code once the namespace is complete; If (One) is
always true, so it still runs against the same target. Nothing else in the table changes, only its length and checksum.
A table with an opcode this parser does not know, or with such a Scope nested inside another object, is left unchanged.
"""
import os

ROOT = ()
HEADER = 36
# opcodes whose body is PkgLength-delimited and NOT parsed in pass 1 (skipped, names inside do not exist yet)
SKIP_PKG = {0xA0, 0xA1, 0xA2, 0x14}           # If, Else, While, Method
DATA_PKG = {0x11, 0x12, 0x13}                  # Buffer, Package, VarPackage
EXT_SKIP_PKG = {0x81, 0x86, 0x87}              # Field, IndexField, BankField (5B xx)
# the root names ACPICA creates before any table loads (AcpiGbl_PreDefinedNames)
PREDEFINED = {(n,) for n in (b"_GPE", b"_PR_", b"_SB_", b"_SI_", b"_TZ_", b"_GL_", b"_OS_", b"_OSI", b"_REV")}
# opcode -> (operands, targets); a target is a name, a Local/Arg, or NullName (0x00)
EXPR = {0x70: (1, 1), 0x86: (2, 0), 0x8A: (2, 1), 0x8B: (2, 1), 0x8C: (2, 1), 0x8D: (2, 1), 0x8F: (2, 1), 0x72: (2, 1), 0x74: (2, 1), 0x77: (2, 1), 0x78: (2, 2), 0x79: (2, 1), 0x7A: (2, 1), 0x7B: (2, 1), 0x7C: (2, 1),
        0x7D: (2, 1), 0x7E: (2, 1), 0x7F: (2, 1), 0x80: (1, 1), 0x85: (2, 1), 0x83: (1, 0), 0x87: (1, 0), 0x88: (2, 1),
        0x99: (1, 1), 0x96: (1, 1), 0x97: (1, 1), 0x98: (1, 1)}
EXT_SCOPED = {0x82: "Device", 0x83: "Processor", 0x84: "PowerResource", 0x85: "ThermalZone"}


class Unsupported(Exception):
    pass


def _pkglen(d, i):
    lead = d[i]
    extra = lead >> 6
    if extra == 0:
        return lead & 0x3F, 1
    v = lead & 0x0F
    for k in range(extra):
        v |= d[i + 1 + k] << (4 + 8 * k)
    return v, extra + 1


def _encode_pkglen(body_without_len):
    """PkgLength for a body of `body_without_len` bytes following it (the length counts its own bytes)."""
    for n in (1, 2, 3, 4):
        total = body_without_len + n
        if (n == 1 and total < 0x40) or (n > 1 and total < (1 << (4 + 8 * (n - 1)))):
            if n == 1:
                return bytes([total])
            out = [((n - 1) << 6) | (total & 0x0F)]
            for k in range(n - 1):
                out.append((total >> (4 + 8 * k)) & 0xFF)
            return bytes(out)
    raise Unsupported("Scope too large to wrap")


def _namestring(d, i):
    """Returns (prefix, segs, next_i): prefix '\\' or count of '^'."""
    root, up = False, 0
    if d[i] == 0x5C:
        root, i = True, i + 1
    while d[i] == 0x5E:
        up, i = up + 1, i + 1
    b = d[i]
    if b == 0x00:
        return (root, up, ()), i + 1
    if b == 0x2E:
        return (root, up, (bytes(d[i + 1:i + 5]), bytes(d[i + 5:i + 9]))), i + 9
    if b == 0x2F:
        n = d[i + 1]
        return (root, up, tuple(bytes(d[i + 2 + 4 * k:i + 6 + 4 * k]) for k in range(n))), i + 2 + 4 * n
    if b == 0x5F or 0x41 <= b <= 0x5A:
        return (root, up, (bytes(d[i:i + 4]),)), i + 4
    raise Unsupported(f"name byte {b:#x} at {i:#x}")


def _resolve(scope, ns):
    root, up, segs = ns
    base = ROOT if root else scope[:len(scope) - up] if up else scope
    return base + segs


def _exists(ns_set, scope, ns):
    root, up, segs = ns
    if not root and not up and len(segs) == 1:  # a single NameSeg searches up through the parent scopes
        s = scope
        while True:
            if s + segs in ns_set:
                return True
            if not s:
                return False
            s = s[:-1]
    return _resolve(scope, ns) in ns_set


CONTAINERS = {}  # offset of each parsed Scope/Device/... -> (opcode bytes, PkgLength bytes, end)
METHODS = {}  # path -> argument count, filled by the walk (a call is a NameString followed by that many TermArgs)


def _lookup_method(scope, ns):
    root, up, segs = ns
    if not root and not up and len(segs) == 1:
        s = scope
        while True:
            if s + segs in METHODS:
                return METHODS[s + segs]
            if not s:
                return None
            s = s[:-1]
    return METHODS.get(_resolve(scope, ns))


def _name_or_call(d, i, scope):
    ns, j = _namestring(d, i)
    for _ in range(_lookup_method(scope, ns) or 0):
        j = _termarg(d, j, scope)
    return j


def _termarg(d, i, scope=ROOT):
    """Skips one data object / simple TermArg (constants, strings, buffers, packages, a name or method call)."""
    b = d[i]
    if b in (0x00, 0x01, 0xFF):
        return i + 1
    if b == 0x0A:
        return i + 2
    if b == 0x0B:
        return i + 3
    if b == 0x0C:
        return i + 5
    if b == 0x0E:
        return i + 9
    if b == 0x0D:
        return d.index(0, i + 1) + 1
    if b in DATA_PKG:
        n, _ = _pkglen(d, i + 1)
        return i + 1 + n
    if b == 0x5B and d[i + 1] == 0x30:  # Revision
        return i + 2
    if b in (0x5C, 0x5E, 0x2E, 0x2F, 0x5F) or 0x41 <= b <= 0x5A:
        return _name_or_call(d, i, scope)
    if 0x60 <= b <= 0x6E:  # Local0-7, Arg0-6
        return i + 1
    if b in EXPR:  # integer expressions (region offsets like Add (BASE, 0x1000)): operands, then targets
        operands, targets = EXPR[b]
        i += 1
        for _ in range(operands + targets):
            i = _termarg(d, i, scope)
        return i
    raise Unsupported(f"term {b:#x} at {i:#x}")


def _walk(d, start, end, scope, ns_set, failing, top):
    """Pass-1 walk of a term list. Adds created names to ns_set; appends (offset, length) of top-level Scopes whose target
    is missing to `failing` (nested ones raise Unsupported)."""
    i = start
    while i < end:
        op = d[i]
        if op == 0x10:  # Scope
            n, nl = _pkglen(d, i + 1)
            ns, body = _namestring(d, i + 1 + nl)
            if not _exists(ns_set, scope, ns):
                failing.append((i, 1 + n))
            else:
                CONTAINERS[i] = (1, nl, i + 1 + n)
                _walk(d, body, i + 1 + n, _resolve(scope, ns), ns_set, failing, False)
            i += 1 + n
        elif op in SKIP_PKG:
            if op == 0x14:  # Method: its name exists, its body is not parsed
                n, nl = _pkglen(d, i + 1)
                ns, j = _namestring(d, i + 1 + nl)
                ns_set.add(_resolve(scope, ns))
                METHODS[_resolve(scope, ns)] = d[j] & 0x07
            n, _ = _pkglen(d, i + 1)
            i += 1 + n
        elif op == 0x08:  # Name
            ns, j = _namestring(d, i + 1)
            ns_set.add(_resolve(scope, ns))
            i = _termarg(d, j, scope)
        elif op == 0x15:  # External: no object in pass 1
            _, j = _namestring(d, i + 1)
            i = j + 2
        elif op == 0x06:  # Alias
            _, j = _namestring(d, i + 1)
            ns, j = _namestring(d, j)
            ns_set.add(_resolve(scope, ns))
            i = j
        elif op == 0x5B:
            ext = d[i + 1]
            if ext in EXT_SCOPED:
                n, nl = _pkglen(d, i + 2)
                ns, body = _namestring(d, i + 2 + nl)
                path = _resolve(scope, ns)
                ns_set.add(path)
                if ext == 0x83:
                    body += 6   # ProcID, PblkAddr, PblkLen
                elif ext == 0x84:
                    body += 3   # SystemLevel, ResourceOrder
                CONTAINERS[i] = (2, nl, i + 2 + n)
                _walk(d, body, i + 2 + n, path, ns_set, failing, False)
                i += 2 + n
            elif ext in EXT_SKIP_PKG:
                n, _ = _pkglen(d, i + 2)
                i += 2 + n
            elif ext == 0x80:  # OperationRegion: name, space, offset, length
                ns, j = _namestring(d, i + 2)
                ns_set.add(_resolve(scope, ns))
                i = _termarg(d, _termarg(d, j + 1, scope), scope)
            elif ext == 0x88:  # DataTableRegion: name + 3 TermArgs
                ns, j = _namestring(d, i + 2)
                ns_set.add(_resolve(scope, ns))
                i = _termarg(d, _termarg(d, _termarg(d, j, scope), scope), scope)
            elif ext == 0x01:  # Mutex: name + sync level
                ns, j = _namestring(d, i + 2)
                ns_set.add(_resolve(scope, ns))
                i = j + 1
            elif ext == 0x13:  # CreateField (source, bit index, bit count, name): executable, creates nothing in pass 1
                i = _termarg(d, _termarg(d, _termarg(d, _termarg(d, i + 2, scope), scope), scope), scope)
            elif ext == 0x02:  # Event
                ns, j = _namestring(d, i + 2)
                ns_set.add(_resolve(scope, ns))
                i = j
            else:
                raise Unsupported(f"ext op 5B {ext:#x} at {i:#x}")
        elif op in EXPR or op in (0x5C, 0x5E, 0x2E, 0x2F, 0x5F) or 0x41 <= op <= 0x5A:
            # executable code in an object body (Store, Notify, a method call): parsed past, creates nothing
            i = _termarg(d, i, scope)
        else:
            raise Unsupported(f"op {op:#x} at {i:#x}")


def failing_scopes(dsdt):
    """[(offset, length)] of the Scopes ACPICA 20160930 cannot resolve in pass 1 (top-level or nested)."""
    d = bytes(dsdt)
    if d[:4] != b"DSDT" or int.from_bytes(d[4:8], "little") != len(d):
        raise Unsupported("not a DSDT")
    failing = []
    METHODS.clear()
    CONTAINERS.clear()
    _walk(d, HEADER, len(d), ROOT, set(PREDEFINED) | {ROOT}, failing, True)
    return failing


def repair(dsdt):
    """Returns (new_table, count) with every failing Scope wrapped in If (One); (original, 0) when none. A Scope nested in
    a Device (or another Scope) makes its parents longer, so every enclosing PkgLength is encoded again."""
    src = bytes(dsdt)
    spots = failing_scopes(src)
    if not spots:
        return src, 0
    fail = dict(spots)
    holders = [o for o, (_, _, end) in CONTAINERS.items() if any(o < f < end for f in fail)]

    def emit(start, end):
        out, i = bytearray(), start
        items = sorted([o for o in fail if start <= o < end] + [o for o in holders if start <= o < end])
        for o in items:
            if o < i:
                continue  # inside an item already emitted
            out += src[i:o]
            if o in fail:
                body = b"\x01" + src[o:o + fail[o]]  # predicate One, then the original Scope
                out += b"\xa0" + _encode_pkglen(len(body)) + body
                i = o + fail[o]
            else:
                oplen, nl, cend = CONTAINERS[o]
                body = emit(o + oplen + nl, cend)
                out += src[o:o + oplen] + _encode_pkglen(len(body)) + body
                i = cend
        return out + src[i:end]

    d = bytearray(src[:HEADER]) + emit(HEADER, len(src))
    d[4:8] = len(d).to_bytes(4, "little")
    d[9] = 0
    d[9] = (-sum(d)) & 0xFF
    return bytes(d), len(spots)


def apply(acpi_dir, out_dir):
    """Ships a repaired DSDT.aml in the EFI when the firmware's would be discarded by macOS. Returns change records."""
    import plistlib  # noqa: PLC0415
    src = next((os.path.join(acpi_dir, f) for f in sorted(os.listdir(acpi_dir)) if f.upper() == "DSDT.AML"), None)
    if not src:
        return []
    try:
        fixed, n = repair(open(src, "rb").read())
    except Unsupported as e:
        return [{"rule": "dsdt-pass1", "before": "", "after": "unchanged", "why": f"DSDT not checked: {e}"}]
    if not n:
        return []
    oc = os.path.join(out_dir, "EFI", "OC")
    with open(os.path.join(oc, "ACPI", "DSDT.aml"), "wb") as f:
        f.write(fixed)
    cfgp = os.path.join(oc, "config.plist")
    with open(cfgp, "rb") as f:
        cfg = plistlib.load(f)
    add = cfg.setdefault("ACPI", {}).setdefault("Add", [])
    if not any((e.get("Path") or "").upper() == "DSDT.AML" for e in add):
        add.insert(0, {"Comment": "firmware DSDT with forward Scopes deferred (loads in macOS's ACPICA)",
                       "Enabled": True, "Path": "DSDT.aml"})
    tmp = cfgp + ".tmp"
    with open(tmp, "wb") as f:
        plistlib.dump(cfg, f)
    os.replace(tmp, cfgp)
    return [{"rule": "dsdt-pass1", "before": f"{n} Scope(s) macOS cannot resolve - the whole DSDT is discarded",
             "after": "DSDT.aml with those Scopes in If (One)",
             "why": "macOS's ACPICA (20160930) needs a Scope target to exist in pass 1; deferred Scopes run once it does"}]
