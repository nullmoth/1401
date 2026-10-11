# 1401 1.11.0 for Windows

**Something not working? [nullmothsystems.com/help](https://nullmothsystems.com/help) lists every known problem and exactly what to do.**

## NVIDIA driver
- Builds for a supported NVIDIA card include Lilu and AMFIPass. Without them the driver's Mac setup stopped and asked for a rebuild that still lacked them.
- The driver's boot arguments include `ipc_control_port_options=0`, so Firefox opens.

## Boot
- PCs stuck at the prohibited sign / `EB.MM.AKM`: a build after **Send logs** now reads the stick's last startup log (sending moves it into `NullMoth\sent-logs`, and the build used to miss it). Sending a log that stopped there tells you to build again. Starting an old stick again changes nothing: build it again with 1.11.
- Laptops with an Intel Iris Xe that macOS cannot drive no longer fail the build.

## Logs
- A stick whose OpenCore EFI was not built by 1401 is named as the problem when its logs are sent; a config edited after the build is noted.
- A failed stick write shows the real error instead of an internal one.

## Scope
macOS 15 Sequoia. Requires OpenCore.
