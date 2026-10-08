# 1401

**macOS on the PC you already own: the reverse of Boot Camp.** Free of charge, never for sale. Hardware reports stay local until a log submission is explicitly approved.

Made by **NullMoth Systems**. Support the work: https://buymeacoffee.com/nullmoth

| Download (Releases) | What it is |
|---|---|
| `1401-Windows-1.0.23.zip` | the Windows app: checks your PC, builds its OpenCore setup, writes a macOS install stick |
| `1401-Mac-1.0.17.dmg` (in the [driver repo](https://github.com/nullmoth/nvidia-macos-driver) releases) | the Mac installer for the NVIDIA driver: open it and run **1401**; the helper package is a separate verified download or the copy staged on the USB stick |

> **1401 is new and may not work on every PC.** It has been tested end to end on one PC (Intel Core Ultra 5 225F,
> B860 board, GeForce RTX 5060). If it does not work on yours, set up OpenCore by hand with the
> [OpenCore Install Guide](https://dortania.github.io/OpenCore-Install-Guide/)
> ([OpenCore releases](https://github.com/acidanthera/OpenCorePkg/releases)). The Mac installer targets macOS 15 on OpenCore; individual GPU, display and application support requires validation.

How the code works, step by step: [`docs/HOW-IT-WORKS.md`](docs/HOW-IT-WORKS.md).

Maintenance changes: [`Windows 1.0.23 companion refresh`](docs/RELEASE-1.0.23.md).

## Using it

1. Unzip `1401-Windows-1.0.23.zip` and keep the `1401` folder together. Run `1401.exe` (it asks for administrator
   rights: it reads the hardware and writes the stick).
2. **Check this PC**, **Build the Mac setup**, read **Your BIOS steps**, then **Create the macOS stick** on a USB stick of
   4 GB or more that can be erased. You need internet.
3. Restart, change the BIOS settings 1401 showed you, boot the stick, and pick the macOS installer in the OpenCore menu.
   In the installer, choose only the intended macOS partition or volume. Do not erase a whole disk containing Windows or other data. Prepare verified backups and recovery media before changing partitions. Format only the intended macOS destination as APFS with Disk Utility, then choose Reinstall macOS. The installer
   downloads the rest of macOS from Apple.
4. With a supported Turing-or-later NVIDIA card: when macOS is running, open the `NullMoth` folder on the stick, unzip `1401-Mac-1.0.17.zip`
   and run **1401.app** (or download `1401-Mac-1.0.17.dmg`). It installs the NVIDIA driver and updates the driver-related OpenCore settings. Keep the 1401 stick plugged in while it runs and every time you start
   the Mac: OpenCore on that stick is what starts macOS, and it is the config 1401.app changes.
The Mac companion does not copy OpenCore onto an internal EFI. Keep its startup stick attached for every restart until that boot setup is separately reviewed.

5. Something went wrong? If the build fails, 1401 shows why and sends the log to nullmothsystems.com after telling you
   (Cancel keeps it on your PC). If macOS does not start from the stick, boot back into Windows, plug the stick in and open
   1401, or click **Scan for logs and send them**: the stick holds OpenCore's and macOS's startup logs and 1401 sends them.
   Quote the report ID it shows when you ask for help.

## What 1401 changes compared with the engine it builds on

1401 builds with [OpCore-Simplify](https://github.com/lzhoang2801/OpCore-Simplify) and then applies its own rules.
Every rule that fires is recorded in the build result.

| Rule | What it does |
|---|---|
| `sip-minimal` | SIP stays on unless a chosen feature needs it lowered, and then only as far as that feature needs |
| `tahoe-weg-amd`, `tahoe-weg-args` | macOS 26 with an AMD card: WhateverGreen removed (it panics on 26), its boot arguments stripped |
| `tahoe-intel-bt` | macOS 26 with Intel Bluetooth: `-ibtcompatbeta` |
| `arrow-lake-ctr`, `arrow-lake-ctrsmt` | Core Ultra 200 (Arrow Lake): CpuTopologyRebuild and `ctrsmt` off, matching a config that installs and runs macOS 15 on that CPU |
| `boot-logs-on-stick` | OpenCore writes its log, Apple's boot log and any macOS panic to the stick, so a PC that never reaches macOS can still report why |
| `keep-boot-args` | the stick never overwrites the boot arguments of a machine that already runs macOS |
| `nullmoth-boot-args`, `nullmoth-sip` | NVIDIA card in the driver's table: macOS 15, the driver's boot arguments, SIP `0x0A43` |
| `nullmoth-installer-bar` | NVIDIA card: small BAR for the installer (`ResizeAppleGpuBars 0`, `ResizeGpuBars -1`) so its screen survives PCI setup; the Mac app restores the full BAR after install |

## Tests

```bash
python3 tests/corpus/fetch.py          # public Hardware Sniffer reports, pinned by commit
python3 tests/run_corpus.py build      # build + rules + ocvalidate for every machine in the corpus
python3 -m p1401.selftest && python3 -m p1401.guide --selftest && python3 -m p1401.apple --selftest \
  && python3 -m p1401.usbwriter --selftest && python3 -m p1401.scan --selftest && python3 -m p1401.nullmoth --selftest
```

`loader/` is an experimental UEFI boot layer (Rust) tested in QEMU only. The app does not use it; sticks boot with
OpenCore.

## Legal

1401 is free of charge, forever, under the **PolyForm Noncommercial License 1.0.0** (`LICENSE`): use it, change it,
share it, but nobody may sell it or use it to make money. Third-party parts keep their own licences (`NOTICE.md`).
The NullMoth name and the moth logo belong to NullMoth Systems and are not licensed.
