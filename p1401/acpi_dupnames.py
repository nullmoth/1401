"""Let iasl disassemble a DSDT that defines the same Device twice.

Some AMI firmware (seen on AM5 boards) builds the DSDT with one Device declared in several If/Else branches, for
example \\_SB.PCI0.GPP7.UP00 three times. The firmware's own interpreter only runs one branch, but iasl loads them all
and stops with AE_ALREADY_EXISTS, so the build stopped at "dsdt.aml could not be disassembled" (15 builds on 1.1.0).
iasl 20260930 refuses it the same way, and neither -df nor -f helps.

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


def _pkglen(data, i):
    lead = data[i]
    extra = lead >> 6
    if extra == 0:
        return lead & 0x3F, 1
    value = lead & 0x0F
    for k in range(extra):
        value |= data[i + 1 + k] << (4 + 8 * k)
    return value, extra + 1


def device_names(data, name):
    """Offsets of NameSeg `name` (4 bytes) directly after a Device op (5B 82 PkgLength)."""
    out = []
    i = data.find(b"\x5b\x82")
    while i >= 0:
        j = i + 2
        if j < len(data):
            _, n = _pkglen(data, j)
            if data[j + n:j + n + 4] == name:
                out.append(j + n)
        i = data.find(b"\x5b\x82", i + 1)
    return out


def rename_later(data, name, serial):
    """Renames every definition of `name` after the first. Returns how many, 0 when it is defined once."""
    spots = device_names(data, name)
    for k, off in enumerate(spots[1:]):
        data[off:off + 4] = ("Z%03X" % (serial + k)).encode()
    return max(len(spots) - 1, 0)  # WAS len - 1: a name that is not a Device gave -1, and the retry loop never ended


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
    print(f"acpi_dupnames: {sum(results)}/{len(results)}")
    return all(results)


if __name__ == "__main__":
    import sys  # noqa: PLC0415
    sys.exit(0 if selftest() else 1)
