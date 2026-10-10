# 1401 1.6.0 for Windows

Includes the Mac app and NVIDIA driver 1.6.0 ([release notes](https://github.com/nullmoth/nvidia-macos-driver/releases/tag/v1.6.0)).
**Something not working? [nullmothsystems.com/help](https://nullmothsystems.com/help) lists every known problem and exactly what to do.**

Changes
- **A Linux USB probe report can be built into an EFI.** A probe folder (report.json + acpi/tables) converts into the same hardware report the Windows scan makes (`python -m p1401.probe_report`), with each device's OpenCore path, ACPI path and Resizable BAR state read from the probe. If the Windows scan will not run on your PC, upload the probe and support builds your EFI from it.
- **Sticks whose serial number changes on every read are accepted.** Some USB sticks (SMI controllers) report a new serial each time Windows asks, so every write stopped with "disk N is not the USB stick you picked any more". The stick now counts as the same one when it is the only USB disk of that exact size and model at the picked disk number.
- **The macOS download keeps going on networks that pause it for minutes.** It now waits out up to about 15 minutes of empty connections (was about 2.5), asks Apple for a fresh download link along the way, and a reset on a resume no longer ends the download.
- Driver 1.6.0: the driver no longer removes itself a few seconds after login on machines whose firmware ignores NVRAM changes made from macOS.
- Everything from 1.5, 1.4 and 1.3 still applies.

Keep the whole 1401 folder together and run 1401.exe.
