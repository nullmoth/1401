# 1401 1.7.0 for Windows

Includes the Mac app and NVIDIA driver 1.7.0 ([release notes](https://github.com/nullmoth/nvidia-macos-driver/releases/tag/v1.7.0)).
**Something not working? [nullmothsystems.com/help](https://nullmothsystems.com/help) lists every known problem and exactly what to do.**

Changes
- **macOS gets your PC's ACPI table (DSDT) again on about 1 in 5 PCs.** macOS's ACPI interpreter throws away the whole DSDT when a `Scope()` points at a device the firmware only creates later; Windows and Linux load the same table fine. This hit 43 of the 233 PCs whose tables users have sent (every Arrow Lake H laptop among them, and several AM5 boards). 1401 now finds those `Scope()`s and defers them, and ships the repaired table in your EFI. Every repaired table was checked to load in the same ACPI interpreter macOS uses. Rebuild your EFI with 1.7 to get it.
- Everything from 1.6, 1.5, 1.4 and 1.3 still applies.

Keep the whole 1401 folder together and run 1401.exe.
