# 1401

Install macOS on the PC you already own: the reverse of Boot Camp. 1401 runs on Windows, checks your hardware, builds
an OpenCore setup for it and writes a macOS install stick. It is free and open source.

- Download: [releases page](https://github.com/nullmoth/1401/releases) (`1401-Windows-<version>.zip`)
- Changes: [CHANGELOG.md](CHANGELOG.md)
- Problems: [troubleshooting](docs/TROUBLESHOOTING.md)
- How it works: [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md)
- NVIDIA driver for macOS: [nvidia-macos-driver](https://github.com/nullmoth/nvidia-macos-driver)

1401 has been tested end to end on a small number of PCs, so expect problems on others. If it doesn't work on yours,
the [OpenCore Install Guide](https://dortania.github.io/OpenCore-Install-Guide/) covers setting OpenCore up by hand.

## Using it

1. Unzip the release and keep the `1401` folder together. Run `1401.exe` as administrator (it reads the hardware and
   writes the stick).
2. Click Check this PC, Build the Mac setup, read Your BIOS steps, then Create the macOS stick. You need a USB stick of
   4 GB or more that can be erased, and an internet connection.
3. Restart, change the BIOS settings 1401 showed you, boot the stick and pick the macOS installer in the OpenCore menu.
   In Disk Utility, erase only the partition or disk meant for macOS (APFS), never a disk with Windows or data you
   want to keep. Then choose Reinstall macOS; the rest of macOS downloads from Apple.
4. With an NVIDIA card (GTX 16 or newer): once macOS is running, open the `NullMoth` folder on the stick and run
   1401.app, or download `1401-Mac-<version>.dmg` from the driver's releases page. It installs the driver and updates
   the OpenCore settings on the stick. Keep the stick plugged in: OpenCore on it is what starts macOS.

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
