"""Let iasl disassemble a DSDT that defines the same Device or Method twice.

Some AMI firmware (seen on AM5 boards) builds the DSDT with one Device declared in several If/Else branches, for
example \\_SB.PCI0.GPP7.UP00 three times. The firmware's own interpreter only runs one branch, but iasl loads them all
and stops with AE_ALREADY_EXISTS, so the build stopped at "dsdt.aml could not be disassembled" (15 builds on 1.1.0).
iasl 20260930 refuses it the same way, and neither -df nor -f helps.

The same AE_ALREADY_EXISTS also appears on a Method declared twice, for example a GPE handler \\_GPE._L02 that the
firmware defines in more than one branch (BIOSTAR B650MT-E PRO, 1401 #1 / driver #7). A Method opens with 0x14, not
5B 82, so the Device-only scan found nothing and the build stopped the same way; the leaf after the clash is renamed
whether it is a Device (5B 82) or a Method (0x14).

The upstream loader copies the tables into a temp folder and runs iasl there. When a run fails this way, the later
definitions of that name in the temp copy of the DSDT are renamed (Z000, Z001, ...) and the run is repeated. The first
definition keeps its name, the user's own tables are never touched, and the DSDT is never shipped in the EFI: it is
only read to plan the build.
"""
import contextlib
import os
import re

MAX_RENAMES = 16
_FAILED = re.compile(r"Failure creating named object \[([^\]]+)\], AE_ALREADY_EXISTS")
# A DSDT iasl could not read rides in the build log as base64 so the repair can be written from the upload. 192 KB raw
# is far above any firmware DSDT seen (27-55 KB); a larger one is left out and only described.
TABLE_IN_LOG_MAX = 192 * 1024


def _table_for_log(path):
    """{'dsdt_sha256', 'dsdt_size', 'dsdt_oem', 'dsdt_b64'} for the table at path; what could be read of it."""
    import base64  # noqa: PLC0415
    import hashlib  # noqa: PLC0415
    try:
        with open(path, "rb") as fh:
            data = fh.read(TABLE_IN_LOG_MAX + 1)
    except OSError as error:
        return {"dsdt_error": f"{type(error).__name__}: {error}"}
    try:
        size = os.path.getsize(path)
    except OSError:
        size = len(data)
    out = {"dsdt_sha256": hashlib.sha256(data).hexdigest(), "dsdt_size": size}
    if len(data) >= 36:
        out["dsdt_oem"] = data[10:16].decode("ascii", "replace").strip() + " " + data[16:24].decode("ascii", "replace").strip()
    if len(data) <= TABLE_IN_LOG_MAX:
        out["dsdt_b64"] = base64.b64encode(data).decode("ascii")
    else:
        out["dsdt_error"] = f"table larger than {TABLE_IN_LOG_MAX} bytes; not included"
    return out


def _pkglen(data, i):
    lead = data[i]
    extra = lead >> 6
    if extra == 0:
        return lead & 0x3F, 1
    value = lead & 0x0F
    for k in range(extra):
        value |= data[i + 1 + k] << (4 + 8 * k)
    return value, extra + 1


def _defs_after(data, op, oplen, name):
    """Offsets of NameSeg `name` (4 bytes) directly after `op` + PkgLength (op is `oplen` bytes)."""
    out = []
    i = data.find(op)
    while i >= 0:
        j = i + oplen
        if j < len(data):
            _, n = _pkglen(data, j)
            if data[j + n:j + n + 4] == name:
                out.append(j + n)
        i = data.find(op, i + 1)
    return out


def device_names(data, name):
    """Offsets of NameSeg `name` (4 bytes) directly after a Device op (5B 82 PkgLength)."""
    return _defs_after(data, b"\x5b\x82", 2, name)


def method_names(data, name):
    """Offsets of NameSeg `name` (4 bytes) directly after a Method op (14 PkgLength)."""
    return _defs_after(data, b"\x14", 1, name)


def name_defs(data, name):
    """Offsets where `name` is defined as a Device or a Method, in table order. A clash on \\_GPE._L02 is a Method,
    on \\_SB.PCI0.GPP7.UP00 a Device, so both opcodes are scanned and the first definition keeps its name."""
    return sorted(set(device_names(data, name)) | set(method_names(data, name)))


def rename_later(data, name, serial):
    """Renames every Device/Method definition of `name` after the first. Returns how many, 0 when it is defined once."""
    spots = name_defs(data, name)
    for k, off in enumerate(spots[1:]):
        data[off:off + 4] = ("Z%03X" % (serial + k)).encode()
    return max(len(spots) - 1, 0)  # WAS len - 1: a name that is not a Device/Method gave -1, and the loop never ended


@contextlib.contextmanager
def tolerate(dsdt, records):
    runner = getattr(dsdt, "r", None)
    if runner is None or not getattr(dsdt, "iasl", None):
        yield  # no iasl runner on this loader: nothing to wrap
        return
    original = runner.run
    executable = os.path.normcase(os.path.abspath(dsdt.iasl))

    def run(command, *args, **kwargs):
        result = original(command, *args, **kwargs)
        argv = command.get("args", []) if isinstance(command, dict) else []
        if not (argv and isinstance(argv[0], str) and os.path.normcase(os.path.abspath(argv[0])) == executable):
            return result
        tables = [a for a in argv[1:] if isinstance(a, str) and os.path.basename(a).lower() == "dsdt.aml"]
        # iasl can CRASH on some firmware's DSDT instead of returning an ASL error: on Windows the exit code is a
        # structured-exception value (0xC0000005 access violation = 3221225477), not a small iasl error code. Renaming a
        # repeated Device cannot help a crash, so record it with the exact code and keep a copy of the DSDT beside it so
        # the next uploaded log carries the table itself (38 build logs on 10-09 showed only "exit 3221225477"). The
        # build then follows upstream's own path, which proceeds on the raw tables when disassembly is unavailable.
        if tables and isinstance(result, (list, tuple)) and len(result) >= 3 and isinstance(result[2], int) and result[2] >= 0x80000000:
            kept = None
            try:
                import shutil  # noqa: PLC0415
                kept = tables[0] + ".crash"
                shutil.copyfile(tables[0], kept)
            except OSError:
                kept = None
            record = {"tool": "acpi-dupnames", "iasl_crash_exit": result[2],
                      "hex": hex(result[2] & 0xFFFFFFFF), "dsdt_kept": kept}
            # The kept copy lives in the loader's temp folder, which is deleted when the build ends, so three uploaded
            # logs carried its path and not one byte of the table. The table itself rides in the record now (a DSDT is
            # tens of KB; base64 under the log's size cap), and the message says that this log is what to send.
            record.update(_table_for_log(tables[0]))
            # exit -1 (0xffffffff) with AE_ALREADY_EXISTS is not a crash: iasl's pass 1 found a name defined twice and
            # stopped without saying which (During name lookup/catalog, psobject-372) - nothing to rename from the output.
            # AMD and Haswell AMI boards, 10-17. The repair needs the table, which this record now carries.
            said = str(result[0]) + str(result[1])
            if "AE_ALREADY_EXISTS" in said:
                record["reason"] = "AE_ALREADY_EXISTS during name lookup/catalog: a name is defined twice; iasl did not say which"
                print(f"ACPI: iasl stopped on this DSDT (exit {result[2]} = {hex(result[2] & 0xFFFFFFFF)}): a name is "
                      "defined twice and iasl did not say which, so it could not be renamed for reading. The table is "
                      "included in this build log - send the log with Send logs so the repair can be added. "
                      "Continuing without pre-patch disassembly.")
            else:
                print(f"ACPI: iasl crashed on this DSDT (exit {result[2]} = {hex(result[2] & 0xFFFFFFFF)}); the table is "
                      "included in this build log (send it with Send logs) and the build continues without pre-patch disassembly")
            records.append(record)
            return result
        serial = 0
        while tables and isinstance(result, (list, tuple)) and len(result) >= 3 and result[2] != 0 and serial < MAX_RENAMES:
            m = _FAILED.search(str(result[0]) + str(result[1]))
            if not m:
                break
            name = m.group(1).split(".")[-1].encode()
            path = tables[0]
            try:
                with open(path, "rb") as fh:
                    data = bytearray(fh.read())
                n = rename_later(data, name, serial)
                if not n:
                    break  # the clash is with another table, not a repeated Device in the DSDT: leave it
                with open(path, "wb") as fh:
                    fh.write(bytes(data))
            except OSError as error:
                records.append({"tool": "acpi-dupnames", "error": f"{type(error).__name__}: {error}"})
                break
            serial += n
            records.append({"tool": "acpi-dupnames", "renamed": m.group(1), "copies": n})
            print(f"ACPI: the DSDT defines {m.group(1)} {n + 1} times; renamed the later copies for reading only")
            result = original(command, *args, **kwargs)
        return result

    runner.run = run
    try:
        yield
    finally:
        runner.run = original


def selftest():
    results = []

    def arm(name, ok, shown=""):
        results.append(bool(ok))
        print(("  ok   " if ok else "  FAIL ") + name + (f"  [{shown}]" if shown else ""))

    def dev(name, body=b""):
        return b"\x5b\x82" + bytes([len(name) + len(body) + 1]) + name + body

    aml = bytearray(b"HDR" + dev(b"UP00") + b"\xa0\x01" + dev(b"UP00", b"\x00") + dev(b"UP01") + dev(b"UP00"))
    arm("three Device definitions of UP00 are found, UP01 is not one of them", len(device_names(aml, b"UP00")) == 3,
        len(device_names(aml, b"UP00")))
    n = rename_later(aml, b"UP00", 0)
    arm("the later two are renamed and the first keeps its name",
        n == 2 and len(device_names(aml, b"UP00")) == 1 and len(device_names(aml, b"Z000")) == 1 and
        len(device_names(aml, b"Z001")) == 1, aml)
    arm("a name defined once is left alone (the clash is with another table)", rename_later(aml, b"UP01", 5) == 0)
    arm("a name that is no Device at all gives 0, never a negative count (it looped the loader forever)",
        rename_later(aml, b"M237", 5) == 0)
    long_body = b"\x00" * 100
    big = bytearray(b"\x5b\x82" + bytes([0x40 | ((len(long_body) + 6) & 0x0F), (len(long_body) + 6) >> 4]) + b"GPP7" + long_body)
    arm("a two-byte PkgLength is decoded", device_names(big, b"GPP7") == [4])

    def meth(name, body=b""):  # Method op: 14 PkgLength NameSeg MethodFlags body
        inner = name + b"\x00" + body
        return b"\x14" + bytes([len(inner) + 1]) + inner

    maml = bytearray(b"HDR" + meth(b"_L02") + b"\xa0\x01" + meth(b"_L02", b"\x00") + meth(b"_L08"))
    arm("two Method definitions of _L02 are found (\\_GPE._L02 declared twice: 1401 #1 / driver #7)",
        len(method_names(maml, b"_L02")) == 2, len(method_names(maml, b"_L02")))
    arm("a Method clash is renamed just like a Device, the first _L02 keeps its name",
        rename_later(maml, b"_L02", 0) == 1 and len(method_names(maml, b"_L02")) == 1 and
        len(method_names(maml, b"Z000")) == 1, maml)
    arm("a Method defined once (_L08) is left alone", rename_later(maml, b"_L08", 5) == 0)
    mixed = bytearray(b"HDR" + dev(b"UP00") + meth(b"UP00"))
    arm("a name used as both a Device and a Method is ordered and the later one renamed",
        rename_later(mixed, b"UP00", 0) == 1)

    class Runner:
        def __init__(self, path):
            self.path, self.calls = path, 0

        def run(self, command):
            self.calls += 1
            with open(self.path, "rb") as fh:
                data = fh.read()
            if len(device_names(data, b"UP00")) > 1:
                return ("", "Firmware Error (ACPI): Failure creating named object [\\_SB.PCI0.GPP7.UP00], AE_ALREADY_EXISTS", 255)
            return ("ok", "", 0)

    import tempfile  # noqa: PLC0415
    from types import SimpleNamespace  # noqa: PLC0415
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "DSDT.aml")
        with open(path, "wb") as fh:
            fh.write(b"HDR" + dev(b"UP00") + dev(b"UP00") + dev(b"UP00"))
        iasl = os.path.join(tmp, "iasl")
        d = SimpleNamespace(r=Runner(path), iasl=iasl)
        records = []
        with tolerate(d, records):
            r = d.r.run({"args": [iasl, "-dl", "-l", path]})
        arm("a DSDT iasl refused for a repeated Device disassembles after the rename (AM5 AMI firmware)",
            r[2] == 0 and records and records[0]["copies"] == 2, records)
        d2 = SimpleNamespace(r=Runner(path), iasl=iasl)
        with open(path, "wb") as fh:
            fh.write(b"HDR" + dev(b"UP00") + dev(b"UP00"))
        with tolerate(d2, []):
            r2 = d2.r.run({"args": [os.path.join(tmp, "other-tool"), path]})
        arm("a command that is not iasl is passed through untouched", r2[2] != 0 and d2.r.calls == 1)

        class Crasher:
            def __init__(self): self.calls = 0
            def run(self, command): self.calls += 1; return ("", "", 3221225477)  # 0xC0000005 access violation
        d3 = SimpleNamespace(r=Crasher(), iasl=iasl)
        rec3 = []
        with tolerate(d3, rec3):
            r3 = d3.r.run({"args": [iasl, "-dl", "-l", path]})
        arm("an iasl CRASH (0xC0000005) is recorded once, the DSDT is kept, and it is NOT retried as a rename",
            d3.r.calls == 1 and rec3 and rec3[0].get("hex") == "0xc0000005" and rec3[0].get("dsdt_kept", "x").endswith(".crash")
            and os.path.exists(path + ".crash"), rec3)
    print(f"acpi_dupnames: {sum(results)}/{len(results)}")
    return all(results)


if __name__ == "__main__":
    import sys  # noqa: PLC0415
    sys.exit(0 if selftest() else 1)
