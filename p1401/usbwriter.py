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
# 1401\\Recovery beside 1401.exe: a recovery image the user brings (see cli_write)
RECOVERY_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "Recovery"))
FIELDS = "Number,FriendlyName,SerialNumber,BusType,Size,IsBoot,IsSystem,IsOffline,IsReadOnly,PartitionStyle"


class UsbError(RuntimeError):
    pass


def _system_tool(*parts):
    """A Windows tool by its full path under System32. 1.7 log 10-10: "FileNotFoundError: [WinError 2]" starting plain
    "powershell" on a PC whose PATH no longer listed it; the tool was there, the lookup was not."""
    root = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"
    path = os.path.join(root, "System32", *parts)
    return path if os.path.isfile(path) else parts[-1]


def _ps(script):
    if platform.system() != "Windows":
        raise UsbError("the USB writer runs on Windows only")
    p = subprocess.run([_system_tool("WindowsPowerShell", "v1.0", "powershell.exe"), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
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


def same_stick_ps(disk):
    """PowerShell that sets $same when disk $d is still the stick the user picked. The serial decides, except for USB
    controllers that report a new serial on every read (10-10: one SMI stick, 7 writes, 7 different serials, every write
    refused "not the USB stick you picked"). Then the stick still counts as the same one only when it is the ONLY USB disk
    with that exact size and model, it sits at the picked disk number, and no disk carries the picked serial."""
    n, size = int(disk["Number"]), int(disk["Size"])
    return f"""$sn = {_q((disk.get('SerialNumber') or '').strip())}
$same = (($d.SerialNumber + '').Trim() -eq $sn)
if (-not $same) {{
  $twins = @(Get-Disk -ErrorAction SilentlyContinue | Where-Object {{ $_.BusType -eq 'USB' -and $_.Size -eq {size} -and $_.FriendlyName -eq {_q(disk.get('FriendlyName'))} }})
  $named = @(Get-Disk -ErrorAction SilentlyContinue | Where-Object {{ $sn -and (($_.SerialNumber + '').Trim() -eq $sn) }})
  $same = ($twins.Count -eq 1 -and $twins[0].Number -eq {n} -and $named.Count -eq 0)
}}
"""


def format_script(disk):
    """Builds the PowerShell that re-checks the disk, erases it, and prints the new drive letter. Doesn't run it."""
    ok, why = eligible(disk, allow_large=True)
    if not ok:
        raise UsbError("refusing: " + "; ".join(why))
    n, size = int(disk["Number"]), int(disk["Size"])
    psize = min(size - 64 * (1 << 20), PART_CAP)
    return f"""$ErrorActionPreference = 'Stop'
$d = Get-Disk -Number {n}
{same_stick_ps(disk)}if (-not $same -or $d.Size -ne {size} -or
    $d.FriendlyName -ne {_q(disk.get('FriendlyName'))} -or $d.BusType -ne 'USB' -or $d.IsBoot -or $d.IsSystem) {{
  throw '1401: disk {n} is not the USB stick you picked any more. Nothing was erased.'
}}
if ($d.PartitionStyle -ne 'RAW') {{ Clear-Disk -Number {n} -RemoveData -RemoveOEM -Confirm:$false }}
Initialize-Disk -Number {n} -PartitionStyle GPT
$p = New-Partition -DiskNumber {n} -Size {psize} -AssignDriveLetter -GptType '{BASIC_DATA}'
Format-Volume -Partition $p -FileSystem FAT32 -NewFileSystemLabel '{LABEL}' -Confirm:$false | Out-Null
(Get-Partition -DiskNumber {n} -PartitionNumber $p.PartitionNumber).DriveLetter
"""


def check_script(disk, erase_os=False):
    """PowerShell that only READS: throws unless disk N is still the exact stick the user picked. Unless erase_os (the
    user confirmed a second time), it also throws when the stick holds a Mac or Windows system/installer partition and
    names each one, so the app can ask. WAS a hard stop: a stick made by createinstallmedia (HFS+) or an earlier macOS
    install could never be reused (1.2.0 logs), and the message told people to delete volumes by hand."""
    ok, why = eligible(disk, allow_large=True)
    if not ok:
        raise UsbError("refusing: " + "; ".join(why))
    n, size = int(disk["Number"]), int(disk["Size"])
    return f"""$ErrorActionPreference = 'Stop'
$d = Get-Disk -Number {n} -ErrorAction SilentlyContinue
if (-not $d) {{ throw '1401: disk {n} is not attached any more (Windows renumbered the stick). Nothing was erased. Press Refresh, pick the stick again and write.' }}
{same_stick_ps(disk)}if (-not $same -or $d.Size -ne {size} -or
    $d.FriendlyName -ne {_q(disk.get('FriendlyName'))} -or $d.BusType -ne 'USB' -or $d.IsBoot -or $d.IsSystem) {{
  throw '1401: disk {n} is not the USB stick you picked any more. Nothing was erased.'
}}
""" + ("" if erase_os else f"""$os = @(Get-Partition -DiskNumber {n} -ErrorAction SilentlyContinue | Where-Object {{ $_.GptType -in {OS_TYPES} }})
if ($os.Count) {{
  $kinds = @{{'{{7c3457ef-0000-11aa-aa11-00306543ecac}}'='Mac APFS'; '{{48465300-0000-11aa-aa11-00306543ecac}}'='Mac HFS+'; '{{de94bba4-06d1-4d40-a16a-bfd50179d6ac}}'='Windows recovery'}}
  $list = ($os | ForEach-Object {{ $kinds[$_.GptType] + ' ' + [math]::Round($_.Size / 1GB, 1) + ' GB' }}) -join ', '
  throw ('1401-OS-PARTITIONS: disk {n} holds ' + $list + '. Nothing was erased.')
}}
""")


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


def _copy_settled(src, dst, root, tries=6, sleep=time.sleep):
    """copytree that survives the stick's volume blinking out for a moment: "device not ready" (WinError 21) and
    access denied mid-copy on 1.2.0 sticks, while Windows or an antivirus re-read the fresh FAT32 volume."""
    for attempt in range(tries):
        try:
            shutil.copytree(src, dst, dirs_exist_ok=True)
            return
        except (shutil.Error, OSError) as error:
            if attempt == tries - 1:
                raise
            print(f"(the stick was busy: {type(error).__name__}; trying the copy again)", flush=True)
            for _ in range(20):
                if os.path.isdir(root):
                    break
                sleep(1)
            sleep(2)


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
        p = subprocess.run([_system_tool("diskpart.exe"), "/s", sp], capture_output=True, text=True, timeout=TIMEOUT)
        for _ in range(3):  # a just-released stick can refuse clean ("not ready"/"access denied") for a few seconds
            if p.returncode == 0:
                break
            time.sleep(5)
            p = subprocess.run([_system_tool("diskpart.exe"), "/s", sp], capture_output=True, text=True, timeout=TIMEOUT)
        if p.returncode != 0:
            raise UsbError(f"Windows could not erase the stick (diskpart exit {p.returncode}): " + (p.stdout or p.stderr).strip()[-1200:])
    finally:
        os.remove(sp)


def write(disk, efi_build_dir, recovery_info, allow_large=False, progress=None, machine_profile=None, erase_os=False):
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
    _ps(check_script(disk, erase_os))
    from . import rawdisk  # noqa: PLC0415
    n = int(disk["Number"])
    rawdisk.wipe_mbr_fat32(n, int(disk["Size"]), PART_CAP, say=lambda m: print(m, flush=True))
    letter = _free_letter()
    out = _ps(f"""$ErrorActionPreference = 'Stop'
# After the raw erase Windows re-detects the stick: its disk number can change and the partition objects it had are
# gone ("The requested object could not be found" from Get-/Set-Partition and Remove-PartitionAccessPath, 1.2.0).
# Find it again by serial and size, wait for partition 1, and keep the letter Windows gives it.
$sn = {_q((disk.get('SerialNumber') or '').strip())}; $sz = {int(disk['Size'])}; $fn = {_q(disk.get('FriendlyName'))}
function Find-Stick {{
  $all = @(Get-Disk -ErrorAction SilentlyContinue | Where-Object {{ $_.BusType -eq 'USB' -and $_.Size -eq $sz }})
  $hit = @($all | Where-Object {{ $sn -and (($_.SerialNumber + '').Trim() -eq $sn) }})
  if (-not $hit.Count) {{ $hit = @($all | Where-Object {{ $_.FriendlyName -eq $fn }}) }}
  if ($hit.Count -eq 1) {{ return $hit[0] }}
  return Get-Disk -Number {n} -ErrorAction SilentlyContinue
}}
$p = $null
for ($i = 0; $i -lt 40 -and -not $p; $i++) {{
  Update-HostStorageCache
  $d = Find-Stick
  if ($d) {{ $p = Get-Partition -DiskNumber $d.Number -PartitionNumber 1 -ErrorAction SilentlyContinue }}
  if (-not $p) {{ Start-Sleep 1 }}
}}
if (-not $p) {{ throw '1401: the stick was erased but Windows did not show its new partition. Unplug the stick, plug it into another USB port (on the back of the PC) and write again.' }}
# DriveLetter is the char NUL (not an empty string) when Windows has not assigned one, and NUL is not whitespace, so
# the old -not $letter.Trim() test passed it on: Format-Volume "Invalid property" + format.com "Required parameter
# missing" on 1.6/1.7 (5 sticks 10-10). A letter counts only when it is A-Z.
function Letter-Of($q) {{ $c = [string]$q.DriveLetter; if ($c -match '^[A-Za-z]$') {{ return $c }} return '' }}
$letter = Letter-Of $p
for ($i = 0; $i -lt 5 -and -not $letter; $i++) {{
  try {{ Set-Partition -DiskNumber $p.DiskNumber -PartitionNumber 1 -NewDriveLetter {letter} -ErrorAction Stop; $letter = '{letter}' }}
  catch {{ Start-Sleep 2; Update-HostStorageCache; $d = Find-Stick; if ($d) {{ $p = Get-Partition -DiskNumber $d.Number -PartitionNumber 1 -ErrorAction SilentlyContinue; $letter = Letter-Of $p }} }}
}}
if (-not $letter) {{ throw '1401: Windows would not give the stick a drive letter. Unplug it, plug it in again and write again.' }}
# Format-Volume failed with "Invalid Parameter", "Access Denied" or "Failed" on 12 sticks through 1.1: the new volume
# was not published yet, or an indexer/antivirus held it for a moment. Three tries, then format.com, which Windows
# has shipped for decades and which does not go through the storage management service.
$done = $false
for ($i = 0; $i -lt 3 -and -not $done; $i++) {{
  try {{ Format-Volume -DriveLetter $letter -FileSystem FAT32 -NewFileSystemLabel '{LABEL}' -Force -Confirm:$false -ErrorAction Stop | Out-Null; $done = $true }}
  catch {{ $last = $_; Start-Sleep 2; Update-HostStorageCache }}
}}
if (-not $done) {{
  $out = cmd /c "format ${{letter}}: /FS:FAT32 /Q /Y /V:{LABEL} 2>&1"
  if ($LASTEXITCODE -ne 0) {{ throw "Format-Volume: $last; format.com: $($out | Select-Object -Last 2)" }}
}}
Write-Output "LETTER=$letter"
""")
    got_letter = next((ln.split("=", 1)[1].strip() for ln in (out or "").splitlines() if ln.startswith("LETTER=")), "")
    letter = got_letter[:1].upper() if got_letter[:1].isalpha() else letter
    root = letter + ":\\"
    for _ in range(60):
        if os.path.isdir(root):
            break
        time.sleep(0.5)
    if not os.path.isdir(root):
        raise UsbError(f"diskpart finished but {root} did not appear")
    got = (apple.copy_local if recovery_info.get("local") else apple.download)(recovery_info, root, progress)
    _copy_settled(os.path.join(efi_build_dir, "EFI"), os.path.join(root, "EFI"), root)
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
    # A recovery image already downloaded elsewhere (1401\\Recovery, or --recovery-dir) is used first: Apple refuses some
    # networks on every session (HTTP 403 in 1.2.0 logs) and some PCs have no internet at all.
    rec = (opt("--recovery-dir") or [RECOVERY_DIR])[0]
    info = apple.local_image(rec)
    if info:
        print(f"OK using {info['name']} (checked against Apple's signed chunklist while copying)", flush=True)
    else:
        print("STEP asking Apple for the macOS recovery image", flush=True)
        try:
            info = apple.image_info(darwin)
        except apple.AppleError as e:
            if "403" in str(e):
                print(f"STOP Apple's recovery server refused this network (HTTP 403). Connect through a VPN or another "
                      f"network and press Next again, or put BaseSystem.dmg and BaseSystem.chunklist (macrecovery on any "
                      f"computer) into {rec} and press Next again.", flush=True)
                return 1
            raise
        print(f"OK {info['name']} ({info['product']})", flush=True)
    last = [-1]
    def progress(done, total, *_):
        pct = int(done * 100 / total) if total else 0
        if pct != last[0]:
            last[0] = pct; print(f"PROGRESS {pct} downloading macOS recovery from Apple", flush=True)
    print(f"STEP erasing and writing disk {num} ({disk.get('FriendlyName')})", flush=True)
    res = write(disk, efi, info, allow_large="--allow-large" in argv, progress=progress, machine_profile=handoff,
                erase_os="--erase-os-partitions" in argv)
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
            import traceback  # noqa: PLC0415
            # where it stopped, module and line only (no user paths): 41 write reports through 1.1 said just
            # "Errno 22" or "WinError 2" and nothing could be traced from them
            where = [f"{os.path.basename(f.filename)}:{f.lineno} {f.name}" for f in traceback.extract_tb(e.__traceback__)][-4:]
            print(f"STOP {type(e).__name__}: {e}", flush=True)
            print("WHERE " + " < ".join(reversed(where)), flush=True); sys.exit(1)
    print(json.dumps(list_disks(), indent=2))
