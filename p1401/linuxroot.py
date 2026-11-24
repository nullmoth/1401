"""The two steps of the Linux app that need root: reading the firmware's ACPI tables, and writing a USB stick.

The app runs as the user. ACPI tables under /sys/firmware/acpi/tables are readable by root only, so the scan asks
policykit to run this file's `acpi` command once. The USB writer is started the same way (`usb write ...`) so the
whole erase, format and mount sequence happens in one elevated process rather than a mix of sudo calls.

    pkexec python3 p1401/linuxroot.py acpi <dest> --owner UID:GID
    pkexec python3 p1401/linuxroot.py usb write <device> <EFI build> <darwin major> [options]

When the app itself is already root (a root shell, a live session) the same functions are called directly.
"""
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLES = "/sys/firmware/acpi/tables"
SYSTEM_ACPI = ("DSDT", "FACP", "FACS", "APIC", "MCFG", "HPET", "SRAT", "SLIT", "XSDT", "RSDT")


class RootError(RuntimeError):
    pass


def _destination(relative):
    """sysfs names one table `DSDT`; the builder expects `DSDT.aml`. Subdirectories (dynamic/) stay subdirectories."""
    return os.path.join(*[part.upper() for part in relative.split(os.sep)]) + ".aml"


def copy_tables(source=TABLES, dest=None, owner=None):
    """Copies every table under `source` into `dest`, returns the paths written.

    Reads are done as root and each file is made readable by its owner before the scan continues as the user. A
    table that vanishes between listdir and open is skipped: hot-plugged Thunderbolt boxes can add and remove SSDTs
    while the scan runs, and one missing optional table should not lose the DSDT.
    """
    if not dest:
        raise RootError("no destination for the ACPI tables")
    if not os.path.isdir(source):
        raise RootError(f"{source} does not exist: this kernel has no ACPI table directory")
    written = []
    for folder, folders, names in os.walk(source, followlinks=False):
        folders.sort()
        rel_dir = os.path.relpath(folder, source)
        for name in sorted(names):
            src = os.path.join(folder, name)
            if os.path.islink(src) or not os.path.isfile(src):
                continue
            relative = name if rel_dir == "." else os.path.join(rel_dir, name)
            dst = os.path.join(dest, _destination(relative))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                with open(src, "rb") as source_file:
                    data = source_file.read()
            except FileNotFoundError:
                continue
            with open(dst + ".tmp", "wb") as out:
                out.write(data)
            os.replace(dst + ".tmp", dst)
            os.chmod(dst, 0o644)
            if owner:
                os.chown(dst, owner[0], owner[1])
            written.append(dst)
    if not table_has(os.path.join(dest, "DSDT.aml"), b"DSDT"):
        raise RootError(f"the ACPI directory {source} had no DSDT; this PC's firmware tables cannot be read")
    return written


def table_has(path, signature):
    try:
        with open(path, "rb") as fh:
            return fh.read(4) == signature
    except OSError:
        return False


def _owner(value):
    if not value:
        return None
    try:
        uid, gid = value.split(":", 1)
        return int(uid), int(gid)
    except ValueError as error:
        raise RootError(f"bad --owner {value!r}; expected UID:GID") from error


def _write_acpi(dest, owner):
    if os.geteuid() != 0:
        raise RootError("reading /sys/firmware/acpi/tables needs root")
    tables = copy_tables(dest=dest, owner=owner)
    print(f"copied {len(tables)} ACPI table(s) to {dest}", flush=True)
    return 0


def elevate_acpi(dest):
    """Runs the ACPI copy through pkexec, or directly when the process is already root. Returns the child's output.

    pkexec exits 126 when the password dialog is dismissed and 127 when no agent answers; both mean the scan
    cannot see the firmware, so they get one sentence instead of an exit code.
    """
    owner = f"{os.getuid()}:{os.getgid()}"
    if os.geteuid() == 0:
        _write_acpi(dest, None)
        return
    tool = shutil.which("pkexec")
    if not tool:
        raise RootError("pkexec is not installed. Install policykit-1/polkit, or run 1401 from a root terminal.")
    command = [tool, sys.executable, os.path.join(REPO, "p1401", "linuxroot.py"), "acpi", dest, "--owner", owner]
    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        detail = " ".join((result.stderr or result.stdout or "").split())[-500:]
        if result.returncode in (126, 127):
            raise RootError("the ACPI read was not authorised, so the hardware check cannot finish. Approve the "
                            "password prompt and run Check this PC again.")
        raise RootError(f"copying the ACPI tables failed (pkexec exit {result.returncode}): {detail or 'no detail'}")
    if result.stdout:
        print(result.stdout.rstrip(), flush=True)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: linuxroot.py acpi <dest> --owner UID:GID | usb <command> ...", file=sys.stderr)
        return 2
    command, rest = argv[0], argv[1:]
    try:
        if command == "acpi":
            dest, owner = None, None
            i = 0
            while i < len(rest):
                if rest[i] == "--owner" and i + 1 < len(rest):
                    owner = _owner(rest[i + 1])
                    i += 2
                    continue
                if dest is None:
                    dest = rest[i]
                i += 1
            if not dest:
                raise RootError("acpi needs a destination directory")
            return _write_acpi(dest, owner)
        if command == "usb":
            from p1401 import linuxusb  # noqa: PLC0415 - the writer imports the engine only when it is used
            return linuxusb.main(rest)
    except RootError as error:
        print(f"STOP {error}", file=sys.stderr)
        return 1
    print(f"unknown command {command!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    if not __package__:
        # pkexec starts this file by path, so make `p1401` importable before reloading it under its real name.
        sys.path.insert(0, REPO)
        from p1401 import linuxroot  # noqa: PLC0415
        sys.exit(linuxroot.main())
    sys.exit(main())
