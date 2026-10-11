# 1401 1.14.0 for Windows

**Something not working? [Why a machine does not work, and how to fix it](TROUBLESHOOTING.md) lists every known problem.**

Bundles the NVIDIA driver and Mac app 1.14.0 (their notes list the driver fixes). What was wrong in 1401, and what changed:

- **Windows Smart App Control stopped the build** ("ValidatorUnavailable: Windows application control blocked …", 8 PCs).
  1401 now checks the config against OpenCore's own sample config when Windows will not run OpenCore's validator.
- **"OCB: DMG has been altered" / "LoadImage failed" at start-up.** The stick did not keep the macOS image it was given.
  1401 now reads the image back from the stick after writing and stops with what to do if the stick changed it.
- **"This version of Mac OS X is not supported on this platform!" after moving to macOS 26.** Desktops with a graphics
  card were built as iMacPro1,1, which macOS 26 refuses. They are built as MacPro7,1 now, which runs macOS 15 and 26.
  *Check your EFI* also names a Mac model Apple's installer refuses.
- **"The only graphics card Windows reports is 'NVIDIA GeForce GT 730', with no maker or PCI ID"** stopped the build.
  The maker is now read from the card's name and the build goes on with basic display.
- **"engine download history names no OpenCorePkg"** stopped the build. A reused OpenCore download is now matched
  against the hashes Dortania publishes.
- **The macOS install froze about 19 minutes in on Ryzen 7000/8000/9000 PCs** (#30; X870 and B850 boards). The installer
  writes firmware settings at that point, and these boards hang on it. 1401 now builds them with OpenCore's
  DisableVariableWrite on, which a 9800X3D owner confirmed lets the install finish. Make the stick again with 1.14.
- **"HTTP Error 502: Bad Gateway" from osrecovery.apple.com.** A proxy on some networks breaks plain HTTP to Apple's
  recovery service. 1401 now asks it over HTTPS when that happens; the image is still checked against Apple's signed list.
- **The NullMoth boot logo** is in every EFI 1401 builds, on by default (Mac app → Boot logo off).
- **1401 updates itself**: *Update 1401 (this app)* downloads the newest version, checks it, and replaces itself.
- **The hardware capture** records the installed Windows driver of every graphics adapter, any brand.

## Scope
Windows 10/11, 64-bit. Builds macOS 15 Sequoia installers with OpenCore.
