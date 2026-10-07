"""Runs the 1401 loader under real UEFI firmware (OVMF in QEMU, x86_64 TCG) and checks the serial log.

    python3 tests/loader_qemu.py

Each scenario is a set of FAT disks the firmware sees. The loader has to find the OS stand-ins on them and
chain-load the right one by its real device path. The stand-in is next.efi (loader/src/bin/next.rs), which prints
whether it can see its own file path, since Windows Boot Manager needs that to find its BCD.

Two negative controls: no OS on any disk means no chain-load, and an empty ESP means no loader banner at all
(without them the checks could pass on whatever the firmware happens to print).

Everything runs in a temp dir: disks, the NVRAM vars copy, the logs. Nothing touches a real disk or this Mac's NVRAM.
"""
import concurrent.futures
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOADER = os.path.join(REPO, "loader")
QEMU = shutil.which("qemu-system-x86_64")
FW = "/opt/homebrew/share/qemu"
CODE, VARS = os.path.join(FW, "edk2-x86_64-code.fd"), os.path.join(FW, "edk2-i386-vars.fd")
REL = os.path.join(LOADER, "target", "x86_64-unknown-uefi", "release")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")  # OVMF's console escape codes, stripped from the log before matching

LOADER_AT = "EFI/BOOT/BOOTX64.EFI"
PROBE = "EFI/1401/next.efi"
WINDOWS = "EFI/Microsoft/Boot/bootmgfw.efi"
MACOS = "System/Library/CoreServices/boot.efi"

# name -> (disks: [[(dest path, "loader"|"next")]], timeout secs, [must appear], [must not appear], must power off?)
SCENARIOS = {
    "probe": ([[(LOADER_AT, "loader"), (PROBE, "next")]], 150,
              ["1401 loader", "1401 probe at", "1401 probe: chainload ok, own file path present",
               "1401 probe returned to the loader", "powering off"], ["MISSING", "failed to start"], True),
    "windows-on-2nd-disk": ([[(LOADER_AT, "loader")], [(WINDOWS, "next")]], 150,
                            ["Windows at", "loading Windows from", "chainload ok, own file path present"],
                            ["MISSING", "failed to start", "no bootable OS"], True),
    "macos-outranks-windows": ([[(LOADER_AT, "loader")], [(WINDOWS, "next")], [(MACOS, "next")]], 150,
                               ["Windows at", "macOS at", "loading macOS from", "chainload ok"],
                               ["loading Windows", "failed to start"], True),
    "CONTROL-no-os": ([[(LOADER_AT, "loader")]], 150,
                      ["1401 loader", "no bootable OS found", "powering off"], ["chainload ok"], True),
    "CONTROL-empty-esp": ([[]], 60, [], ["1401 loader"], False),
    # APFS: a disk given as "@name" is a raw image fixture (built in fixtures(), attached with snapshot=on).
    "apfs-no-jumpstart": ([[(LOADER_AT, "loader"), (PROBE, "next")], "@apfs-plain"], 150,
                          ["APFS container with no EFI jumpstart", "0 APFS driver(s) started", "chainload ok"],
                          ["refused", "apfs.efi"], True),
    "CONTROL-apfs-flipped-bit": ([[(LOADER_AT, "loader"), (PROBE, "next")], "@apfs-flipped"], 150,
                                 ["APFS container refused: container superblock checksum mismatch", "chainload ok"],
                                 ["no EFI jumpstart"], True),
    "apfs-jumpstart": ([[(LOADER_AT, "loader"), (PROBE, "next")], "@apfs-blessed"], 150,
                       ["APFS jumpstart:", "apfs.efi started", "1 APFS driver(s) started",
                        "macOS at \\System\\Library\\CoreServices\\boot.efi", "chainload ok"],
                       ["refused", "failed to start"], True),
    "CONTROL-apfs-jumpstart-flipped-bit": ([[(LOADER_AT, "loader"), (PROBE, "next")], "@apfs-js-flipped"], 150,
                                           ["APFS container refused: jumpstart checksum mismatch", "0 APFS driver(s) started"],
                                           ["apfs.efi started", "macOS at"], True),
}
# Built on an Intel Mac with tests/make_apfs_fixture.py (bless needs root there). It contains Apple's code, so it
# lives in the cache, never in the repo. If it's missing, those scenarios are skipped, not passed.
BLESSED = os.path.join(os.path.expanduser("~"), ".cache", "1401", "fixtures", "apfs-blessed.cdr")


def build():
    env = dict(os.environ)
    rustup = subprocess.run(["brew", "--prefix", "rustup"], capture_output=True, text=True).stdout.strip()
    env["PATH"] = os.path.join(rustup, "bin") + os.pathsep + env["PATH"]
    p = subprocess.run(["cargo", "+stable", "build", "--release"], cwd=LOADER, env=env, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit("loader build failed:\n" + p.stderr[-3000:])
    return {"loader": os.path.join(REL, "loader1401.efi"), "next": os.path.join(REL, "next.efi")}


def _gpt_first_partition(img):
    import struct  # noqa: PLC0415
    with open(img, "rb") as fh:
        d = fh.read(1 << 20)
    assert d[512:520] == b"EFI PART", "fixture has no GPT"
    ent = struct.unpack_from("<Q", d, 512 + 72)[0] * 512
    return struct.unpack_from("<Q", d, ent + 32)[0] * 512


def fixtures(root):
    """APFS containers made by Apple's tools. hdiutil is macOS-only, so elsewhere those scenarios are skipped."""
    fx = {}
    if os.path.isfile(BLESSED):
        fx["@apfs-blessed"] = BLESSED
        import struct  # noqa: PLC0415
        jf = os.path.join(root, "js-flipped.cdr")
        shutil.copyfile(BLESSED, jf)
        with open(jf, "r+b") as fh:  # flip one bit in the real jumpstart object's reserved area
            p0 = _gpt_first_partition(jf)
            fh.seek(p0 + 36)
            bs = struct.unpack("<I", fh.read(4))[0]
            fh.seek(p0 + 1272)
            js = struct.unpack("<Q", fh.read(8))[0]
            fh.seek(p0 + js * bs + 100)
            b = fh.read(1)
            fh.seek(-1, 1)
            fh.write(bytes([b[0] ^ 1]))
        fx["@apfs-js-flipped"] = jf
    if shutil.which("hdiutil"):
        dmg, raw = os.path.join(root, "plain.dmg"), os.path.join(root, "plain")
        subprocess.run(["hdiutil", "create", "-quiet", "-size", "64m", "-layout", "GPTSPUD", "-fs", "APFS",
                        "-volname", "P1401", dmg], check=True)
        subprocess.run(["hdiutil", "convert", "-quiet", dmg, "-format", "UDTO", "-o", raw], check=True)
        fx["@apfs-plain"] = raw + ".cdr"
        flipped = os.path.join(root, "flipped.cdr")
        shutil.copyfile(raw + ".cdr", flipped)
        with open(flipped, "r+b") as fh:  # one bit inside nx_counters, far from every field the loader reads
            fh.seek(_gpt_first_partition(flipped) + 1000)
            b = fh.read(1)
            fh.seek(-1, 1)
            fh.write(bytes([b[0] ^ 1]))
        fx["@apfs-flipped"] = flipped
    return fx


def run(name, spec, efis, root, fx):
    disks, timeout, want, never, off = spec
    missing = [x for x in disks if isinstance(x, str) and x not in fx]
    if missing:
        return name, None, [f"fixture {missing} not available"]
    d = os.path.join(root, name)
    os.makedirs(d)
    args = [QEMU, "-machine", "q35", "-m", "512", "-display", "none", "-no-reboot", "-nodefaults",
            "-drive", f"if=pflash,format=raw,unit=0,readonly=on,file={CODE}"]
    vars_copy = os.path.join(d, "vars.fd")
    shutil.copyfile(VARS, vars_copy)
    args += ["-drive", f"if=pflash,format=raw,unit=1,file={vars_copy}"]
    for i, files in enumerate(disks):
        if isinstance(files, str):  # raw image: snapshot=on keeps every write off the fixture
            args += ["-drive", f"format=raw,file={fx[files]},snapshot=on"]
            continue
        disk = os.path.join(d, f"disk{i}")
        os.makedirs(disk)
        for dest, src in files:
            os.makedirs(os.path.dirname(os.path.join(disk, dest)), exist_ok=True)
            shutil.copyfile(efis[src], os.path.join(disk, dest))
        # read-only vvfat ("fat:") is refused by q35's AHCI disk ("Block node is read-only"); rw writes land only
        # in this temp dir, and the loader writes nothing.
        args += ["-drive", f"format=raw,file=fat:rw:{disk}"]
    log = os.path.join(d, "serial.log")
    args += ["-serial", f"file:{log}"]
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        exited, rc = True, p.returncode
    except subprocess.TimeoutExpired:
        exited, rc = False, None
    text = ANSI.sub("", open(log, errors="replace").read()) if os.path.exists(log) else ""
    fails = [f"missing {w!r}" for w in want if w not in text] + [f"present {n!r}" for n in never if n in text]
    if off and not (exited and rc == 0):
        fails.append(f"did not power off cleanly (exited={exited}, rc={rc})")
    # Make sure the firmware actually ran. QEMU dying at startup (rc=1, empty log) once made the empty-ESP
    # control "pass". An empty log, or the no-power-off control exiting early, counts as a failure.
    if not text.strip():
        fails.append(f"serial log empty - firmware never ran (exited={exited}, rc={rc}): {p.stderr[-300:] if exited else ''}")
    if not off and exited:
        fails.append(f"expected the firmware to still be up at the timeout; QEMU exited rc={rc}")
    lines = [ln.strip() for ln in text.splitlines() if "1401" in ln]
    return name, fails, lines


def main():
    for f in (QEMU, CODE, VARS):
        if not f or not os.path.exists(f):
            print(f"can't run: {f or 'qemu-system-x86_64'} not found")
            return 2
    efis = build()
    root = tempfile.mkdtemp(prefix="1401-loader-")
    with concurrent.futures.ThreadPoolExecutor(len(SCENARIOS)) as ex:
        fx = fixtures(root)
        results = list(ex.map(lambda kv: run(kv[0], kv[1], efis, root, fx), SCENARIOS.items()))
    ok = unknown = 0
    for name, fails, lines in results:
        if fails is None:
            unknown += 1
            print(f"skip {name}  {lines[0]}")
            continue
        print(("ok   " if not fails else "FAIL ") + name + ("" if not fails else f"  {fails}"))
        for ln in lines[:8]:
            print("       | " + ln)
        ok += not fails
    print(f"\n{ok}/{len(results)} passed, {unknown} skipped   (logs: {root})")
    return 1 if ok + unknown < len(results) else (2 if unknown else 0)


if __name__ == "__main__":
    sys.exit(main())
