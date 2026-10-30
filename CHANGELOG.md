# Changelog

Each release also bundles the NVIDIA driver and Mac app of the same version; see the
[driver changelog](https://github.com/nullmoth/nvidia-macos-driver/blob/main/CHANGELOG.md).

## 2.6.5
- Rebuilding a stick from its boot logs now reaches the kernel's boot arguments. Once one start had stored boot-args in the PC's NVRAM, OpenCore refused every later build's ("ignored, exists"), so added options such as npci=0x2000 never applied until NVRAM was reset by hand (#124, #126). When the logs show no installed macOS on an internal disk, the stick now replaces the stored boot-args; a PC that runs macOS keeps its own and is told to reset NVRAM once.
- If the screen stops inside the touchpad driver's start ("VoodooGPIO... Loading GPIO Data for AMD"), the rebuilt stick leaves the VoodooI2C touchpad stack off; the keyboard keeps working and a USB mouse drives the installer (#124).
- Two kext pairs that do the same job are never both on: USBInjectAll with USBToolBox, and IntelMausi with IntelSnowMausi. Every config in the field reports with the startup crash "element modified after free" had one of these pairs on. 1401 leaves USBInjectAll and IntelSnowMausi off when it builds, and the Mac app's EFI check flags either pair in an existing config and fixes it.
- Mac app: setup no longer picks a Windows (NTFS) partition as the OpenCore partition. An EFI folder copied onto one was chosen, and its config backup failed because macOS cannot write NTFS (nvidia-macos-driver #453).
- Mac app: a driver update can use the driver package from the 1401 download you already have, instead of downloading it again. The file must match the release's SHA-256 exactly (PR #125, thanks developforapple).
- Bundles NVIDIA driver 2.6.5.

## 2.6.4
- Writing the stick no longer stops with "this is the disk the computer booted from" on PCs whose Windows storage service lists no disks. On that route, 1401 counted the stick's own boot partition as the PC's, and 28 of 29 such writes stopped there. It now refuses the disk holding the partition Windows actually started from.
- When Apple's recovery server answers "400 Bad Request", 1401 asks again over HTTPS. If it still fails, it says what to change (antivirus web scanning, a hotspot or a VPN) instead of showing only the error.
- Mac app: if a Mac's saved kernel panic shows IntelBTPatcher crashing Bluetooth at startup ("IOGMD: not wired"), the next driver update turns that kext off. Bluetooth keeps working through IntelBluetoothFirmware. Seven Tahoe laptops had this panic, one restarting ten times in twenty minutes.
- Mac app: a **HiDPI (Retina) modes** switch. It turns on the driver's larger desktop (boot-arg nvfbhidpi=1) that "looks like" sizes above half the screen need, for example 1920 x 1080 on a 2560 x 1440 screen, including sizes added with BetterDisplay.
- Laptops with AMD Ryzen AI 300 (Strix Point) processors are offered the USB input-lag fix XhciNudge when experimental drivers are on (#121).
- Mac app: the AMD / Intel test driver leaves alone any GPU that Apple's own drivers run.
- Bundles NVIDIA driver 2.6.4.

## 2.6.3
- Mac app: Intel Xe graphics for Tiger Lake, Alder Lake and Raptor Lake on macOS 15.8 or 26.7 and later, through b00t0x's WhateverXe (thanks b00t0x). It shows only on the Intel GPUs WhateverXe supports, downloads its parts from the author's GitHub with every file checked, and **Turn it off** puts the config back as it was.
- Mac app: **Allow an app...** under Microphone and camera lets an app such as Discord use the microphone, camera and screen recording. With the driver installed macOS never asks, so those apps got silence. The method follows tccplus by Jeremy Legendre.
- Mac app: when the driver is parked by "Start once without NVIDIA driver" or -nvoff, a **Turn the driver on** button removes only that switch.
- Mac app: the AMD / Intel test driver checks SIP before it downloads anything, and skips a firmware mirror that refuses the download.
- Mac app: Macs using itlwm for Wi-Fi are told to install HeliPort, the app itlwm joins networks through.
- The boot picker's "Start once without NVIDIA driver" also starts that one time without WhateverXe.
- MediaTek RZ616 Bluetooth works: its USB ID gets the firmware entry of its family (#336).
- Bundles NVIDIA driver 2.6.3.

## 2.6.2
- When the stick does not start macOS, 1401 for Windows now says what to change, in numbered steps, before it offers to send the logs. It reads the stick's logs, the line you type for where the screen stopped, and this PC's scan, and covers: no room in memory to start (EB.MM.AKM), Secure Boot blocking OpenCore's drivers, a stick missing HfsPlus.efi, the Windows entry chosen instead of 1401, a freeze at EXITBS:START (with the settings for your CPU: VT-d on Intel, IOMMU on AMD), a stop at PCI configuration, a black screen with only a cursor after the install, a kernel panic, the prohibited sign, no macOS entry in the menu, an installer that shows no disk (AHCI, VMD) and "waiting for root device".
- EFI builds work on Windows accounts whose names are not in English: OpenCore's validator could not read the config from such a folder, and every build there stopped with "ocvalidate issues=0" (115 builds).
- On Chinese Windows, the install guide and the other pages 1401's engine writes are in Chinese too; they were in English.
- Mac app: the window moves by its title bar again (it could not be dragged in 2.6.1).
- Mac app: each issue in **Check my EFI** shows what this Mac has now and the exact value to set, for example which boot-args to add. It checks the EFI your Mac starts from, not the rules meant only for the USB stick.
- Mac app: the installed driver version is read from the driver itself when its record is missing, so it no longer offers an update you already have.
- Mac app: the copy of your config saved before a change is named `config.plist.before-1401-<date>`, so the original is easy to find.
- Bundles NVIDIA driver 2.6.2, the same driver as 2.6.0.

## 2.6.1
- A new look for 1401 on Mac and Windows: the NullMoth colours as glass panels over the site's drifting starfield, a sidebar for each part of the app, and a light/dark switch in the title bar that remembers your choice.
- Mac app: the sidebar holds This Mac, Issues (Check my EFI, with a count of what to change), Tools, USB ports and Send a report. **Mount EFI** in Tools finds the EFI partition this Mac started from, mounts it and opens it in Finder, with one password prompt.
- Bundles NVIDIA driver 2.6.1, the same driver as 2.6.0.

## 2.6.0
- Bundles NVIDIA driver 2.6.0: updating the driver takes one restart. macOS's "system extensions updated" notice no longer needs approving and a second restart.
- 12th-gen and newer Intel, Core Ultra included: the BIOS checklist tells you to turn VT-d off. It used to leave VT-d out for exactly these PCs, and turning it off is what got them past EXITBS:START (#10, #11, #53, #58). When the BIOS hides it, the checklist says where to look: the Advanced or overclocking pages, X2APIC off first on some laptops (HONOR), and Kernel DMA Protection.
- DevirtualiseMmio on 12th-gen and newer Intel follows the PC: off on laptops (1401 #6), on for Core Ultra 200 desktops, as on a Core Ultra 5 225F that runs macOS 26, and as built on other desktops. Measured over 448 of these machines in the stick reports, forcing it off everywhere did not help desktops.
- One rule file for the EFI settings 1401 builds and the Mac app checks (p1401/efi_rules.json): what each setting is, which machines need it, why, and the steps to change it by hand. Tests hold the builder and both checkers to the same answers, including over 3,465 uploaded stick configs.
- Writing the stick on Windows builds without Windows PowerShell in System32: 1401 uses a PowerShell on PATH or PowerShell 7 instead of stopping (five runs on one PC). The PC scan does the same.
- Mac app: **Check my EFI** reads the OpenCore setup your Mac starts from, without changing it, and lists anything that should change, each with the steps to change it.

## 2.5.5
- Bundles NVIDIA driver 2.5.5: Discord videos play again, Screen Sharing shows the screen, remote-desktop apps get keyframes from the hardware encoder, and Brave and Edge use the GPU.
- Fixes 2.5.4's "EFI failed validation: ocvalidate issues=1" with "Include experimental drivers": the KernReserveLow driver's description had a "~", which OpenCore refuses in a comment (#101, thanks myvoow). Every comment in the built config is now kept to the characters OpenCore accepts.
- Writing the stick on PCs where Windows' storage service lists no disks (a missing or broken Storage Management Provider): 1401 lists the disks through classic WMI, checks the stick there and erases it with diskpart, instead of stopping with DISK-LIST-EMPTY.
- Sticks that refuse the raw erase with an I/O device error (Windows error 1117) are erased with diskpart instead of stopping, as sticks refusing it with access denied already were.
- A real Windows PC is no longer taken for Wine because some other program left a Software\\Wine registry key (#99).
- Rebuilding from a failed boot: when the stick's log shows the firmware has no memory attributes table ("MAT support is 0"), the build uses the booter settings for such firmware.
- Mac app: a config backup that fails on a read-only partition whose name has a space now says why and what to do; cancelling a Tahoe preparation that was never started no longer stops with "this driver has no kexts for macOS 15"; a Mac whose driver is loaded but shows no NVIDIA Metal device is told so, with what that means on a laptop without a MUX, instead of "installed but not running" (#98, thanks CGR-MIX).

## 2.5.4
- Bundles NVIDIA driver 2.5.4: desktops whose only GPU is the NVIDIA card start instead of looping on a black screen when the card's display does not come up, Discord and sandboxed apps' video use the GPU, and clearer installer stops.
- Fixes 2.5.3's "EFI failed validation: ocvalidate issues=1": community UEFI drivers were added without the HideVerbose key OpenCore checks, so builds that included one stopped (PR #92, thanks CreateRan).
- The window fits high-DPI screens and small work areas: text wraps, the page scrolls, and nothing is cut off (PR #72, thanks rootwhois). The macOS version picker and the experimental-drivers box show only on the build page.
- The BIOS guide no longer says "Resizable BAR: Disabled - turn it On" for NVIDIA cards: the Windows scan cannot see that setting on NVIDIA, so it is no longer guessed.
- Security: certifi 2026.10.23, which drops the last two emSign root certificates (2.5.3's 2026.10.19 still carried emSign Root CA - C1 and ECC Root CA - C3).
- Writing the stick: a PC missing Windows PowerShell gets a stop that says so and how to restore it; an empty disk list records which other Windows route still sees the disks.
- Mac app: the USB map no longer redraws every second (an open plug-type list closed and plug choices reset); the first-login report names the audio controller, its layout-id and codecs; a kernel log cut off by a moved clock (dual boot) is collected again; the uninstaller removes the driver's licence texts.

## 2.5.3
- Bundles NVIDIA driver 2.5.3: `nvregdwords=` options no longer stop the startup.
- Community drivers for hardware the builder had none for, added only when the scan finds a device each one matches and
  only for the macOS its author built it for. Behind "Include experimental drivers": Realtek Wi-Fi 6/6E/7 (AirportRTW),
  MediaTek MT7921/MT7922/RZ616 with the native Wi-Fi menu on macOS 26 (AirportMtkWlan), Qualcomm WCN7850 Wi-Fi
  (AirportWCN7850), the AMD laptop USB input-lag and USB-storage fixes (XhciNudge, KernReserveLow), Lenovo's
  cloud-recovery panic fix (LegionCbmrFix) and Arrow Lake clocks and power (LegionCpuPower). Without the opt-in, for the
  hardware they match: Qualcomm WCN7850 Bluetooth (BluetoothWCN7850), the Arrow Lake touchpad controller
  (LegionI2CArrowLake) and the ITE 8258 laptop keyboard (LegionITEKbdFix). NOTICE.md credits every author.
- Every download has a recorded licence (p1401/licenses.json). The download mirror keeps copies only of what each
  licence lets NullMoth redistribute, with the source beside every GPL binary; the rest comes from its author.
- Security: the Windows package runs Python 3.13.17 (3.12 gets no more Windows security builds) with certifi
  2026.10.19, which drops the emSign certificate authorities whose keys were compromised.
- Writing the stick: when Windows returns no disks at all, 1401 says so and records why, instead of reporting a
  renumbered stick.
- The Mac app's first-login report (opt-in, sent once) says which parts of the machine came up: audio, Wi-Fi,
  Bluetooth, network, keyboard and touchpad, battery, and the drivers that loaded. No network names, addresses or
  paired devices are included.
- Mac setup: a stick's config.plist that macOS will not let 1401 read is reported as that, with where to allow it, not
  as an invalid plist.

## 2.5.2
- Bundles NVIDIA driver 2.5.2: HDMI and DisplayPort audio, a startup hold that waits for slow laptop GPU bring-up, opt-in primary-GPU selection for several NVIDIA cards, opt-in deferred flip checks for high-refresh displays, and a quieter system log.
- The Mac app's uninstaller also removes the opt-in primary-GPU selector.

## 2.5.1
- Bundles NVIDIA driver 2.5.1: Apple TV video, sRGB shader writes (Blender), scaled and HiDPI desktop modes, faster window updates and GPU temperature.

## 2.5.0
- Bundles NVIDIA driver 2.5.0, built on NVIDIA's 615.78.08 driver: NVIDIA's fixes since 610, new cards, 12-bit HDMI deep colour and NVIDIA's driver options.
- The NVIDIA T-series workstation cards (T400, T500, T550, T600, T1000, T1200) and the second RTX 5070 device ID are recognised as supported.

## 2.4.4
- Bundles NVIDIA driver 2.4.4: hardware video encode on every GTX 16 card, HEVC past the second frame on GTX 16 and RTX 20,
  and no more app freezes after a missing GPU completion mark (#322).
- The first-login report sends the driver logs when the kernel is still running an older driver than the one installed.
- The first-login report no longer says the driver did not come up on laptops whose NVIDIA card drives no screen: it
  waits for the driver's own check, which gives those cards their Metal device a minute after start-up.
- Mac setup no longer turns off the NVIDIA hardware video encoder on GTX 16, RTX 20 and RTX 30 cards. A rule from before
  those cards had encoders kept them on Apple's software encoder; updating clears it.
- Writing the stick no longer stops on every try with "The scan changed after the EFI was built": 1401 builds the startup
  files again for the current check of the PC, then asks for the stick again.

## 2.4.3
- Bundles NVIDIA driver 2.4.3, which fixes a desktop freeze followed by a kernel panic shortly after logging in.

## 2.4.2
- Bundles NVIDIA driver 2.4.2, which fixes the black screen and the startup that stops on the verbose text after
  updating to the 2.4 or 2.4.1 driver.

## 2.4.1
- Bundles NVIDIA driver 2.4.1, which fixes the black screen after updating to the 2.4 driver, along with everything
  2.4 brought: hardware H.264 and HEVC encode on RTX 20 and RTX 30 cards, macOS 26 icons and glass panels, the stale
  shader cache cleared after an update, and the power source reported to the GPU on laptops

## 2.4
- Bundles NVIDIA driver 2.4: hardware H.264 and HEVC encode on RTX 20 and RTX 30 cards (it was RTX 50 only), picked
  automatically for each card; hardening against malformed input from apps; macOS 26 icons and glass panels draw again;
  a stale shader cache no longer leaves the login screen black after an update; the driver tells the GPU whether a
  laptop is on battery or mains power
- Mac: installs from a root-owned copy of the package and keeps the previous driver as an automatic fallback

## 2.3.6
- Bundles NVIDIA driver 2.3.6: smoother window dragging and cursor movement, OpenGL apps pace to the display's refresh
  rate, faster OpenGL (Minecraft), Chrome uses the GPU, Dock badges and text masks draw correctly, and Metal reports the
  card's whole video memory

## 2.3.5
- Bundles NVIDIA driver 2.3.5: the login screen no longer stays black for a minute after the display comes up

## 2.3.4
- Bundles NVIDIA driver 2.3.4 (pre-release to the early-updates program first; see its changelog)
- Mac: the first-login report names the kernel driver version the Mac is actually running next to the one installed
  on disk, and says STALE when they differ. A Mac that kept running an older kernel driver after an update used to
  report the new version
- Mac: hybrid laptops with WhateverGreen next to the driver get the boot argument it needs (gfxrst=4), so the boot
  screen is not copied from memory the other card has released

## 2.3.3
- Bundles NVIDIA driver 2.3.3: the 2.3.1 driver on both macOS 15 and 26, installable on Sequoia; the 2.3.2 display
  changes that made some Macs worse are withdrawn until they pass a staged test (see its changelog)
- Mac: the app can update itself again ("signature could not be downloaded" was a deadlock in the app, not the server)
- Mac: the first-login report carries the installed component hashes and each display's refresh rate, and attaches the
  driver logs when the driver did not come up
- Send logs: every query has its own time limit, so a slow Mac no longer loses the log it was sending

## 2.3.2
- Checking a PC no longer fails when Python is installed on it: 1401's own Python ignores the PC's Python packages
  ("certifi has no attribute where", "win32com ... __gen_path__")
- Under Wine, 1401 stops at once and says it needs real Windows, instead of failing three times to read the hardware
- A PC that can only run up to macOS Sequoia stops with that answer when Tahoe was picked, instead of looping on the
  macOS version question
- If something on the PC rewrites OpenCore's boot files after the build (security software), 1401 writes them back
  from the verified release and says what changed them
- After a BIOS change (for example turning VMD off), 1401 checks the PC again instead of using the old scan
- A DSDT the ACPI compiler cannot read now travels in the build log, so it can be repaired
- Mac: Send logs no longer times out on a broken GPU stack (every query has its own time limit); it also includes
  how much video memory the driver uses
- Bundles NVIDIA driver 2.3.2: installing and updating on macOS Sequoia works again, and screenshots and the lock
  screen show windows again (see its changelog)

## 2.3.1
- Writing the installer stick: on PCs where Windows' storage service lists no disks at all (the write stopped with
  1401-DISK-RENUMBERED, or the stick list said "Invalid class"), 1401 repairs the service itself and lists the disks
  again. It also uses 64-bit PowerShell and logs PowerShell's own error
- Bundles NVIDIA driver 2.3.1: a driver update that cannot bring the display up falls back to the previous driver
  automatically (see its changelog)

## 2.3.0
- Mac: after a successful install, 1401 can confirm once that the Mac reached its desktop (you choose; the default
  is not to send). It sends one small summary at the first login, then removes itself, so a working install can be
  told apart from one that failed silently
- Writing the installer stick: when Get-Disk lists no disks at all, 1401 reads them through Windows' storage WMI
  instead of stopping
- When Windows' storage management is missing or damaged, the USB stick list names the repair instead of only
  "Invalid class"
- Mac: the AMD and Intel GPU test program. Join from the AMD/Intel panel to get the newest signed test build; after
  each restart 1401 sends what the AMD/Intel driver did. Leave from the same panel
- Bundles NVIDIA driver 2.3.0 (see its changelog)

## 2.2.0
- Writing the installer stick: when Windows gives the stick a new disk number after it was picked, 1401 finds the
  same stick again and keeps going (it used to stop with 1401-DISK-RENUMBERED); a different disk that took the old
  number is never written
- The Mac app is part of 1401 now. It installs the NVIDIA driver with that package's own installer, and the AMD/Intel
  test driver comes from its own package
- Bundles NVIDIA driver 2.2.0 (the NVIDIA driver only: no boot logo, no background jobs; see its changelog)

## 2.1.0
- When Windows refuses to start PowerShell, 1401 retries once and the log says why it was refused
- Bundles driver and Mac app 2.1.0 (per-generation GPU support, Blender Eevee lighting, desktop no longer waits
  on every frame, Map my GPU)

## 2.0.4
- When the stick's disk number is gone at write time, the log now lists the USB disks Windows shows, so the cause
  can be found
- Bundles driver and Mac app 2.0.4 (Prepare this Mac for Tahoe is back; the AMD / Intel test driver turns on for an
  Intel or AMD GPU switched off in OpenCore)

## 2.0.3
- When Windows gives the stick a new disk number after you pick it, 1401 says so and reloads the list, instead of
  stopping with "the USB stick stopped accepting writes" on every retry
- A volume on the stick that Windows removes while the erase starts no longer stops the write
- When Apple's download server keeps cutting the connection, the stop says what to change on your network
- Intel PCs (12th gen and newer) that stop at EB.MM.AKM because no kernel slide fit: rebuilding with the stick plugged
  in reads its startup log and turns on DevirtualiseMmio for the next start
- Bundle driver 2.0.3: the driver saves and restores the GPU across system sleep, diagnostic sysctls are gone from
  normal builds, and the Mac app explains a hidden NVIDIA card, lets AMD/Intel-only Macs try the test GPU driver, and
  adds an opt-in laptop brightness switch

## 2.0.2
- A PC with no network adapter that works in the macOS installer gets its stick written, with a note to connect a
  supported Ethernet or Wi-Fi adapter before installing. 2.0.0 stopped the write and asked for a recovery image that
  would not have helped
- A stick that Windows gives a new disk number just before the erase is found again and written
- Bundle driver 2.0.2 (the same driver as 2.0.0)

## 2.0.1
- PCs with an NVIDIA card can build for macOS 26 Tahoe. 2.0.0 offered only macOS 15 for them, so picking
  Tahoe stopped the build
- Bundle driver 2.0.1 (the same driver as 2.0.0)

## 2.0.0
- Pick macOS 15 Sequoia or macOS 26 Tahoe before the build
- Bundle driver 2.0.0 (security fixes, GeForce RTX 50 compute, flicker, refresh-rate and black-screen fixes)
- Tahoe boots and updates on PC models Apple did not ship it for, and boards with a Realtek 2.5G/5G port and Intel or
  Broadcom Wi-Fi no longer stop at the Apple logo
- Hybrid-core Intel PCs that stopped at EXITBS:START boot, and Intel PCs that froze with "No slide values are usable"
  get the matching memory-map setting
- Every AMD graphics card is identified, with what macOS can do on it shown in the build summary
- Experimental drivers are off unless you tick "Include experimental drivers": the AMD RX 9070 display driver and the
  MediaTek MT7921/MT7922 Wi-Fi driver. With it off, the build says which one your PC could use
- MediaTek Bluetooth works on the OEM versions people have; PCs with no supported network adapter get the offline
  installer by default
- NVMe drives macOS cannot install to are named before you start
- A rebuild for the same PC keeps its serial number, board serial, UUID and ROM; ask for a new one if macOS Setup
  says the Mac belongs to an organization
- A PC with a NullMoth-driver card is built for macOS 15 even when the engine suggests Ventura
- A build that stopped in the EFI step no longer locks out every later build
- Apple download errors (403, 502, cut-off downloads, a bad chunk) are retried where they can be and explained where
  they cannot
- USB stick writing: sticks Windows could not format are erased with diskpart, a renumbered stick is found again, and
  files that read back wrong are written again
- The Remove NVIDIA driver startup entry stays visible in the boot picker

## 1.15.0
- Fix the build stopping on ACPI tables that declare a method twice (BIOSTAR B650 and similar)
- Bundle driver 1.15.0 (fixes the GTX 16 black screen that started in 1.14)

## 1.14.7
- Leave the optional boot logo off in new builds

## 1.14.6
- Retry Apple recovery downloads that return HTTP 403

## 1.14.3
- Check for a newer version of 1401 at start-up
- Let Windows pick any free drive letter for the stick
- Retry downloads when Apple's server keeps answering 502
- Wait for antivirus to release the OpenCore validator before erasing

## 1.14.2
- Fix an empty "UsbError:" on Windows set to Chinese and other languages
- Fix "IsADirectoryError" when the stick is not ready
- Fix "'NoneType' object has no attribute 'headers'" while downloading macOS

## 1.14.0
- Work with Windows Smart App Control
- Fix "OCB: DMG has been altered" from sticks that don't keep what is written
- Prepare desktops for macOS 26
- Fix the build stopping when Windows reports a graphics card without a PCI ID

## 1.13.0
- Fix Turing cards stuck at start-up
- Fix "Remove NVIDIA driver" hanging in the boot picker

## 1.12.0
- Keep the Intel GPU on for laptop panels macOS has no driver for
- Name the files that changed when an EFI no longer matches its machine profile

## 1.11.0
- Include Lilu and AMFIPass for supported NVIDIA cards
- Read the stick's last startup log on the next build
- Fix the build failing on laptops with Iris Xe

## 1.10.0
- Use the memory settings AM5 Ryzen CPUs boot with on the first build
- Drop the DMAR table on Intel Core Ultra
- Apply the CFG-lock fix only when the log shows it is needed

## 1.9.0
- Try one more memory setting on AM5 boards
- Erase stubborn sticks with diskpart

## 1.8.0
- Use known-good settings for boards that have booted before
- Fix "Format-Volume: Invalid property" and "WinError 2" when erasing

## 1.7.0
- Pass the board's DSDT to macOS again (was dropped on about 1 in 5 PCs)
- Keep writing when Windows re-mounts the stick mid-download

## 1.6.0
- Build an EFI from a Linux USB probe report
- Accept sticks whose serial number changes on every read
- Wait out longer network stalls during the macOS download

## 1.5.0
- Finish the macOS download on networks that cut connections

## 1.4.0
- Build on PCs whose ACPI tables crash the disassembler
- Accept partial hardware scans

## 1.3.0
- Resume downloads from the last byte
- Reuse a stick that already has macOS or Windows on it
- Step through boot fixes for PCs that freeze at EXITBS:START

## 1.0.x
First public releases.
