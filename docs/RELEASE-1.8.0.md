# 1401 1.8.0 for Windows

Includes the Mac app and NVIDIA driver 1.8.0 ([release notes](https://github.com/nullmoth/nvidia-macos-driver/releases/tag/v1.8.0)).
**Something not working? [nullmothsystems.com/help](https://nullmothsystems.com/help) lists every known problem and exactly what to do.**

Changes
- **Machines we've already solved build right the first time.** When your board and CPU match a machine whose own boots showed what it needs, 1401 builds with those settings straight away instead of waiting for a failed start and a rebuild. The list grows as people report what works.
- **"Format-Volume: Invalid property" / "format.com: Required parameter missing" fixed.** When Windows had not given the new stick a drive letter yet, 1401 read Windows' empty-letter marker as a letter and formatted nothing. It now waits for a real letter.
- **"FileNotFoundError: [WinError 2]" at the erase step fixed.** 1401 now starts Windows' own PowerShell and diskpart by their full path, so a PC with a changed PATH still writes.
- **Sticks that refuse direct writes ("Windows error 5") are erased with Windows' own diskpart instead of stopping.**
- Apple's recovery server answering 502 or timing out is retried longer before giving up.
- Everything from 1.7, 1.6, 1.5, 1.4 and 1.3 still applies.

Keep the whole 1401 folder together and run 1401.exe.
