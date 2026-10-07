# 1401 - reverse Boot Camp

Boot Camp Assistant runs on a Mac and puts Windows beside macOS. **1401 runs on a Windows PC and puts macOS on it.**
The person installs one Windows app and clicks through it. They never see a config file, a kext list, or a boot argument.
1401 targets PCs; Macs on older macOS are not a target.

## The flow

```
On Windows (1401.exe)                                   On the PC, from the stick
---------------------                                   -------------------------
1. scan the hardware (local, nothing uploaded)          5. PC firmware (UEFI) boots the stick
   -> verdict: which macOS, what works, what doesn't        -> 1401 loader  <- replaces OpenCore
2. build this machine's EFI: kexts, SSDTs, SMBIOS           - the Mac-firmware role (SMBIOS, ACPI, NVRAM,
3. the GUIDE, written for this exact machine                  Apple protocols, memory map, kexts)
   - Windows traps first: BitLocker key + pause,           - Apple's recovery from the stick
     RAID->AHCI via safe mode, Legacy->UEFI (MBR2GPT)     6. Apple's installer: erase the chosen disk, install
   - BIOS: only the settings this board needs,          7. after install: 1401 copies the EFI to the disk,
     with the board's own keys; "Open BIOS" button         so the stick is no longer needed
4. write the USB stick: GPT, FAT32, loader + EFI +
   Apple's recovery, straight from Apple
```

- **The USB stick is the install path.** Everything the PC needs to boot macOS goes on the stick, which 1401 writes
  from Windows (`p1401/usbwriter.py`; it refuses anything that isn't a removable USB stick). Windows' own disk is not
  touched by 1401.
- **The guide is part of the product, not a readme** (`p1401/guide.py`). It is built from the scan and from the EFI
  1401 actually built: a setting the EFI already works around (CFG Lock, VT-d, Above 4G via `npci`) is marked
  skip-if-missing, never "must". Every BIOS change risks Windows, so TPM/PTT and SGX are never touched.
- **macOS comes from Apple.** Apple's servers send it to the person's own stick, and every chunk is checked against
  Apple's signature (`p1401/apple.py`, done and tested).

## Why not OpenCore

OpenCore is excellent, and it is what 1401 measures itself against. But it is a toolkit: roughly 300 options and one
plist, and one wrong key means a black screen. 1401's loader takes no options. Everything it needs comes from the scan
that ran on the same machine, and 1401 writes it on the Windows side. Every rule that makes a decision is named and
tested. OpenCore stays in the repo as the **reference implementation**: for each milestone, the same VM is
booted with OpenCore and with 1401, and the two have to agree.

## Milestones

| # | What | Proof |
|---|---|---|
| **M0** (done) | Loader boots on real UEFI firmware, finds OSes on every disk, chain-loads by real device path, ranks macOS over Windows | `tests/loader_qemu.py` 5/5 on OVMF: probe, Windows on a 2nd disk, macOS outranks Windows, and 2 negative tests (no OS -> no chain-load; empty ESP -> no banner) |
| **M1** (done) | **APFS jumpstart**: read the container superblock's EFI jumpstart, verify Apple's Fletcher-64 checksums, load `apfs.efi` **from the person's own disk**, reconnect so APFS volumes appear (`loader/src/apfs.rs`) | 9/9 on OVMF. Apple's `apfs_efi_osx-2811.160.7.0.4` (745,080 bytes, extracted read-only from an installed Intel Mac's container) is loaded from the container, mounts it, and the scan finds `boot.efi` on APFS. Controls: a flipped superblock bit and a flipped jumpstart bit are each refused. The fixture is built by `tests/make_apfs_fixture.py` and kept in `~/.cache/1401`, because it contains Apple's code |
| M1b | **Boot Apple's recovery from the stick**: UDIF `BaseSystem.dmg`, verified against its chunklist, mounted as a RAM disk, plus a read-only reader for its filesystem (HFS+ per Dortania; not yet confirmed) | Tahoe recovery's `boot.efi` found and started in QEMU; control: a tampered chunk is refused |
| M2 | Picker: text menu, default + timeout, remembered choice in 1401's own NVRAM variable | QEMU keystroke injection; Windows Boot Manager chain-loaded from a real Windows ESP |
| M3 | Mac-firmware role for `boot.efi`: SMBIOS (Mac model tables), NVRAM (`csr-active-config`, `boot-args`), the Apple protocols `boot.efi` looks up, memory-map fixes | macOS recovery reaches its installer in QEMU+HVF on the Intel machines, differential against OpenCore on the same VM |
| M4 | Kext injection into the boot kernel collection + ACPI (SSDTs from the scan) | macOS installs and boots in the VM; then on real hardware from the corpus |
| M5 | Windows flow: the per-machine guide (`p1401/guide.py`, 25/25 over the corpus), BitLocker key + suspend, "Open BIOS" (`shutdown /r /fw`), stick writer, "Restart to the stick" | a Windows VM (eval ISO) under QEMU+HVF on an Intel Mac; controls: a fixed disk is refused, BitLocker-on without a saved key refuses |
| M6 | After install: copy the EFI from the stick to the macOS disk's ESP; macOS agent + auto-update after each macOS release | the VM boots with the stick removed; a staged update applied and rolled back |

**Test rigs.** An Apple-silicon laptop runs OVMF under TCG, which is plenty for M0-M2. M3-M6 need macOS and Windows
guests at full speed, so they run under QEMU+HVF on Intel Macs.

## Secure Boot

Microsoft will not sign GPLv3 code (its UEFI CA policy names GRUB 2). So 1401 takes the path every Linux distribution
takes: a Microsoft-signed **shim** (BSD) loads the GPL-3 loader. The loader is signed with 1401's own key, which the
person enrolls once through MokManager, the same route Ventoy uses. After that, the loader starts Apple's `boot.efi`
and `apfs.efi` with its own PE loader, checking Apple's signatures (M3), because the firmware's `LoadImage` would refuse
binaries Microsoft didn't sign. Until then, Secure Boot has to be off. The Windows app detects that
(`Confirm-SecureBootUEFI`) and says what it costs: some Windows anti-cheat games require Secure Boot on.

## Legal lines (not negotiable)

- 1401 ships **no Apple code and no Apple keys**. Apple Internet Recovery provides the installer. The person's own macOS
  install provides `apfs.efi`, from their disk at boot.
- **The SMC's `OSK0`/`OSK1` key is never embedded.** That key is what Apple v. Psystar turned on under the DMCA's
  section 1201. How M3 answers `OSK` queries without shipping the key is an **open design decision** and has to be settled
  before M3 ships.
- 1401 is **GPL-3.0-or-later**. Everything it builds on keeps its own license (`NOTICE.md`).
