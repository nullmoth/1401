# 1401 1.12.0 for Windows

**Something not working? [nullmothsystems.com/help](https://nullmothsystems.com/help) lists every known problem and exactly what to do.**

- Dual GPU laptops: the NVIDIA GPU now works when the screen is wired to the Intel GPU, as a second Metal device for apps (as on Apple's two-GPU MacBook Pros). Laptops with 6th-10th generation or Ice Lake Intel graphics get both GPUs accelerated. New in 1.12: if the NVIDIA GPU does not appear in macOS, press Send logs in the Mac app.
- Bundles the NVIDIA driver and Mac app 1.12.0: a display tracker that records flicker and black screens from every boot (Send logs uploads it), Live Text no longer crashes, the first WebGL fix, and old setup logs are no longer re-sent.
- Laptops whose built-in panel runs on an Intel GPU macOS has no driver for keep that GPU on, so the panel shows macOS.
- "The EFI changed after its machine profile was recorded" now names the files that changed, and says to allow the 1401 folder in your antivirus if it removed one.
- A **Buy me a coffee** link sits beside Scan for logs.

## If you saw these before
- `EB.MM.AKM` / prohibited sign on Ryzen 7000/9000: build the stick again; restarting an old stick changes nothing.
- The recovery download stops at 1 MB: something on the network (often antivirus web scanning) cuts Apple's download. Turn off web scanning, or use a phone hotspot or VPN.

## Still open
- macOS installer freezing at "19 minutes remaining" on some AMD PCs: send a photo of a verbose boot and your NVMe drive model.
- Acceleration for the screen itself on 11th-generation and newer Intel and on AMD integrated graphics.

## Scope
Windows 10/11, 64-bit. Builds macOS 15 Sequoia installers with OpenCore.
