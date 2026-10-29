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
import re
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
FIELDS = "Number,FriendlyName,SerialNumber,UniqueId,BusType,Size,IsBoot,IsSystem,IsOffline,IsReadOnly,PartitionStyle"


# Windows errors a raw sector write ends with on sticks that diskpart still erases: 5 access denied, 1117 I/O device error
RAW_REFUSED = (5, 1117)


class UsbError(RuntimeError):
    pass


def _system_tool(*parts):
    """A Windows tool by its full path under System32. 1.7 log 10-10: "FileNotFoundError: [WinError 2]" starting plain
    "powershell" on a PC whose PATH no longer listed it; the tool was there, the lookup was not."""
    root = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"
    # A 32-bit 1401 on 64-bit Windows is redirected from System32 to the 32-bit tools, where the storage WMI provider
    # (Get-Disk, MSFT_Disk) can be missing while the 64-bit one the window reads works: the writer then saw "0 disks"
    # right after the window had listed the stick. Sysnative is the 64-bit System32 for such a process.
    if os.environ.get("PROCESSOR_ARCHITEW6432"):
        native = os.path.join(root, "Sysnative", *parts)
        if os.path.isfile(native):
            return native
    path = os.path.join(root, "System32", *parts)
    return path if os.path.isfile(path) else parts[-1]


def powershell():
    """Windows PowerShell where Windows keeps it, else any on PATH, else PowerShell 7 (pwsh), which has the same Get-Disk
    and Format-Volume. 2.5.5 write logs (10-26, five runs on one PC): stripped-down Windows builds remove
    powershell.exe from System32 and the write stopped before it listed a single disk."""
    found = _system_tool("WindowsPowerShell", "v1.0", "powershell.exe")
    if os.path.isfile(found):
        return found
    for name in ("powershell.exe", "pwsh.exe"):
        on_path = shutil.which(name)
        if on_path:
            return on_path
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432"), r"C:\Program Files"):
        pwsh = os.path.join(base or "", "PowerShell", "7", "pwsh.exe")
        if base and os.path.isfile(pwsh):
            return pwsh
    return found


# diskpart prints in the OEM code page; "oem" is that codec on Windows (absent elsewhere, where diskpart never runs)
_OEM = "oem" if os.name == "nt" else "utf-8"


def _ps(script):
    if platform.system() != "Windows":
        raise UsbError("the USB writer runs on Windows only")
    # PowerShell writes in the console's code page (GBK, cp866, ...), not UTF-8: on a Chinese Windows reading its output
    # as UTF-8 raised UnicodeDecodeError and the write stopped with an empty "UsbError:" (1.14.1 write logs). It is told
    # to write UTF-8, and anything that still is not is replaced instead of stopping the write.
    cmd = [powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
           "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; " + script]
    try:
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT)
        except PermissionError:
            # 2.0.4 write logs (10-16, nine runs on one PC, same stick): PowerShell had just erased the stick, and Windows
            # then refused to START it again ("[WinError 5] Access is denied" in CreateProcess) - security software
            # blocking a script host it had let run a moment before. One retry after a pause, then a STOP that says so
            # instead of a raw PermissionError.
            time.sleep(3)
            try:
                p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT)
            except PermissionError:
                raise UsbError("Windows refused to start PowerShell (access denied) while preparing the stick. Security "
                               "software is blocking it: allow 1401 (and PowerShell) in your antivirus or Windows Security "
                               "> Controlled folder access, then try again") from None
        except FileNotFoundError:
            # 2.5.3 write logs (one PC, two runs): the write stopped at once on a bare "[WinError 2] The user cannot find
            # the file specified" - Windows PowerShell was not where Windows keeps it, and the writer reads every disk
            # through it.
            raise UsbError(f"Windows PowerShell is missing ({cmd[0]} was not found), and 1401 reads and prepares the "
                           "stick through it. Run 'sfc /scannow' in a Command Prompt opened as administrator to restore "
                           "it, restart, then write again") from None
    except subprocess.TimeoutExpired:
        # 1.15 write log (10-13, a 500 GB hard disk in a USB case): Format-Volume ran past the limit and the raw
        # TimeoutExpired, PowerShell command line and all, was the STOP. It is a UsbError the format step can recover from.
        raise UsbError(f"Windows did not finish preparing the stick within {TIMEOUT} s") from None
    if p.returncode != 0:
        # 1.15 write log (10-14, a "General UDisk"): PowerShell exited non-zero and printed nothing, and the STOP read
        # just "UsbError:". The exit code is the only trace left, so it is named.
        raise UsbError((p.stderr or p.stdout).strip()[-1500:]
                       or f"Windows PowerShell stopped with exit code {p.returncode} (0x{p.returncode & 0xFFFFFFFF:08X}) "
                          "and printed no reason while preparing the stick")
    if p.stderr.strip():
        # a non-terminating PowerShell error ("Get-Disk : Invalid class") exits 0 with no output; without this line the
        # log said only "Windows lists 0 disk(s)" and the cause was lost
        print("WARN PowerShell: " + " ".join(p.stderr.split())[-400:])
    return p.stdout


def _repair_storage_wmi():
    """Re-registers Windows' storage WMI provider (what Get-Disk and MSFT_Disk read): users whose 1401 listed no disks
    at all fixed it by running exactly this as administrator (mofcomp storagewmi.mof in System32\\wbem). The writer runs
    elevated, so it does it once itself. Returns whether mofcomp ran and succeeded."""
    root = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"
    sysdir = "Sysnative" if os.environ.get("PROCESSOR_ARCHITEW6432") else "System32"
    wbem = os.path.join(root, sysdir, "wbem")
    mof, tool = os.path.join(wbem, "storagewmi.mof"), os.path.join(wbem, "mofcomp.exe")
    if not (os.path.isfile(mof) and os.path.isfile(tool)):
        print("WARN storage WMI repair not possible: storagewmi.mof or mofcomp.exe is missing")
        return False
    try:
        p = subprocess.run([tool, mof], cwd=wbem, capture_output=True, text=True, encoding=_OEM, errors="replace", timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"WARN storage WMI repair did not run: {e}")
        return False
    print(f"OK storage WMI repair (mofcomp storagewmi.mof) exit {p.returncode}")
    return p.returncode == 0


# MSFT_Disk's numeric codes, as Get-Disk names them (BusType and PartitionStyle are compared as text below)
BUS_NAMES = {1: "SCSI", 3: "ATA", 7: "USB", 8: "RAID", 10: "SAS", 11: "SATA", 12: "SD", 13: "MMC", 17: "NVMe"}
STYLE_NAMES = {0: "RAW", 1: "MBR", 2: "GPT"}


def _as_list(out):
    d = json.loads(out or "[]")
    return d if isinstance(d, list) else [d]


# Win32_DiskDrive reports a CHS-rounded size, up to one cylinder (255 x 63 x 512 = 8,225,280 bytes) short of the disk.
WMI_SIZE_SLACK = 16 * (1 << 20)


# The disk holding the EFI system partition this Windows started from, for the WMI route (no storage cmdlets).
# Win32_DiskPartition.BootPartition marks every disk's active/EFI partition, a bootable stick's too, so it cannot say
# which one the PC booted from; the volume Windows reports as its system volume can. It is found by its drive letter
# when it has one, else mounted for a moment with `mountvol <letter> /s` (removed again at once); then classic WMI maps
# the letter to a disk. $espKnown stays $false when neither works (legacy BIOS start, no free letter), and the callers
# then refuse every disk with a boot partition, as before 2.6.4.
_BOOT_ESP_PS = r"""$espDisk = -1; $espKnown = $false
try {
  $sv = @(Get-WmiObject -Class Win32_Volume -Filter "SystemVolume=True" -ErrorAction SilentlyContinue | Where-Object { $_.DriveLetter })
  $tmp = $null
  if ($sv.Count -eq 1) { $l = $sv[0].DriveLetter } else {
    $used = @(Get-WmiObject -Class Win32_LogicalDisk | ForEach-Object { $_.DeviceID.Substring(0, 1).ToUpper() })
    $free = @('R','S','T','U','V','W','X','Y','Z') | Where-Object { $used -notcontains $_ } | Select-Object -First 1
    $l = $null
    if ($free) { & mountvol.exe "$($free):" /s 2>&1 | Out-Null; if ($LASTEXITCODE -eq 0) { $l = "$($free):"; $tmp = $l } }
  }
  if ($l) {
    for ($i = 0; $i -lt 10 -and -not $espKnown; $i++) {
      $d = @(Get-WmiObject -Query "ASSOCIATORS OF {Win32_LogicalDisk.DeviceID='$l'} WHERE AssocClass=Win32_LogicalDiskToPartition" -ErrorAction SilentlyContinue | ForEach-Object { $_.DiskIndex })
      if ($d.Count) { $espDisk = [int]$d[0]; $espKnown = $true } else { Start-Sleep -Milliseconds 300 }
    }
  }
} catch { } finally { if ($tmp) { & mountvol.exe $tmp /d 2>&1 | Out-Null } }
"""


def _wmi_disks():
    """Every disk through classic WMI (Win32_DiskDrive), in list_disks' fields, marked Via=Win32_DiskDrive. 2.5.4 logs
    (22 PCs): Get-Disk and MSFT_Disk listed 0 disks while Win32_DiskDrive listed 2-4; on 8 of them the Storage Management
    Provider service (smphost) did not exist at all, which no repair brings back. Index is the PhysicalDrive number the
    storage cmdlets and diskpart use. The boot and system disks are found through the partitions Windows boots from and
    runs from, so eligible() refuses them exactly as it does a Get-Disk listing.
    Win32_DiskPartition.BootPartition marks a disk's active (MBR) or EFI system (GPT) partition, which every bootable
    stick has, a stick 1401 wrote before included. Counted on USB disks it refused the picked stick as "the disk the
    computer booted from": 2.6.3 uploads, 28 of the 29 writes that took this route. It is counted on the other disks
    only; a USB disk Windows runs from is still refused through the system drive ($sys)."""
    out = _ps("""$ErrorActionPreference = 'SilentlyContinue'
""" + _BOOT_ESP_PS + """$sysd = $env:SystemDrive
$sys = @(Get-WmiObject -Query "ASSOCIATORS OF {Win32_LogicalDisk.DeviceID='$sysd'} WHERE AssocClass=Win32_LogicalDiskToPartition" | ForEach-Object { $_.DiskIndex })
$usbd = @(Get-WmiObject -Class Win32_DiskDrive | Where-Object { $_.InterfaceType -eq 'USB' -or ($_.PNPDeviceID + '') -like 'USBSTOR\\*' } | ForEach-Object { $_.Index })
$boot = @(Get-WmiObject -Class Win32_DiskPartition | Where-Object { $_.BootPartition -and (-not $espKnown -or $usbd -notcontains $_.DiskIndex) } | ForEach-Object { $_.DiskIndex })
if ($espKnown) { $boot += $espDisk }
@(Get-WmiObject -Class Win32_DiskDrive | ForEach-Object {
  [pscustomobject]@{ Index = $_.Index; Model = $_.Model; SerialNumber = $_.SerialNumber; PNPDeviceID = $_.PNPDeviceID;
    InterfaceType = $_.InterfaceType; MediaType = $_.MediaType; Size = [int64]$_.Size;
    IsSystem = ($sys -contains $_.Index); IsBoot = ($boot -contains $_.Index) } }) | ConvertTo-Json -Compress""")
    disks = []
    for w in _as_list(out):
        if not isinstance(w, dict) or w.get("Index") is None:
            continue
        pnp = (w.get("PNPDeviceID") or "").strip()
        usb = (w.get("InterfaceType") or "").upper() == "USB" or pnp.upper().startswith("USBSTOR\\")
        disks.append({"Number": int(w["Index"]), "FriendlyName": (w.get("Model") or "").strip(),
                      "SerialNumber": (w.get("SerialNumber") or "").strip(), "UniqueId": pnp,
                      "BusType": "USB" if usb else (w.get("InterfaceType") or "unknown"), "Size": int(w.get("Size") or 0),
                      "IsBoot": bool(w.get("IsBoot")), "IsSystem": bool(w.get("IsSystem")), "IsOffline": False,
                      "IsReadOnly": False, "PartitionStyle": "unknown", "Via": "Win32_DiskDrive"})
    return disks


def list_disks(_repaired=False):
    """Every disk, with the fields eligible() and the write read. Get-Disk first; when it lists nothing at all (2.2.0
    write logs, two PCs: "Windows lists 0 disk(s)" right after the window had listed the stick through WMI, so every
    write stopped as DISK-RENUMBERED), the same MSFT_Disk class the window reads, with its numeric bus and partition
    codes named the way Get-Disk names them."""
    disks = _as_list(_ps(f"Get-Disk | Select-Object {FIELDS} | ConvertTo-Json -Compress"))
    if disks:
        return disks
    raw = _as_list(_ps(f"Get-CimInstance -Namespace root/Microsoft/Windows/Storage -ClassName MSFT_Disk | "
                       f"Select-Object {FIELDS} | ConvertTo-Json -Compress"))
    for d in raw:
        if isinstance(d.get("BusType"), int):
            d["BusType"] = BUS_NAMES.get(d["BusType"], f"bus {d['BusType']}")
        if isinstance(d.get("PartitionStyle"), int):
            d["PartitionStyle"] = STYLE_NAMES.get(d["PartitionStyle"], "RAW")
    if raw:
        print(f"OK Get-Disk listed nothing; {len(raw)} disk(s) read from MSFT_Disk instead")
    elif not _repaired and _repair_storage_wmi():
        # every PC has at least the disk Windows runs from: an empty list means the storage provider is broken
        return list_disks(_repaired=True)
    if not raw:
        raw = _wmi_disks()
        if raw:
            print(f"OK the storage service listed no disks; {len(raw)} disk(s) read from Win32_DiskDrive instead "
                  "(the stick is checked there and erased with diskpart)")
    return raw


def _log_powershell_context():
    """One line on the PowerShell the writer starts, for a disk list that came back empty: its version, language mode
    (Constrained Language Mode blocks parts of the Storage module), whether it is 64-bit, the Storage module it loads,
    and the two services Get-Disk depends on. Never raises: this is a diagnostic, not a step."""
    try:
        out = _ps("$m = Get-Module -ListAvailable Storage | Select-Object -First 1; "
                  "$s = Get-Service smphost, winmgmt -ErrorAction SilentlyContinue | ForEach-Object { \"$($_.Name)=$($_.Status)\" }; "
                  # 2.5.3 (32 PCs): Get-Disk and Get-CimInstance MSFT_Disk empty with both services running and the
                  # provider re-registered, while the window read MSFT_Disk through .NET's WMI. These counts say which
                  # other route still sees the disks: the classic WMI API, Win32_DiskDrive, the storage subsystem.
                  "$wm = @(Get-WmiObject -Namespace root/Microsoft/Windows/Storage -Class MSFT_Disk -ErrorAction SilentlyContinue).Count; "
                  "$dd = @(Get-WmiObject -Class Win32_DiskDrive -ErrorAction SilentlyContinue).Count; "
                  "$ss = @(Get-StorageSubSystem -ErrorAction SilentlyContinue).Count; "
                  "$ad = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole("
                  "[Security.Principal.WindowsBuiltInRole]::Administrator); "
                  "\"PowerShell $($PSVersionTable.PSVersion) mode=$($ExecutionContext.SessionState.LanguageMode) "
                  "x64=$([Environment]::Is64BitProcess) Storage=$($m.Version) services=$($s -join ',') "
                  "wmi-MSFT_Disk=$wm Win32_DiskDrive=$dd subsystems=$ss admin=$ad\"")
        print("OK disk list context: " + " ".join(out.split())[:300]
              + f"; writer x64={sys.maxsize > 2**32}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"WARN disk list context unavailable: {type(e).__name__}: {str(e)[:200]}", flush=True)


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


def wmi_check_script(disk, erase_os=False):
    """check_script for a disk listed through Win32_DiskDrive (no storage cmdlets on this PC): disk N must still be the
    same model, serial and size, on USB, and not the disk Windows boots or runs from. Unless erase_os, a partition
    Windows cannot name (an Apple or Linux one shows as "GPT: Unknown") stops the write so the app can ask."""
    ok, why = eligible(disk, allow_large=True)
    if not ok:
        raise UsbError("refusing: " + "; ".join(why))
    n, size = int(disk["Number"]), int(disk["Size"])
    return _BOOT_ESP_PS + f"""$ErrorActionPreference = 'Stop'
$d = @(Get-WmiObject -Class Win32_DiskDrive -ErrorAction SilentlyContinue | Where-Object {{ $_.Index -eq {n} }})
if (-not $d.Count) {{ throw '1401: disk {n} is not attached any more (Windows renumbered the stick). Nothing was erased. Press Refresh, pick the stick again and write.' }}
$d = $d[0]
$sysd = $env:SystemDrive
$sys = @(Get-WmiObject -Query "ASSOCIATORS OF {{Win32_LogicalDisk.DeviceID='$sysd'}} WHERE AssocClass=Win32_LogicalDiskToPartition" | ForEach-Object {{ $_.DiskIndex }})
$usb = ($d.InterfaceType -eq 'USB') -or (($d.PNPDeviceID + '') -like 'USBSTOR\\*')
$bootHere = if ($espKnown) {{ $espDisk -eq {n} }} else {{ @(Get-WmiObject -Class Win32_DiskPartition | Where-Object {{ $_.BootPartition -and $_.DiskIndex -eq {n} }}).Count -gt 0 }}
if ([int64]$d.Size -ne {size} -or ($d.Model + '').Trim() -ne {_q(disk.get('FriendlyName'))} -or
    ($d.SerialNumber + '').Trim() -ne {_q((disk.get('SerialNumber') or '').strip())} -or -not $usb -or
    ($sys -contains {n}) -or $bootHere) {{
  throw '1401: disk {n} is not the USB stick you picked any more. Nothing was erased.'
}}
""" + ("" if erase_os else f"""$odd = @(Get-WmiObject -Class Win32_DiskPartition | Where-Object {{ $_.DiskIndex -eq {n} -and ($_.Type + '') -like '*Unknown*' }})
if ($odd.Count) {{
  $list = ($odd | ForEach-Object {{ 'a partition Windows cannot read ' + [math]::Round($_.Size / 1GB, 1) + ' GB' }}) -join ', '
  throw ('1401-OS-PARTITIONS: disk {n} holds ' + $list + ' (it may be a Mac or Linux system). Nothing was erased.')
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


def current_number(disk):
    """The stick's disk number now. Taking a stick offline and online (the write's own retry, release()) can give it a
    new number: a 1.15 write log (10-13, ADATA USB Flash Drive) then sent diskpart "select disk 3" and got "The disk
    you specified is not valid". Found again by serial; by size and model when the serial does not identify exactly one
    disk (some controllers report a new serial on every read); the number the user picked when neither does."""
    n = int(disk["Number"])
    if platform.system() != "Windows":
        return n
    out = _ps(f"""$sn = {_q((disk.get('SerialNumber') or '').strip())}; $sz = {int(disk['Size'])}; $fn = {_q(disk.get('FriendlyName'))}
$all = @(Get-Disk -ErrorAction SilentlyContinue)
$hit = @($all | Where-Object {{ $sn -and (($_.SerialNumber + '').Trim() -eq $sn) }})
if ($hit.Count -ne 1) {{ $hit = @($all | Where-Object {{ $_.Size -eq $sz -and $_.FriendlyName -eq $fn -and $_.BusType -eq 'USB' }}) }}
if ($hit.Count -eq 1) {{ Write-Output "NUMBER=$($hit[0].Number)" }}
""")
    got = next((ln.split("=", 1)[1].strip() for ln in (out or "").splitlines() if ln.startswith("NUMBER=")), "")
    return int(got) if got.isdigit() else n


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
                # shutil.Error carries one (source, destination, reason) per file: the STOP was that whole list with
                # the user's paths in it (1.15 write log 10-14, WinError 433 on every BlueToolFixup file). One line.
                if isinstance(error, shutil.Error) and error.args and isinstance(error.args[0], list) and error.args[0]:
                    bad = error.args[0]
                    first = bad[0][2] if isinstance(bad[0], tuple) and len(bad[0]) == 3 else str(bad[0])
                    raise UsbError(f"copying the EFI to the stick failed for {len(bad)} file(s): {first}") from error
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


# diskpart exits with the HRESULT of the command that failed. 0x80070005 is "access denied": seen on 1.13 (two
# reports, 10-11) after all retries, where the bare number told the user nothing.
E_ACCESSDENIED = 0x80070005


def _diskpart_failure(code, output):
    """The stop shown when diskpart could not erase the stick, naming the cause when the exit code identifies one."""
    if code & 0xFFFFFFFF == E_ACCESSDENIED:
        return ("Windows refused access to the stick (access denied, diskpart 0x80070005) - nothing was erased. The stick "
                "is write-protected (check for a lock switch on it or its card adapter), or another program has it open: "
                "close Explorer windows showing it, other USB tools (Rufus, balenaEtcher, Ventoy) and any antivirus scan "
                "of it, unplug it and plug it back in, then try again. If it still refuses, use another stick. "
                f"diskpart said: {output}")
    return f"Windows could not erase the stick (diskpart exit {code}): {output}"


def _diskpart(script):
    """diskpart /s from a fresh private temp file: /s mode stops at the first failed command with a non-zero exit."""
    import tempfile  # noqa: PLC0415
    fd, sp = tempfile.mkstemp(prefix="1401-", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="ascii", newline="") as fh:
            fh.write(script)
        p = subprocess.run([_system_tool("diskpart.exe"), "/s", sp], capture_output=True, text=True,
                           encoding=_OEM, errors="replace", timeout=TIMEOUT)
        for _ in range(3):  # a just-released stick can refuse clean ("not ready"/"access denied") for a few seconds
            if p.returncode == 0:
                break
            time.sleep(5)
            p = subprocess.run([_system_tool("diskpart.exe"), "/s", sp], capture_output=True, text=True,
                           encoding=_OEM, errors="replace", timeout=TIMEOUT)
        if p.returncode != 0:
            raise UsbError(_diskpart_failure(p.returncode, (p.stdout or p.stderr).strip()[-1200:]))
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
    if disk.get("Via") == "Win32_DiskDrive":
        root = _write_wmi_erase(disk, erase_os)
        return _write_payload(root, efi_build_dir, recovery_info, progress, machine_profile)
    _ps(check_script(disk, erase_os))
    from . import rawdisk  # noqa: PLC0415
    n = int(disk["Number"])
    letter = _free_letter()
    try:
        try:
            rawdisk.wipe_mbr_fat32(n, int(disk["Size"]), PART_CAP, say=lambda m: print(m, flush=True))
        except rawdisk.DiskError as e:
            # A 2.0.1 write log: "cannot open \\.\PhysicalDrive1 (Windows error 2)" right after its volume was locked;
            # the stick had come back under another disk number. Find it again by serial and erase that one, once.
            moved = current_number(disk) if "Windows error 2" in str(e) else n
            if moved == n:
                raise
            print(f"(Windows renumbered the stick: disk {n} is now disk {moved}; erasing that one)", flush=True)
            n = moved
            rawdisk.wipe_mbr_fat32(n, int(disk["Size"]), PART_CAP, say=lambda m: print(m, flush=True))
    except rawdisk.DiskError as e:
        # Some sticks refuse raw sector writes outright (1.7 logs 10-10: Lexar, "Windows error 5" with nothing else
        # using them). Windows' own diskpart erase goes through the volume manager and works on them; it was the
        # writer's path before the raw erase, so it is kept as the fallback rather than ending the write. 2.5.4 logs (two
        # "Generic Flash Disk" sticks) refused them with error 1117, an I/O device error on the raw handle: the same
        # fallback, since diskpart reaches the stick through the volume manager rather than that handle.
        code = re.search(r"Windows error (\d+)\)", str(e))
        if not code or int(code.group(1)) not in RAW_REFUSED:
            raise
        print("(this stick refuses direct writes; erasing it with Windows' diskpart instead)", flush=True)
        n = current_number(disk)
        release(n)
        _diskpart(diskpart_script({**disk, "Number": n}, letter))
    script = (f"""$ErrorActionPreference = 'Stop'
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
# The one letter picked earlier can be refused (taken since, or reserved): 4 sticks on 1.14.2 stopped here. Let Windows
# choose any free letter, then diskpart's assign, before giving up.
if (-not $letter -and $p) {{
  try {{ Add-PartitionAccessPath -DiskNumber $p.DiskNumber -PartitionNumber 1 -AssignDriveLetter -ErrorAction Stop }} catch {{ }}
  Start-Sleep 2; Update-HostStorageCache; $p = Get-Partition -DiskNumber $p.DiskNumber -PartitionNumber 1 -ErrorAction SilentlyContinue; $letter = Letter-Of $p
}}
if (-not $letter -and $p) {{
  $dp = Join-Path $env:TEMP ('1401-assign-' + [guid]::NewGuid().ToString() + '.txt')
  Set-Content -Path $dp -Encoding ASCII -Value ("select disk " + $p.DiskNumber + "`r`nselect partition 1`r`nassign`r`n")
  & (Join-Path $env:SystemRoot 'System32\diskpart.exe') /s $dp | Out-Null
  Remove-Item $dp -ErrorAction SilentlyContinue
  Start-Sleep 2; Update-HostStorageCache; $p = Get-Partition -DiskNumber $p.DiskNumber -PartitionNumber 1 -ErrorAction SilentlyContinue; $letter = Letter-Of $p
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
    try:
        out = _ps(script)
    except UsbError as e:
        # 1.8 log 10-10 (a "VendorCo ProductCode" stick): the raw erase succeeded but Windows never showed the new
        # partition. Windows' own diskpart erase makes Windows re-read the stick, then the same find-and-format runs again.
        # 1.15 logs 10-13 (General UDisk, SanDisk 3.2Gen1, TOSHIBA TransMemory): the raw erase left a lettered partition
        # with no volume behind it - Format-Volume found no MSFT_Volume for the letter and format.com said "Invalid media
        # or Track 0 bad" / "Specified drive does not exist". diskpart's own clean + format rebuilds the volume through the
        # volume manager, the same rescue as for a partition Windows never showed.
        unshown = "did not show its new partition" in str(e)
        if not unshown and "Format-Volume:" not in str(e) and "did not finish preparing" not in str(e):
            raise
        print("(Windows did not pick up the erased stick; erasing it with Windows' diskpart and looking again)" if unshown else
              "(Windows could not format the erased stick; erasing it with Windows' diskpart instead)", flush=True)
        # 2.0.2 write logs 10-15 (3 x an "F8 T5" USB SSD): diskpart then failed "The request is not supported" and the log
        # never said why Format-Volume failed first, so nothing could be done about it. The first error rides along now.
        print(f"(the format error was: {str(e)[:400]})", flush=True)
        n = current_number(disk)
        release(n)
        _diskpart(diskpart_script({**disk, "Number": n}, letter))
        # diskpart has already made, formatted and lettered the partition. Five 1.8/1.9 logs (10-10, all the same
        # "VendorCo ProductCode" stick) passed diskpart and then failed the second search, which looks the stick up by
        # bus type, size and serial that this stick does not report the same way twice. The letter diskpart assigned
        # is the answer; the search only runs again when that drive never appears.
        out = ""
        for _ in range(30):
            if os.path.isdir(letter + ":\\"):
                break
            time.sleep(1)
        else:
            out = _ps(script)
    got_letter = next((ln.split("=", 1)[1].strip() for ln in (out or "").splitlines() if ln.startswith("LETTER=")), "")
    letter = got_letter[:1].upper() if got_letter[:1].isalpha() else letter
    root = letter + ":\\"
    for _ in range(60):
        if os.path.isdir(root):
            break
        time.sleep(0.5)
    if not os.path.isdir(root):
        raise UsbError(f"diskpart finished but {root} did not appear")
    return _write_payload(root, efi_build_dir, recovery_info, progress, machine_profile)


def _write_wmi_erase(disk, erase_os):
    """The erase when this PC has no working storage cmdlets: every Get-Disk / Get-Partition / Format-Volume step of the
    usual path would fail, so the stick is checked through classic WMI and erased by diskpart alone (clean, MBR, FAT32,
    letter), which goes through the volume manager rather than the storage provider. Returns the drive root."""
    _ps(wmi_check_script(disk, erase_os))
    letter = _free_letter()
    print("(erasing the stick with Windows' diskpart: this PC's storage service lists no disks)", flush=True)
    _diskpart(diskpart_script(disk, letter))
    root = letter + ":\\"
    for _ in range(60):
        if os.path.isdir(root):
            return root
        time.sleep(0.5)
    raise UsbError(f"diskpart finished but {root} did not appear")


def _write_payload(root, efi_build_dir, recovery_info, progress, machine_profile):
    """Everything after the erase: the recovery image (checked as it arrives and read back), the EFI, the driver."""
    from . import apple  # noqa: PLC0415
    from . import machine_handoff  # noqa: PLC0415
    got = (apple.copy_local if recovery_info.get("local") else apple.download)(recovery_info, root, progress)
    # the image checked out while it arrived; this checks what the stick actually kept (see apple.verify_written)
    with open(got["chunklist"], "rb") as fh:
        changed = apple.verify_written(got["image"], apple.parse_chunklist(fh.read()))
    if changed and len(changed) <= 16:
        # A few parts read back wrong: write those parts once more (fetched again and hash-checked) and check again.
        # Many parts wrong is a stick smaller than it claims or a dying one; that is not retried.
        print(f"(parts {', '.join(map(str, changed[:16]))} of {got['chunks']} read back different; writing them again)", flush=True)
        try:
            with open(got["chunklist"], "rb") as fh:
                changed = apple.repair_written(recovery_info, got["image"], apple.parse_chunklist(fh.read()), changed)
        except (apple.AppleError, OSError, apple.http.client.HTTPException) as e:
            print(f"(writing them again failed: {type(e).__name__}: {str(e)[-160:]})", flush=True)
    if changed:
        raise UsbError(f"this stick changed the macOS image after it was written ({len(changed)} of {got['chunks']} parts "
                       f"read back different: {', '.join(map(str, changed[:12]))}{' ...' if len(changed) > 12 else ''}). "
                       f"The stick is failing or not the size it claims: use another USB stick.")
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


def verify_efi_copy(source, destination, copy=None):
    """Read the written EFI files back before reporting a ready installer. A file that differs is copied once more and
    checked again: a 1.15 write (10-13) stopped on OC/Kexts/itlwm.kext alone, the shape of an antivirus scan holding or
    changing one file, or one bad write. Still different after that, the write stops and says which files."""
    import hashlib

    def digest(path):
        hasher = hashlib.sha256()
        with open(path, 'rb') as stream:
            for block in iter(lambda: stream.read(1 << 20), b''):
                hasher.update(block)
        return hasher.digest()

    def differing():
        bad = []
        for folder, _, files in os.walk(source):
            for name in files:
                original = os.path.join(folder, name)
                relative = os.path.relpath(original, source)
                target = os.path.join(destination, relative)
                if not os.path.isfile(target) or digest(original) != digest(target):
                    bad.append(relative)
        return bad

    bad = differing()
    if bad:
        copy = copy or shutil.copy2
        print(f"(the stick kept {len(bad)} EFI file(s) different from the build; copying them again)", flush=True)
        for relative in bad:
            target = os.path.join(destination, relative)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            try:
                copy(os.path.join(source, relative), target)
            except OSError as error:
                print(f"(copying {relative} again failed: {type(error).__name__})", flush=True)
        bad = differing()
    if bad:
        raise UsbError('The written EFI did not match the build: ' + ', '.join(bad[:4]) + (' ...' if len(bad) > 4 else '')
                       + '. The stick is not ready. If an antivirus is running, let it allow the 1401 folder and write again.')

def needs_nullmoth(efi_build_dir):
    """True when the built config carries the NullMoth driver's boot-args (only nullmoth.apply writes nvaccel=1)."""
    import plistlib  # noqa: PLC0415
    with open(os.path.join(efi_build_dir, "EFI", "OC", "config.plist"), "rb") as fh:
        cfg = plistlib.load(fh)
    nv = cfg.get("NVRAM", {}).get("Add", {}).get("7C436110-AB2A-4BBB-A880-FE41995C9F82", {})
    return "nvaccel=1" in (nv.get("boot-args") or "").split()


def _pinned_package(path):
    """The driver package this build pins, from the folder the app passed. A folder kept across updates holds every
    version, and the app took the first by name: a 1.8 app passed nullmoth-nvidia-1.7.0.tar.gz (10-10), so the stick
    went to the network for 1.8.0, and "1.10.0" sorts before "1.9.0". The pinned name wins when it is there."""
    from . import nullmoth  # noqa: PLC0415
    pinned = os.path.join(os.path.dirname(path), nullmoth.PACKAGE["name"])
    return pinned if os.path.isfile(pinned) else path


def _fetch(url, path, tries=8, sleep=None):
    """Downloads url to path, resuming a dropped connection from the bytes already on disk (a Range request); a server
    that ignores the range starts the file over. WAS: three tries, each from byte 0 of a 371 MB package, and a body that
    stayed short on every try returned as if done (1.15 write log 10-13: two drops, then "STOP RemoteDisconnected").
    The package's SHA-256 is still checked by the caller before anything reaches the stick."""
    import re as _re  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415
    sleep = sleep or time.sleep
    if os.path.exists(path):
        os.remove(path)
    want = 0
    for attempt in range(tries):
        have = os.path.getsize(path) if os.path.exists(path) else 0
        try:
            req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
            with urllib.request.urlopen(req, timeout=60) as r:
                rng = (r.headers.get("Content-Range") or "") if have else ""
                m = _re.match(r"bytes (\d+)-\d+/(\d+)", rng)
                if have and not (m and int(m.group(1)) == have):
                    have = 0  # the server sent the whole file, not the rest
                if m and have:
                    want = int(m.group(2))
                elif not have:
                    want = int(r.headers.get("Content-Length") or 0)
                with open(path, "ab" if have else "wb") as fh:
                    shutil.copyfileobj(r, fh, 1 << 20)
            size = os.path.getsize(path)
            if not want or size == want:
                return
            print(f"(the driver download stopped at {size} of {want} bytes; resuming)", flush=True)
        except OSError as error:
            if attempt == tries - 1:
                raise
            print(f"(the driver download failed: {type(error).__name__}; resuming)", flush=True)
        sleep(min(5 * (attempt + 1), 30))
    size = os.path.getsize(path) if os.path.exists(path) else 0
    raise OSError(f"the driver download stopped at {size} of {want} bytes after {tries} tries - check the connection "
                  f"and write again")

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
    denied = _diskpart_failure(2147942405, "DiskPart has encountered an error: Access is denied.")
    arm("diskpart's access-denied exit names write protection and programs holding the stick",
        "access denied" in denied and "write-protected" in denied and "nothing was erased" in denied, denied[:60])
    arm("the same code as a signed 32-bit value is recognised too", "write-protected" in _diskpart_failure(-2147024891, ""),
        "-2147024891")
    other = _diskpart_failure(2, "The system cannot find the file specified.")
    arm("any other diskpart failure keeps its exit code and output", other.startswith("Windows could not erase the stick "
        "(diskpart exit 2)") and "write-protected" not in other, other[:60])
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


STICK_ADVICE = (" - the USB stick stopped accepting writes. That is the stick or its port, not the build: plug it into a "
                "rear USB port on the motherboard (not a hub or the front panel), or use another stick (16 GB or more, a "
                "known brand), and press Next again.")


def stick_hint(e):
    """Advice for a write that died because the stick did. 1.9.0 logs (10-10): format.com "Invalid media or Track 0 bad",
    EINVAL copying the driver package after a full download, PermissionError/OSError mid-image ("the stick's file could
    not be reopened"), and the disk vanishing all reached users as bare errors with nothing to do about them."""
    s = str(e)
    # WinError 433 "a device which does not exist" / 1167 "the device is not connected": the stick dropped off the bus
    # mid-copy (1.15 write logs 10-14). "read back different" = the bytes on the stick are not the bytes written.
    if isinstance(e, OSError) and getattr(e, "errno", None) in (5, 22) or "could not be reopened" in s \
            or "Track 0 bad" in s or "Invalid media" in s or "not attached any more" in s \
            or "WinError 433" in s or "WinError 1167" in s or "read back different from the stick" in s:
        return STICK_ADVICE
    return ""


def refind(disks, uid, size, name):
    """The stick the user picked, by what it is rather than its number: Windows renumbers USB disks (an offline/online
    cycle, a re-plug, another drive), and 26 PCs on 2.1.0 stopped with 1401-DISK-RENUMBERED. Its UniqueId first; size and
    model when the id does not name exactly one USB disk (some controllers report a new id on every read). None when
    neither names exactly one, so a different disk is never taken for it."""
    uid = (uid or "").strip()
    if uid:
        hit = [d for d in disks if (d.get("UniqueId") or "").strip() == uid]
        if len(hit) == 1:
            return hit[0]
    def same_size(d):
        have, want = int(d.get("Size") or 0), int(size or -1)
        if d.get("Via") == "Win32_DiskDrive":
            return 0 <= want - have < WMI_SIZE_SLACK
        return have == want
    hit = [d for d in disks if d.get("BusType") == "USB" and same_size(d)
           and (d.get("FriendlyName") or "").strip() == (name or "").strip()]
    return hit[0] if len(hit) == 1 else None


def cli_write(argv):
    """write <disk number> <EFI build dir> <darwin major> [--driver <tar.gz>] [--extra <file>]... [--profile <Report.json>] [--allow-large]
    The Windows app's write step. Every line printed is "STEP|OK|PROGRESS|STOP ..." so the window can show it."""
    from . import apple, nullmoth, netsupport  # noqa: PLC0415
    num, efi, darwin = int(argv[0]), argv[1], int(argv[2])
    def opt(n): return [argv[i + 1] for i, a in enumerate(argv) if a == n and i + 1 < len(argv)]
    disks = list_disks()
    disk = next((d for d in disks if int(d.get("Number", -1)) == num), None)
    ident = (opt("--stick-id") or [""])[0], (opt("--stick-size") or [""])[0], (opt("--stick-name") or [""])[0]
    if any(ident):
        # the window says which stick it means: that stick wins over the number, and a disk that took the number is
        # never written
        found = refind(disks, *ident)
        if found is not None and int(found.get("Number", -1)) != num:
            print(f"OK the stick is disk {found.get('Number')} now (it was disk {num} when it was picked)")
            num = int(found["Number"])
        disk = found
    if not disks:
        # 2.4.3 write logs (10-19..21, 36 PCs): every "DISK-RENUMBERED" stop followed "Windows lists 0 disk(s)" - not even
        # the disk Windows runs from - after Get-Disk, MSFT_Disk and the storage-provider repair all came back empty and
        # silent, while the window had just listed the stick through the same MSFT_Disk class in-process. The stick had
        # not moved; this PowerShell could not see any disk. Say that, and log what the PowerShell is, so the next log
        # names the cause.
        _log_powershell_context()
        print("STOP 1401-DISK-LIST-EMPTY: Windows' storage service gave 1401 an empty list of disks - not even the disk "
              "Windows runs from - so the stick cannot be checked before it is erased. Nothing was erased. Restart the PC "
              "and write again; if this repeats, use Send logs."); return 1
    if not disk:
        # The number came from the window's list, and Windows hands USB sticks new numbers (after an earlier attempt, or a
        # re-plug). 2.0.2 blamed the stick here, before anything was written, and users retried the same stale number
        # 3-4 times (11 write logs in two hours on 10-15). The window now reloads its list when it reads this.
        # 2.0.3 logs from two PCs said only "disk 1 is gone": what Windows lists instead is printed first, so the next
        # log shows whether the stick came back under another number or was not listed at all.
        usb = [f"{d.get('Number')}: {d.get('FriendlyName') or '?'} {int(d.get('Size') or 0) / GiB:.1f} GiB"
               for d in disks if d.get("BusType") == "USB"]
        print(f"OK Windows lists {len(disks)} disk(s) now; USB: {', '.join(usb) or 'none'}")
        print(f"STOP 1401-DISK-RENUMBERED: Windows gave the stick a new disk number after it was picked (disk {num} is gone). "
              "Nothing was erased. The list of disks was reloaded: pick the stick again and press Write."); return 1
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
        shutil.copyfile(_pinned_package(drv[0]), os.path.join(cache, os.path.basename(_pinned_package(drv[0]))))
    # A recovery image already downloaded elsewhere (1401\\Recovery, or --recovery-dir) is used first: Apple refuses some
    # networks on every session (HTTP 403 in 1.2.0 logs) and some PCs have no internet at all.
    rec = (opt("--recovery-dir") or [RECOVERY_DIR])[0]
    info = apple.local_image(rec)
    if netsupport.needs_local_image(efi):
        # The build found no network adapter the macOS installer can use: say what the install will need, then write.
        print("NOTE " + netsupport.OFFLINE_INSTALLER_MESSAGE, flush=True)
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
            print(f"STOP {type(e).__name__}: {e}{stick_hint(e)}", flush=True)
            print("WHERE " + " < ".join(reversed(where)), flush=True); sys.exit(1)
    print(json.dumps(list_disks(), indent=2))
