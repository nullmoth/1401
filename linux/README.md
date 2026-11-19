# 1401 on Linux

The Linux window does the same four steps as the Windows app: Check this PC, Build the Mac setup, Your BIOS steps, and
Create the macOS stick. It is GTK 4 on top of the same Python engine, so the rules, downloads and checks are the ones
described in `docs/HOW-IT-WORKS.md`, not a second implementation.

The Linux app is newer than the Windows one. The engine steps are tested, but the window and the stick writer have not
been through as many real installs. Treat the first stick you write as a test.

## Packages

Debian and Ubuntu:

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 policykit-1 dosfstools exfatprogs
```

Fedora:

```bash
sudo dnf install python3-gobject gtk4 polkit dosfstools exfatprogs
```

Arch:

```bash
sudo pacman -S python-gobject gtk4 polkit dosfstools exfatprogs
```

`util-linux`, `systemd` and `pciutils` are already part of a normal desktop install and provide `lsblk`, `mount`,
`udevadm`, `lspci` and `blockdev`. `exfatprogs` is only needed for the optional full installer; without it the online
installer still works. `partprobe` from `parted` is used when present, and skipped otherwise.

The window runs as your user. Two steps ask policykit for root:

- the hardware check reads `/sys/firmware/acpi/tables`, which only root may open;
- writing the stick erases the disk, formats it and mounts it.

`pkexec` shows the usual password dialog. The app never runs the whole window as root.

## Running it

From the checkout:

```bash
python3 linux/1401.py
```

or `linux/1401`. To make a folder that can be moved out of the checkout:

```bash
bash linux/build.sh              # writes dist/1401-linux
dist/1401-linux/1401
```

The build runs the writer tests and a window self-test first, then copies the engine, `upstream/`, `vendor/` and the
window. It does not download OpenCore; the first build does that, into the copy's `upstream/` folder.

`dist/1401-linux/1401.desktop` points at the staged launcher. Copy it to `~/.local/share/applications` if you want a
menu entry.

## What it writes

The stick gets a new MBR with a FAT32 partition labelled `1401`, the OpenCore EFI, and Apple's recovery image under
`com.apple.recovery.boot/`. The image is downloaded from Apple after the stick is erased and checked chunk by chunk
against Apple's signed chunklist. The EFI is copied and read back.

The full installer option needs a stick of 32 GB or more and a download of Apple's `InstallAssistant.pkg`. The package
is checked with `xar` before anything is written, then unpacked onto a second exFAT partition labelled `NMINSTALL`.
Without the option, macOS downloads the rest itself after the installer starts.

Only USB disks are offered. A disk with `/`, `/boot`, `/home` or another system directory mounted on it is refused by
both the window and the writer, and a disk still held open by LUKS, LVM or RAID is refused until that layer is closed.
The writer looks the stick up again by serial, size and model before erasing it, so a stick that came back as
`/dev/sdc` cannot be confused with another disk. A stick that holds an APFS, HFS+, Windows recovery or Linux partition
is reported before it is erased; the window asks once more.

The NVIDIA driver packages are downloaded by the user's process before the elevated write, so the build folder does not
end up with root-owned files.

## Where things are kept

- scans, the built EFI and the BIOS page: `$XDG_STATE_HOME/nullmoth/1401/` (usually `~/.local/state/nullmoth/1401`);
- a recovery image you picked by hand: `$XDG_DATA_HOME/nullmoth/1401/Recovery/` (usually
  `~/.local/share/nullmoth/1401/Recovery`);
- the log: `$XDG_STATE_HOME/nullmoth/1401/1401.log`, also shown in the window.

Nothing is uploaded. The Linux window has no log-upload step; the log and the scan folder stay on this PC.

## Tests

```bash
python3 -m unittest tests.test_linux_usb tests.test_linux_root
python3 linux/1401.py --selftest       # needs a display; builds every page and exits
python3 -m unittest discover -s tests -t . -p 'test_*.py'
```

The writer tests use fake `lsblk` output and a fake ACPI tree. They never touch a disk.
