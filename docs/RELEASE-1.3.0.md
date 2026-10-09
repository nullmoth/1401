# 1401 1.3.0 for Windows

Includes the Mac app and NVIDIA driver 1.3.0 ([release notes](https://github.com/nullmoth/nvidia-macos-driver/releases/tag/v1.3.0)).
**Something not working? [nullmothsystems.com/help](https://nullmothsystems.com/help) lists every known problem and exactly what to do.**

Changes
- **Apple downloads finish on networks that cut connections.** Some networks close every download connection after 1 MB; 1401 now keeps what arrived and continues from that byte (1.2.0 restarted the 10 MB chunk and stopped with "stream ended at 1048576/10485760").
- **Reuse a stick that has macOS on it.** A stick holding an old macOS installer (HFS+/APFS) was refused; 1401 now names what is on it and asks before erasing.
- **AMD PCs stuck at EXITBS:START.** Send logs with the stick plugged in and type EXITBS:START as the last line; the next build uses DevirtualiseMmio, SetupVirtualMap and EnableWriteUnprotector on, RebuildAppleMemoryMap and SyncRuntimePermissions off (what got a Ryzen 5 5500 / B550 to the installer).
- **A failed start's log reaches the next build.** If the stick is plugged in only when you write it, 1401 reads its startup log first, rebuilds with it, then writes.

Keep the whole 1401 folder together and run 1401.exe.
