# 1401 1.13.0 for Windows

**Something not working? [nullmothsystems.com/help](https://nullmothsystems.com/help) lists every known problem and exactly what to do.**

Bundles the NVIDIA driver and Mac app 1.13.0. What was wrong and what changed:

- **GTX 16 / RTX 20 (Turing) stuck at startup.** The driver waited only half a second for the card's firmware to settle before turning the display on; some GTX 1650/1660 and RTX 2070 machines stopped at boot. The Mac app now gives Turing cards ten seconds (`nvrmsettle=10000`), keeping any value you set yourself.
- **"Remove NVIDIA driver" in the boot picker hung or closed at once.** Its question ran in graphics mode and never appeared, or the Enter that started it was read as "no". It now runs in text mode and ignores keys typed before it asks; when the removal runs at the next start it also finds the OpenCore partition the Mac started from.
- **Crash reports** now date each crash and mark the ones from before the current driver install.

## If you saw these before
- `EB.MM.AKM` / prohibited sign on Ryzen 7000/9000: build the stick again; restarting an old stick changes nothing.
- The recovery download stops at 1 MB or times out: something on the network (often antivirus web scanning) cuts Apple's download. Turn off web scanning, or use a phone hotspot or VPN.

## Still open
- HDMI and DisplayPort audio from the NVIDIA card (in progress).
- macOS installer freezing at "19 minutes remaining" on some AMD PCs: send a photo of a verbose boot and your NVMe drive model.

## Scope
Windows 10/11, 64-bit. Builds macOS 15 Sequoia installers with OpenCore.
