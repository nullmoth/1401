# Changelog

Each release also bundles the NVIDIA driver and Mac app of the same version; see the
[driver changelog](https://github.com/nullmoth/nvidia-macos-driver/blob/main/CHANGELOG.md).

## 2.3.5
- Bundles NVIDIA driver 2.3.5: the login screen no longer stays black for a minute after the display comes up

## 2.3.4
- Bundles NVIDIA driver 2.3.4 (pre-release to the early-updates program first; see its changelog)
- Mac: the first-login report names the kernel driver version the Mac is actually running next to the one installed
  on disk, and says STALE when they differ. A Mac that kept running an older kernel driver after an update used to
  report the new version
- Mac: hybrid laptops with WhateverGreen next to the driver get the boot argument it needs (gfxrst=4), so the boot
  screen is not copied from memory the other card has released

## 2.3.3
- Bundles NVIDIA driver 2.3.3: the 2.3.1 driver on both macOS 15 and 26, installable on Sequoia; the 2.3.2 display
  changes that made some Macs worse are withdrawn until they pass a staged test (see its changelog)
- Mac: the app can update itself again ("signature could not be downloaded" was a deadlock in the app, not the server)
- Mac: the first-login report carries the installed component hashes and each display's refresh rate, and attaches the
  driver logs when the driver did not come up
- Send logs: every query has its own time limit, so a slow Mac no longer loses the log it was sending

## 2.3.2
- Checking a PC no longer fails when Python is installed on it: 1401's own Python ignores the PC's Python packages
  ("certifi has no attribute where", "win32com ... __gen_path__")
- Under Wine, 1401 stops at once and says it needs real Windows, instead of failing three times to read the hardware
- A PC that can only run up to macOS Sequoia stops with that answer when Tahoe was picked, instead of looping on the
  macOS version question
- If something on the PC rewrites OpenCore's boot files after the build (security software), 1401 writes them back
  from the verified release and says what changed them
- After a BIOS change (for example turning VMD off), 1401 checks the PC again instead of using the old scan
- A DSDT the ACPI compiler cannot read now travels in the build log, so it can be repaired
- Mac: Send logs no longer times out on a broken GPU stack (every query has its own time limit); it also includes
  how much video memory the driver uses
- Bundles NVIDIA driver 2.3.2: installing and updating on macOS Sequoia works again, and screenshots and the lock
  screen show windows again (see its changelog)

## 2.3.1
- Writing the installer stick: on PCs where Windows' storage service lists no disks at all (the write stopped with
  1401-DISK-RENUMBERED, or the stick list said "Invalid class"), 1401 repairs the service itself and lists the disks
  again. It also uses 64-bit PowerShell and logs PowerShell's own error
- Bundles NVIDIA driver 2.3.1: a driver update that cannot bring the display up falls back to the previous driver
  automatically (see its changelog)

## 2.3.0
- Mac: after a successful install, 1401 can confirm once that the Mac reached its desktop (you choose; the default
  is not to send). It sends one small summary at the first login, then removes itself, so a working install can be
  told apart from one that failed silently
- Writing the installer stick: when Get-Disk lists no disks at all, 1401 reads them through Windows' storage WMI
  instead of stopping
- When Windows' storage management is missing or damaged, the USB stick list names the repair instead of only
  "Invalid class"
- Mac: the AMD and Intel GPU test program. Join from the AMD/Intel panel to get the newest signed test build; after
  each restart 1401 sends what the AMD/Intel driver did. Leave from the same panel
- Bundles NVIDIA driver 2.3.0 (see its changelog)

## 2.2.0
- Writing the installer stick: when Windows gives the stick a new disk number after it was picked, 1401 finds the
  same stick again and keeps going (it used to stop with 1401-DISK-RENUMBERED); a different disk that took the old
  number is never written
- The Mac app is part of 1401 now. It installs the NVIDIA driver with that package's own installer, and the AMD/Intel
  test driver comes from its own package
- Bundles NVIDIA driver 2.2.0 (the NVIDIA driver only: no boot logo, no background jobs; see its changelog)

## 2.1.0
- When Windows refuses to start PowerShell, 1401 retries once and the log says why it was refused
- Bundles driver and Mac app 2.1.0 (per-generation GPU support, Blender Eevee lighting, desktop no longer waits
  on every frame, Map my GPU)

## 2.0.4
- When the stick's disk number is gone at write time, the log now lists the USB disks Windows shows, so the cause
  can be found
- Bundles driver and Mac app 2.0.4 (Prepare this Mac for Tahoe is back; the AMD / Intel test driver turns on for an
  Intel or AMD GPU switched off in OpenCore)

## 2.0.3
- When Windows gives the stick a new disk number after you pick it, 1401 says so and reloads the list, instead of
  stopping with "the USB stick stopped accepting writes" on every retry
- A volume on the stick that Windows removes while the erase starts no longer stops the write
- When Apple's download server keeps cutting the connection, the stop says what to change on your network
- Intel PCs (12th gen and newer) that stop at EB.MM.AKM because no kernel slide fit: rebuilding with the stick plugged
  in reads its startup log and turns on DevirtualiseMmio for the next start
- Bundle driver 2.0.3: the driver saves and restores the GPU across system sleep, diagnostic sysctls are gone from
  normal builds, and the Mac app explains a hidden NVIDIA card, lets AMD/Intel-only Macs try the test GPU driver, and
  adds an opt-in laptop brightness switch

## 2.0.2
- A PC with no network adapter that works in the macOS installer gets its stick written, with a note to connect a
  supported Ethernet or Wi-Fi adapter before installing. 2.0.0 stopped the write and asked for a recovery image that
  would not have helped
- A stick that Windows gives a new disk number just before the erase is found again and written
- Bundle driver 2.0.2 (the same driver as 2.0.0)

## 2.0.1
- PCs with an NVIDIA card can build for macOS 26 Tahoe. 2.0.0 offered only macOS 15 for them, so picking
  Tahoe stopped the build
- Bundle driver 2.0.1 (the same driver as 2.0.0)

## 2.0.0
- Pick macOS 15 Sequoia or macOS 26 Tahoe before the build
- Bundle driver 2.0.0 (security fixes, GeForce RTX 50 compute, flicker, refresh-rate and black-screen fixes)
- Tahoe boots and updates on PC models Apple did not ship it for, and boards with a Realtek 2.5G/5G port and Intel or
  Broadcom Wi-Fi no longer stop at the Apple logo
- Hybrid-core Intel PCs that stopped at EXITBS:START boot, and Intel PCs that froze with "No slide values are usable"
  get the matching memory-map setting
- Every AMD graphics card is identified, with what macOS can do on it shown in the build summary
- Experimental drivers are off unless you tick "Include experimental drivers": the AMD RX 9070 display driver and the
  MediaTek MT7921/MT7922 Wi-Fi driver. With it off, the build says which one your PC could use
- MediaTek Bluetooth works on the OEM versions people have; PCs with no supported network adapter get the offline
  installer by default
- NVMe drives macOS cannot install to are named before you start
- A rebuild for the same PC keeps its serial number, board serial, UUID and ROM; ask for a new one if macOS Setup
  says the Mac belongs to an organization
- A PC with a NullMoth-driver card is built for macOS 15 even when the engine suggests Ventura
- A build that stopped in the EFI step no longer locks out every later build
- Apple download errors (403, 502, cut-off downloads, a bad chunk) are retried where they can be and explained where
  they cannot
- USB stick writing: sticks Windows could not format are erased with diskpart, a renumbered stick is found again, and
  files that read back wrong are written again
- The Remove NVIDIA driver startup entry stays visible in the boot picker

## 1.15.0
- Fix the build stopping on ACPI tables that declare a method twice (BIOSTAR B650 and similar)
- Bundle driver 1.15.0 (fixes the GTX 16 black screen that started in 1.14)

## 1.14.7
- Leave the optional boot logo off in new builds

## 1.14.6
- Retry Apple recovery downloads that return HTTP 403

## 1.14.3
- Check for a newer version of 1401 at start-up
- Let Windows pick any free drive letter for the stick
- Retry downloads when Apple's server keeps answering 502
- Wait for antivirus to release the OpenCore validator before erasing

## 1.14.2
- Fix an empty "UsbError:" on Windows set to Chinese and other languages
- Fix "IsADirectoryError" when the stick is not ready
- Fix "'NoneType' object has no attribute 'headers'" while downloading macOS

## 1.14.0
- Work with Windows Smart App Control
- Fix "OCB: DMG has been altered" from sticks that don't keep what is written
- Prepare desktops for macOS 26
- Fix the build stopping when Windows reports a graphics card without a PCI ID

## 1.13.0
- Fix Turing cards stuck at start-up
- Fix "Remove NVIDIA driver" hanging in the boot picker

## 1.12.0
- Keep the Intel GPU on for laptop panels macOS has no driver for
- Name the files that changed when an EFI no longer matches its machine profile

## 1.11.0
- Include Lilu and AMFIPass for supported NVIDIA cards
- Read the stick's last startup log on the next build
- Fix the build failing on laptops with Iris Xe

## 1.10.0
- Use the memory settings AM5 Ryzen CPUs boot with on the first build
- Drop the DMAR table on Intel Core Ultra
- Apply the CFG-lock fix only when the log shows it is needed

## 1.9.0
- Try one more memory setting on AM5 boards
- Erase stubborn sticks with diskpart

## 1.8.0
- Use known-good settings for boards that have booted before
- Fix "Format-Volume: Invalid property" and "WinError 2" when erasing

## 1.7.0
- Pass the board's DSDT to macOS again (was dropped on about 1 in 5 PCs)
- Keep writing when Windows re-mounts the stick mid-download

## 1.6.0
- Build an EFI from a Linux USB probe report
- Accept sticks whose serial number changes on every read
- Wait out longer network stalls during the macOS download

## 1.5.0
- Finish the macOS download on networks that cut connections

## 1.4.0
- Build on PCs whose ACPI tables crash the disassembler
- Accept partial hardware scans

## 1.3.0
- Resume downloads from the last byte
- Reuse a stick that already has macOS or Windows on it
- Step through boot fixes for PCs that freeze at EXITBS:START

## 1.0.x
First public releases.
