# 1401 1.14.3 for Windows

**Something not working? [Why a machine does not work, and how to fix it](TROUBLESHOOTING.md) lists every known problem.**

Bundles the NVIDIA driver and Mac app 1.14.3.

## New
- **1401 checks for a newer version when it opens.** Most failed installers reported on 10-12 came from old versions of
  1401 whose problems were already fixed. When a newer 1401 is out, it updates itself (one click) before it builds or
  writes anything. Without internet nothing is blocked.

## Fixed
- **"Windows would not give the stick a drive letter."** 1401 now lets Windows choose any free letter, and then tries
  diskpart, before it gives up.
- **"HTTP Error 502: Bad Gateway" while downloading macOS.** When Apple's download server keeps answering 502, 1401
  asks a different Apple server.
- **"PermissionError: Access is denied" before erasing the stick.** Antivirus holds the OpenCore validator while it
  scans it; 1401 now waits a few seconds for it.

## Scope
Windows 10/11, 64-bit. Builds macOS 15 Sequoia installers with OpenCore.
