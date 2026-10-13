# 1401 1.15.0 for Windows

**Something not working? [Why a machine does not work, and how to fix it](TROUBLESHOOTING.md) lists every known problem.**

Bundles the NVIDIA driver and Mac app [1.15.0](https://github.com/nullmoth/nvidia-macos-driver/releases/tag/v1.15.0),
the last release for macOS 15 Sequoia: the fix for GTX 16 and other cards without Resizable BAR (a regression since
1.14), fixes for stale window content, display sleep and wake, and the Mac setup and Send logs repairs.

## Fixed
- **ACPI table with a method declared twice** (BIOSTAR B650 and similar): the build stopped at "dsdt.aml could not be
  disassembled". The duplicate is now renamed while the build is planned, as duplicate devices already were.

## Scope
Windows 10/11, 64-bit. Builds macOS 15 Sequoia installers with OpenCore.
