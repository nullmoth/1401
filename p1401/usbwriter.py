"""Writes the 1401 installer USB on Windows: GPT, one FAT32 partition, EFI/ and com.apple.recovery.boot/.

This is the only part of 1401 that erases anything, so all the safety checks live here and not in the UI:
  - USB only. Never the boot disk, the system disk, an offline or read-only disk, or anything under 2 GiB.
  - Over 256 GiB needs allow_large (a USB drive that big is usually somebody's backup drive).
  - The PowerShell checks the disk again (number, serial, size, model) right before Clear-Disk, in the same
    run. If the stick gets pulled and another one plugged in, the new one can get the same disk number.

Layout follows Dortania's Windows guide (diskpart clean / convert gpt / create partition primary / format fs=fat32).
The partition is capped at 16 GiB since Windows won't format FAT32 over 32 GiB. EFI + recovery need about 1 GiB.

NOT TESTED ON WINDOWS YET. So far the script and its checks have only been tested on macOS against fake disks.
"""
import json
import os
import platform
import shutil
import subprocess
import time
import sys

GiB = 1 << 30
MIN_DISK = 2 * GiB
MAX_DISK = 256 * GiB
PART_CAP = 16 * GiB
BASIC_DATA = "{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}"
LABEL = "1401"
# GPT types only an installed OS has: Apple APFS, Apple HFS+, Windows recovery.
# WAS also EFI system and Microsoft reserved: every Rufus, Ventoy or 1401 stick has an EFI partition, and Windows adds a
# Microsoft reserved one when it initializes a GPT disk, so 116 users' plain USB sticks were refused (1.0.24 and 1.1.0)
# and a second try on the stick 1401 had just written could never pass.
OS_TYPES = "'{7c3457ef-0000-11aa-aa11-00306543ecac}','{48465300-0000-11aa-aa11-00306543ecac}','{de94bba4-06d1-4d40-a16a-bfd50179d6ac}'"
TIMEOUT = 300  # seconds, so a hung format fails instead of waiting forever
FIELDS = "Number,FriendlyName,SerialNumber,BusType,Size,IsBoot,IsSystem,IsOffline,IsReadOnly,PartitionStyle"


class UsbError(RuntimeError):
    pass


def _ps(script):
    if platform.system() != "Windows":
        raise UsbError("the USB writer runs on Windows only")
    p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                       capture_output=True, text=True, timeout=TIMEOUT)
    if p.returncode != 0:
        raise UsbError((p.stderr or p.stdout).strip()[-1500:])
    return p.stdout


def list_disks():
    out = _ps(f"Get-Disk | Select-Object {FIELDS} | ConvertTo-Json -Compress")
    d = json.loads(out or "[]")
    return d if isinstance(d, list) else [d]


def eligible(disk, allow_large=False):
    """Returns (ok, reasons): every reason this disk can't be erased, worded for the user."""
    why = []
    if disk.get("BusType") != "USB":
        why.append(f"not a USB disk (bus: {disk.get('BusType')})")
    if disk.get("IsBoot"):
        why.append("this is the disk the computer booted from")
    if disk.get("IsSystem"):
        why.append("this disk holds the system partition")
    if disk.get("IsOffline"):
        why.append("the disk is offline")
    if disk.get("IsReadOnly"):
        why.append("the disk is read-only (a lock switch, or a failing stick)")
    size = int(disk.get("Size") or 0)
    if size < MIN_DISK:
        why.append(f"too small ({size / GiB:.1f} GiB; the installer needs 2)")
    if size > MAX_DISK and not allow_large:
        why.append(f"{size / GiB:.0f} GiB is larger than any USB stick 1401 expects - confirm it is not a backup drive")
    return not why, why


def _q(s):
    return "'" + str(s or "").replace("'", "''") + "'"


def format_script(disk):
    """Builds the PowerShell that re-checks the disk, erases it, and prints the new drive letter. Doesn't run it."""
    ok, why = eligible(disk, allow_large=True)
    if not ok:
        raise UsbError("refusing: " + "; ".join(why))
    n, size = int(disk["Number"]), int(disk["Size"])
    psize = min(size - 64 * (1 << 20), PART_CAP)
    return f"""$ErrorActionPreference = 'Stop'
$d = Get-Disk -Number {n}
if (($d.SerialNumber + '').Trim() -ne {_q((disk.get('SerialNumber') or '').strip())} -or $d.Size -ne {size} -or
    $d.FriendlyName -ne {_q(disk.get('FriendlyName'))} -or $d.BusType -ne 'USB' -or $d.IsBoot -or $d.IsSystem) {{
  throw '1401: disk {n} is not the USB stick you picked any more. Nothing was erased.'
}}
if ($d.PartitionStyle -ne 'RAW') {{ Clear-Disk -Number {n} -RemoveData -RemoveOEM -Confirm:$false }}
Initialize-Disk -Number {n} -PartitionStyle GPT
$p = New-Partition -DiskNumber {n} -Size {psize} -AssignDriveLetter -GptType '{BASIC_DATA}'
Format-Volume -Partition $p -FileSystem FAT32 -NewFileSystemLabel '{LABEL}' -Confirm:$false | Out-Null
(Get-Partition -DiskNumber {n} -PartitionNumber $p.PartitionNumber).DriveLetter
"""


def check_script(disk):
    """PowerShell that only READS: throws unless disk N is still the exact stick the user picked."""
    ok, why = eligible(disk, allow_large=True)
    if not ok:
        raise UsbError("refusing: " + "; ".join(why))
    n, size = int(disk["Number"]), int(disk["Size"])
    return f"""$ErrorActionPreference = 'Stop'
$d = Get-Disk -Number {n}
if (($d.SerialNumber + '').Trim() -ne {_q((disk.get('SerialNumber') or '').strip())} -or $d.Size -ne {size} -or
    $d.FriendlyName -ne {_q(disk.get('FriendlyName'))} -or $d.BusType -ne 'USB' -or $d.IsBoot -or $d.IsSystem) {{
  throw '1401: disk {n} is not the USB stick you picked any more. Nothing was erased.'
}}
$os = @(Get-Partition -DiskNumber {n} -ErrorAction SilentlyContinue | Where-Object {{ $_.GptType -in {OS_TYPES} }})
if ($os.Count) {{ throw '1401: disk {n} holds a macOS or Windows system partition (APFS, HFS+ or Windows recovery). Nothing was erased. If nothing on it is needed: Disk Management, right-click each of its volumes, Delete Volume, then try again.' }}
"""


def diskpart_script(disk, letter):
    """The standard Windows erase: diskpart clean, MBR, one FAT32 partition. Windows' FAT32 formatter stops at 32 GB, so 16 GB."""
    n, size = int(disk["Number"]), int(disk["Size"])
    mb = min(size - 64 * (1 << 20), PART_CAP) // (1 << 20)
    # "convert gpt" refused this SanDisk after clean ("select an empty MBR disk") ; MBR is the 1401 Probe's proven
    # sequence and UEFI/OpenCore boot a FAT32 MBR stick the same. "rescan" lets Windows see the cleaned disk before convert.
    # "clean" -> "Access is denied" once the stick had a mounted letter (Z:) from an earlier run. Dismount every
    # volume on it first (remove all dismount), clear a read-only flag, then clean.
    # "select volume Z" failed ("volume you selected is not valid") in the app's session: release() frees letters instead.
    return "\r\n".join([f"select disk {n}", "attributes disk clear readonly noerr",
                         "clean", "rescan", f"select disk {n}", "convert mbr",
                         f"create partition primary size={mb}", f"format fs=fat32 quick label={LABEL}", "active",
                         f"assign letter={letter}", "exit"]) + "\r\n"


def letters_on(n):
    """Drive letters of every volume on disk n (empty off Windows, so the script stays testable)."""
    if platform.system() != "Windows":
        return []
    out = _ps(f"(Get-Partition -DiskNumber {int(n)} -ErrorAction SilentlyContinue | Where-Object DriveLetter).DriveLetter")
    return [c.strip() for c in out.split() if len(c.strip()) == 1 and c.strip().isalpha()]


def release(n):
    """Frees the stick before diskpart clean: drops its drive letters and cycles it offline/online so no process holds a
    handle (diskpart's "Access is denied" on clean, ). Every step may fail harmlessly; clean reports the real error."""
    _ps(f"""$ErrorActionPreference = 'SilentlyContinue'
foreach ($p in @(Get-Partition -DiskNumber {n} | Where-Object DriveLetter)) {{
  Remove-PartitionAccessPath -DiskNumber {n} -PartitionNumber $p.PartitionNumber -AccessPath ($p.DriveLetter + ':\\') }}
Set-Disk -Number {n} -IsReadOnly $false
# an offline/online cycle here made the next clean fail "The device is not ready" (): only wait until it reads Online
for ($i = 0; $i -lt 30 -and (Get-Disk -Number {n}).OperationalStatus -ne 'Online'; $i++) {{ Start-Sleep -Seconds 1 }}
exit 0
""")


def _free_letter():
    import string  # noqa: PLC0415
    used = {d[0].upper() for d in (os.listdrives() if hasattr(os, "listdrives") else [])}
    for c in reversed(string.ascii_uppercase[6:]):
        if c not in used and not os.path.exists(c + ":\\"):
            return c
    raise UsbError("no free drive letter between G: and Z:")


def _diskpart(script):
    """diskpart /s from a fresh private temp file: /s mode stops at the first failed command with a non-zero exit."""
    import tempfile  # noqa: PLC0415
    fd, sp = tempfile.mkstemp(prefix="1401-", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="ascii", newline="") as fh:
            fh.write(script)
        p = subprocess.run(["diskpart", "/s", sp], capture_output=True, text=True, timeout=TIMEOUT)
        for _ in range(3):  # a just-released stick can refuse clean ("not ready"/"access denied") for a few seconds
            if p.returncode == 0:
                break
            time.sleep(5)
            p = subprocess.run(["diskpart", "/s", sp], capture_output=True, text=True, timeout=TIMEOUT)
        if p.returncode != 0:
            raise UsbError(f"Windows could not erase the stick (diskpart exit {p.returncode}): " + (p.stdout or p.stderr).strip()[-1200:])
    finally:
        os.remove(sp)


def write(disk, efi_build_dir, recovery_info, allow_large=False, progress=None, machine_profile=None):
    """Erases the stick, then writes Apple's recovery image (checked chunk by chunk) and the EFI. Returns the drive root."""
    from . import apple  # noqa: PLC0415
    ok, why = eligible(disk, allow_large)
    if not ok:
        raise UsbError("refusing: " + "; ".join(why))
    from . import validate
    checked = validate.validate(efi_build_dir)
    if not checked.get('ok'):
        reasons = checked.get('invariants') or [checked.get('error') or 'The OpenCore configuration did not pass validation.']
        raise UsbError('The EFI must be rebuilt before erasing the stick: ' + '; '.join(reasons))
    if machine_profile is not None:
        from . import machine_handoff
        if machine_handoff.verified(efi_build_dir) != machine_profile:
            raise UsbError('The machine profile changed before erasing the stick. Rebuild the EFI.')
    _ps(check_script(disk))
    from . import rawdisk  # noqa: PLC0415
    n = int(disk["Number"])
    rawdisk.wipe_mbr_fat32(n, int(disk["Size"]), PART_CAP, say=lambda m: print(m, flush=True))
    letter = _free_letter()
    _ps(f"""$ErrorActionPreference = 'Stop'
Update-HostStorageCache
for ($i = 0; $i -lt 20 -and -not (Get-Partition -DiskNumber {n} -PartitionNumber 1 -ErrorAction SilentlyContinue); $i++) {{ Start-Sleep 1 }}
$p = Get-Partition -DiskNumber {n} -PartitionNumber 1
if ($p.DriveLetter) {{ Remove-PartitionAccessPath -DiskNumber {n} -PartitionNumber 1 -AccessPath ($p.DriveLetter + ':\\') }}
Set-Partition -DiskNumber {n} -PartitionNumber 1 -NewDriveLetter {letter}
Format-Volume -DriveLetter {letter} -FileSystem FAT32 -NewFileSystemLabel '{LABEL}' -Force -Confirm:$false | Out-Null
""")
    root = letter + ":\\"
    for _ in range(60):
        if os.path.isdir(root):
            break
        time.sleep(0.5)
    if not os.path.isdir(root):
        raise UsbError(f"diskpart finished but {root} did not appear")
    got = apple.download(recovery_info, root, progress)
    shutil.copytree(os.path.join(efi_build_dir, "EFI"), os.path.join(root, "EFI"))
    verify_efi_copy(os.path.join(efi_build_dir, 'EFI'), os.path.join(root, 'EFI'))
    driver = None
    if needs_nullmoth(efi_build_dir):
        # The EFI was built for a GeForce RTX (nullmoth.apply): the stick carries the driver for the Mac companion.
        from . import nullmoth  # noqa: PLC0415
        cache = os.path.join(efi_build_dir, ".cache")
        os.makedirs(cache, exist_ok=True)
        driver = nullmoth.stage(root, cache, fetch=_fetch)
    if machine_profile is not None:
        machine_handoff.copy_to_installer(machine_profile, root)
    return {"root": root, "nullmoth": driver, **got}


def verify_efi_copy(source, destination):
    """Read the written EFI files back before reporting a ready installer."""
    import hashlib

    def digest(path):
        hasher = hashlib.sha256()
        with open(path, 'rb') as stream:
            for block in iter(lambda: stream.read(1 << 20), b''):
                hasher.update(block)
        return hasher.digest()

    for folder, _, files in os.walk(source):
        for name in files:
            original = os.path.join(folder, name)
            relative = os.path.relpath(original, source)
            target = os.path.join(destination, relative)
            if not os.path.isfile(target) or digest(original) != digest(target):
                raise UsbError('The written EFI did not match the build: ' + relative + '. The stick is not ready.')


def needs_nullmoth(efi_build_dir):
    """True when the built config carries the NullMoth driver's boot-args (only nullmoth.apply writes nvaccel=1)."""
    import plistlib  # noqa: PLC0415
    with open(os.path.join(efi_build_dir, "EFI", "OC", "config.plist"), "rb") as fh:
        cfg = plistlib.load(fh)
    nv = cfg.get("NVRAM", {}).get("Add", {}).get("7C436110-AB2A-4BBB-A880-FE41995C9F82", {})
    return "nvaccel=1" in (nv.get("boot-args") or "").split()


def _fetch(url, path):
    import urllib.request  # noqa: PLC0415
    with urllib.request.urlopen(url, timeout=60) as r, open(path, "wb") as fh:
        shutil.copyfileobj(r, fh, 1 << 20)


def selftest():
    res = []

    def arm(name, cond, shown):
        res.append(bool(cond))
        print(("ok   " if cond else "FAIL ") + name + f"  [{shown}]")

    usb16 = {"Number": 3, "FriendlyName": "SanDisk Ultra", "SerialNumber": "4C53 0001'X", "BusType": "USB",
             "Size": 16 * 10**9, "IsBoot": False, "IsSystem": False, "IsOffline": False, "IsReadOnly": False,
             "PartitionStyle": "MBR"}
    ok, why = eligible(usb16)
    arm("16 GB USB stick is accepted", ok, why or "ok")
    for name, patch, word in [
        ("boot NVMe is refused", {"BusType": "NVMe", "IsBoot": True, "IsSystem": True, "Size": 512 * GiB}, "booted"),
        ("USB disk holding the system partition is refused (Windows To Go)", {"IsSystem": True}, "system"),
        ("internal SATA disk is refused", {"BusType": "SATA"}, "not a USB"),
        ("read-only stick is refused", {"IsReadOnly": True}, "read-only"),
        ("1 GB stick is refused", {"Size": 10**9}, "too small"),
        ("2 TB USB drive is refused without allow_large", {"Size": 2 * 10**12}, "backup"),
    ]:
        ok, why = eligible({**usb16, **patch})
        arm(name, not ok and any(word in w for w in why), why)
    ok, _ = eligible({**usb16, "Size": 2 * 10**12}, allow_large=True)
    arm("same 2 TB drive is allowed once the user confirms", ok, "ok" if ok else "refused")

    arm("an EFI or Microsoft reserved partition alone does not count as an OS (Rufus, Ventoy and 1401 sticks have them)",
        "c12a7328" not in OS_TYPES and "e3c9e316" not in OS_TYPES, OS_TYPES[:40])
    arm("APFS, HFS+ and Windows recovery still count as an OS", all(g in OS_TYPES for g in ("7c3457ef", "48465300", "de94bba4")),
        OS_TYPES.count("{"))
    s = format_script(usb16)
    clear, check = s.find("Clear-Disk"), s.find("throw '1401")
    arm("disk is re-checked before Clear-Disk, in the same run", 0 < check < clear, f"check@{check} clear@{clear}")
    arm("quote in the serial is escaped (no PowerShell injection)", "'4C53 0001''X'" in s,
        s.splitlines()[2][:70])
    arm("destructive cmdlets only target the picked disk number",
        all("-Number 3" in l or "-DiskNumber 3" in l for l in s.splitlines() if l.split(" ")[0] in
            ("Clear-Disk", "Initialize-Disk", "$p")), "3")
    arm("16 GB stick gets the whole disk minus 64 MiB", f"-Size {16 * 10**9 - 64 * (1 << 20)} " in s, 16 * 10**9 - 64 * (1 << 20))
    s64 = format_script({**usb16, "Size": 64 * 10**9})
    arm("64 GB stick is capped at 16 GiB (Windows won't format FAT32 over 32)", f"-Size {PART_CAP} " in s64, PART_CAP)
    try:
        format_script({**usb16, "BusType": "NVMe", "IsBoot": True})
        fired = False
    except UsbError:
        fired = True
    arm("format_script itself refuses the boot disk, not just the UI", fired, "refused" if fired else "SCRIPT MADE")
    try:
        list_disks()
        ran = platform.system() == "Windows"
    except UsbError as e:
        ran = "Windows only" in str(e)
    arm("refuses to run when not on Windows", ran, platform.system())
    scope = "read-only Windows disk discovery; no disk writes" if platform.system() == "Windows" else "logic checks; Windows disk discovery not exercised"
    print(f"\n{sum(res)}/{len(res)} passed ({scope})")
    return all(res)


def cli_write(argv):
    """write <disk number> <EFI build dir> <darwin major> [--driver <tar.gz>] [--extra <file>]... [--profile <Report.json>] [--allow-large]
    The Windows app's write step. Every line printed is "STEP|OK|PROGRESS|STOP ..." so the window can show it."""
    from . import apple, nullmoth  # noqa: PLC0415
    num, efi, darwin = int(argv[0]), argv[1], int(argv[2])
    def opt(n): return [argv[i + 1] for i, a in enumerate(argv) if a == n and i + 1 < len(argv)]
    disk = next((d for d in list_disks() if int(d.get("Number", -1)) == num), None)
    if not disk:
        print(f"STOP disk {num} is not attached any more"); return 1
    ok, why = eligible(disk, "--allow-large" in argv)
    if not ok:
        print("STOP " + "; ".join(why)); return 1
    from . import machine_handoff
    profiles = opt('--profile')
    if len(profiles) > 1:
        raise UsbError('Select one current scan before writing the installer.')
    handoff = machine_handoff.verified(efi, profiles[0] if profiles else None)
    drv = opt("--driver")
    if drv and needs_nullmoth(efi):
        cache = os.path.join(efi, ".cache"); os.makedirs(cache, exist_ok=True)
        shutil.copyfile(drv[0], os.path.join(cache, os.path.basename(drv[0])))
    print("STEP asking Apple for the macOS recovery image", flush=True)
    info = apple.image_info(darwin)
    print(f"OK {info['name']} ({info['product']})", flush=True)
    last = [-1]
    def progress(done, total, *_):
        pct = int(done * 100 / total) if total else 0
        if pct != last[0]:
            last[0] = pct; print(f"PROGRESS {pct} downloading macOS recovery from Apple", flush=True)
    print(f"STEP erasing and writing disk {num} ({disk.get('FriendlyName')})", flush=True)
    res = write(disk, efi, info, allow_large="--allow-large" in argv, progress=progress, machine_profile=handoff)
    root = res["root"]
    print('OK verified build profile written to the stick (live identity remains unverified)', flush=True)
    for f in opt("--extra"):
        d = os.path.join(root, "NullMoth"); os.makedirs(d, exist_ok=True)
        shutil.copyfile(f, os.path.join(d, os.path.basename(f)))
        print(f"OK copied {os.path.basename(f)} to the stick", flush=True)
    print(f"OK the stick is ready at {root}" + (" (NVIDIA driver included)" if res.get("nullmoth") else ""), flush=True)
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    if len(sys.argv) > 1 and sys.argv[1] == "write":
        try:
            sys.exit(cli_write(sys.argv[2:]))
        except Exception as e:  # the window shows the reason; nothing is retried behind the user's back
            print(f"STOP {type(e).__name__}: {e}", flush=True); sys.exit(1)
    print(json.dumps(list_disks(), indent=2))
