# How 1401 works

1401 is a Windows app that turns a USB stick into a macOS installer built for one specific PC. This page follows the
four steps of the app through the code.

> 1401 is new and may not work on every PC. If it does not work on yours, set up OpenCore by hand with the
> [OpenCore Install Guide](https://dortania.github.io/OpenCore-Install-Guide/). The NVIDIA driver and its Mac app work
> on any OpenCore setup.

## 1. What is in the download

```
1401\
  1401.exe              the window (C#, .NET Framework 4.8, WinForms)            [windows/App/]
  engine\python\        embedded Python 3.12 for Windows, with wmi, pywin32, certifi
  engine\app\p1401\     the engine: every step the window runs                   [p1401/]
  engine\app\upstream\  OpCore-Simplify and Hardware Sniffer (pinned copies), bin\acpidump.exe, Scripts\iasl.exe
  NullMoth\             the NVIDIA driver package and the 1401 Mac app (copied to the stick for after the install)
```

`1401.exe` runs each step as `engine\python\python.exe -u -m <module>` from `engine\app` and shows its output. It runs
as administrator (`app.manifest`) because reading ACPI tables and writing a disk need it. Its working files go to
`%LOCALAPPDATA%\NullMoth\1401`, never next to the exe, so a folder synced by OneDrive cannot block it.

## 2. Check this PC (`p1401.scan`)

Hardware Sniffer reads the hardware through WMI (processor, board, graphics, network, audio, USB and storage
controllers) and writes `Report.json`. `acpidump.exe` (pinned by SHA-256) dumps the ACPI tables. Nothing is uploaded.

## 3. Build the Mac setup (`python -m p1401 build`)

`p1401/engine.py` drives OpCore-Simplify without its prompts: every question it would ask a person is answered by a
rule in 1401, the answer is recorded, and a question with no rule stops the build instead of guessing. It picks the
newest macOS the hardware runs natively, then the kexts, ACPI tables, SMBIOS and quirks, and writes an OpenCore `EFI`.
A folder from an earlier build is cleared first (read-only flags included).

`p1401/policy.py` then applies 1401's own rules to `config.plist` (listed in the README). The ones that matter most:
- **GeForce RTX** (`p1401/nullmoth.py`): if the card is in the driver's table (`nvidia_gsp_ids.json`), the target is
  capped at macOS 15, the driver's boot arguments and SIP value are set, and the installer gets a small GPU BAR
  (`ResizeAppleGpuBars 0`, `ResizeGpuBars -1`). The macOS installer has no NVIDIA driver and draws on the firmware's
  screen, which only survives macOS's PCI setup with a small BAR.
- **Core Ultra 200 (Arrow Lake)**: keeps OpenCore-Simplify's CPU spoof (macOS 15 does not know the CPU) and turns off
  CpuTopologyRebuild and `ctrsmt`.
- **Boot arguments are never deleted from NVRAM**, so booting the stick on a PC that already runs macOS leaves that
  system's boot arguments alone.

`p1401/validate.py` checks the result with OpenCore's own `ocvalidate` (downloaded from the same OpenCore release the EFI
was built from, checked by SHA-256) plus 1401's file checks. A validator that cannot run is a failure, not a pass.

## 4. Your BIOS steps (`p1401.guide`)

Reads the report and the built config and writes an HTML page with this board's steps: Windows traps first
(BitLocker, RAID to AHCI, Legacy to UEFI), then only the BIOS settings this config needs.

## 5. Create the macOS stick (`p1401.usbwriter write`)

1. **Safety checks.** Only USB disks are offered. A disk is refused if it is the boot or system disk, offline,
   read-only, or if it holds an operating system (an APFS, HFS+ or
   Windows recovery partition; an EFI or Microsoft reserved partition alone is normal on a USB stick). The disk is re-identified by serial number and size just
   before erasing, so a disk number that moved cannot be erased by mistake.
2. **Erase** (`p1401/rawdisk.py`), the way Rufus does it: lock and dismount every volume on the stick, zero the
   partition tables at both ends, then write a new MBR layout with one active FAT32 partition (16 GB) through the disk
   driver. Windows formats it FAT32 with the label `1401`.
3. **macOS from Apple** (`p1401/apple.py`): asks Apple's recovery server for the macOS recovery image, downloads
   `BaseSystem.dmg` to `com.apple.recovery.boot`, and checks every chunk against Apple's signed chunklist. An unsigned
   chunklist or a bad chunk stops the write.
4. **Startup files**: copies the built `EFI` folder.
5. **NVIDIA**: copies the driver package and the 1401 Mac app to `NullMoth\` on the stick.

## 6. When something fails

If a build fails, 1401 shows the reason and saves `%LOCALAPPDATA%\NullMoth\1401\build-log.txt`. It then tells you it is
sending that log to nullmothsystems.com (the Windows user name and PC name are removed first) and sends it when you click
OK; Cancel keeps it on the PC only. A stick made by 1401 also has OpenCore write its own log, Apple's boot log and any macOS
panic onto the stick. If macOS does not start, boot back into Windows and open 1401: it finds those files on the stick and,
after the same notice, sends them and moves them to `NullMoth\sent-logs` on the stick. Each upload gets a report ID to
quote when asking for help.

## 7. After macOS is installed

The 1401 Mac app (in the driver repo, `app/`) installs the NVIDIA driver. It finds the OpenCore that started the Mac,
shows every change before making it, backs the config up, and sets the driver's settings, including the card's full BAR
(8 GB on an RTX 5060). See the driver repo's `docs/HOW-IT-WORKS.md`.

## 8. Not used by the app

`loader/` is an experimental UEFI boot layer written in Rust, tested in QEMU only. Sticks made by 1401 boot with
OpenCore.
