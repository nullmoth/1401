# 1401 1.5.0 for Windows

Includes the Mac app and NVIDIA driver 1.5.0 ([release notes](https://github.com/nullmoth/nvidia-macos-driver/releases/tag/v1.5.0)).
**Something not working? [nullmothsystems.com/help](https://nullmothsystems.com/help) lists every known problem and exactly what to do.**

Changes
- **The macOS download finishes on networks that cut it off.** Where the first connection got exactly 1 MB and every retry got nothing ("after 9 resumed connections, 8 in a row with no progress"), 1401 now fetches the image in small pieces that get under the limit, backs off between failed tries, and checks every piece against Apple's signed list.
- Everything from 1.4 and 1.3 still applies.

Keep the whole 1401 folder together and run 1401.exe.
