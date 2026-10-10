# 1401 1.10.0 for Windows

**Something not working? [nullmothsystems.com/help](https://nullmothsystems.com/help) lists every known problem and exactly what to do.**

## Boot
- Ryzen 7000, 8000 and 9000 PCs (AM5 and Zen 4/5 laptops): the first build uses the memory settings these CPUs boot with, instead of stopping at the prohibited sign / `EB.MM.AKM`. Build the stick again with 1.10.
- A board that reports no usable memory slide gets the memory whitelist turned off and both memory settings on.
- Intel Core Ultra: VT-d's DMAR table is dropped for macOS, which every Core Ultra that booted needed.
- The CFG-lock fix is applied only when a real power-management panic is in the log.

## Writing the stick
- When the network's DNS fails or refuses Apple's recovery server, 1401 reaches Apple's own server directly.
- A download that keeps stalling says what each connection did and what to try (antivirus web scanning off, a phone hotspot, or a VPN).
- When the USB stick itself fails or disconnects during the write, 1401 says so and what to do (another port or another stick).
- The driver package is always the one this version was built with, and a download that comes up short is fetched again.

## Scope
macOS 15 Sequoia. Builds OpenCore.
