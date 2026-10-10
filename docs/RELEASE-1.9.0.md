# 1401 1.9.0 for Windows

Includes the Mac app and NVIDIA driver 1.9.0 ([release notes](https://github.com/nullmoth/nvidia-macos-driver/releases/tag/v1.9.0)).
**Something not working? [nullmothsystems.com/help](https://nullmothsystems.com/help) lists every known problem and exactly what to do.**

Changes
- **Ryzen (AM5) boards stuck at the prohibited sign / `EB.MM.AKM` get one more setting to try.** After every memory-map step had failed, 1401 used to go back to the default. It now tries DevirtualiseMmio on with SetupVirtualMap off first, the combination a Ryzen 5 7600 owner reached the desktop with. Rebuild from the stick's log (Send logs, then build again) to get it.
- **Sticks that refuse direct writes ("Windows error 5") are erased with Windows' own diskpart instead of stopping.**
- **"The stick was erased but Windows did not show its new partition"**: 1401 now erases it with diskpart and looks again.
- Apple's recovery server answering 502, timing out or resetting the connection is retried longer.
- Everything from 1.8 and earlier still applies.

Keep the whole 1401 folder together and run 1401.exe.
