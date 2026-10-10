# 1401 1.6.0 for Windows

Includes the Mac app and NVIDIA driver 1.6.0 ([release notes](https://github.com/nullmoth/nvidia-macos-driver/releases/tag/v1.6.0)).
**Something not working? [nullmothsystems.com/help](https://nullmothsystems.com/help) lists every known problem and exactly what to do.**

Changes
- **The Linux USB probe can build your EFI.** A probe folder (report.json + acpi/tables) converts into the same hardware report the Windows scan makes, with each device's OpenCore path, ACPI path and Resizable BAR state read from the probe.
- Driver 1.6.0: the driver no longer removes itself a few seconds after login on machines whose firmware ignores NVRAM changes made from macOS.
- Everything from 1.5, 1.4 and 1.3 still applies.

Keep the whole 1401 folder together and run 1401.exe.
