# 1401 1.3.0 for Windows

Includes the Mac app and NVIDIA driver 1.3.0 ([release notes](https://github.com/nullmoth/nvidia-macos-driver/releases/tag/v1.3.0)).
**Something not working? [nullmothsystems.com/help](https://nullmothsystems.com/help) lists every known problem and exactly what to do.**

Changes
- **Apple downloads finish on networks that cut connections.** Some networks close every download connection after 1 MB; 1401 keeps what arrived and continues from that byte (1.2.0 restarted the 10 MB chunk and stopped with "stream ended at 1048576/10485760").
- **Reuse a stick that has macOS or Windows on it.** A stick holding a macOS or Windows partition was refused; 1401 names what is on it and asks before erasing.
- **Sticks that failed to erase or format now work.** The partition table is cleared before the raw write, a refused write is retried with the disk taken offline, formatting falls back to the built-in formatter if Windows Storage refuses, and after erasing, the stick is found again by serial and keeps its drive letter. This fixes "the requested object could not be found," "Windows error 1," Format-Volume failures, and disks that change number mid-write.
- **PCs that freeze handing off to macOS (EXITBS:START).** With the stick plugged in, 1401 reads the startup logs on it and steps through the memory settings that get past the freeze — on Intel and AMD.
- **PCs with no supported graphics card build anyway.** A PC whose only card is a GTX 10, RX 7000 or Intel Arc now builds and runs macOS on the firmware's display (basic display, no graphics acceleration) instead of stopping.
- **macOS appears in the OpenCore picker** without pressing Space.
- If a step stops unexpectedly, the report now says which part of 1401 it came from, so it can be fixed faster.

Keep the whole 1401 folder together and run 1401.exe.
