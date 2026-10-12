# 1401 1.14.2 for Windows

**Something not working? [Why a machine does not work, and how to fix it](TROUBLESHOOTING.md) lists every known problem.**

Bundles the NVIDIA driver and Mac app 1.14.2 (black login window on fast monitors, Tahoe preparation on more EFIs, fewer
app crashes; their notes list the details).

## Fixed
- **Writing the stick stopped with an empty "UsbError:"** on Windows set to Chinese and other non-English languages.
  Windows' disk tools answer in the system's own text encoding, and 1401 could not read it. It can now.
- **"IsADirectoryError" while checking the stick.** That was Windows error 21, "the device is not ready": the stick
  stopped answering while 1401 read it back. 1401 now says that. Replug the stick, or use another one.
- **"'NoneType' object has no attribute 'headers'"** while downloading macOS. A network that needed a second route on
  the last try stopped the download with this message instead of trying that route. It now gets its own try.

## Scope
Windows 10/11, 64-bit. Builds macOS 15 Sequoia installers with OpenCore.
