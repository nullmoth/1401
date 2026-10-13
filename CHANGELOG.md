# Changelog

Each release also bundles the NVIDIA driver and Mac app of the same version; see the
[driver changelog](https://github.com/nullmoth/nvidia-macos-driver/blob/main/CHANGELOG.md).

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
