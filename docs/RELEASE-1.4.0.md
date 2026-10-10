# 1401 1.4.0 for Windows

Includes the Mac app and NVIDIA driver 1.4.0 ([release notes](https://github.com/nullmoth/nvidia-macos-driver/releases/tag/v1.4.0)).
**Something not working? [nullmothsystems.com/help](https://nullmothsystems.com/help) lists every known problem and exactly what to do.**

Changes
- **PCs whose ACPI tables crashed the disassembler.** Some firmware made the ACPI tool crash outright ("could not read this PC's ACPI tables"). 1401 now records the crash and keeps the table, and the build continues.
- **Partial hardware scans are accepted.** A scan missing the USB or Storage Controllers section was rejected as a whole; the build now continues with what is there.
- **Sticks that Windows renumbered or re-detected after erasing** are found again by serial and keep their drive letter; the EFI copy survives the stick blinking out.
- Everything from 1.3: resume-from-last-byte downloads, reuse a stick that has macOS/Windows on it, the EXITBS boot-freeze ladder, basic display for unsupported-only PCs.

Keep the whole 1401 folder together and run 1401.exe.
