# NOTICE - what 1401 is built on

1401 is free, forever: **PolyForm Noncommercial 1.0.0** (`LICENSE`), never for sale. It stands on work other people
gave away, and every piece keeps its own license and credit below.

## Loader dependencies (Rust crates, compiled into `loader1401.efi`, from `loader/Cargo.lock`)

| Crate | License |
|---|---|
| `uefi`, `uefi-raw`, `uefi-macros`, `uguid`, `log`, `bitflags`, `cfg-if`, `bit_field` | MIT or Apache-2.0 |
| `ptr_meta` | MIT |
| `ucs2` | MPL-2.0 |
| build-time only: `syn`, `quote`, `proc-macro2`, `unicode-ident` | MIT or Apache-2.0 (+ Unicode-3.0) |

Test-only, never shipped: QEMU and its EDK2/OVMF firmware (`tests/loader_qemu.py`).

## Vendored source (in `upstream/`, pinned in `upstream/PINNED.json`, unmodified)

| Component | Author | License | Role in 1401 |
|---|---|---|---|
| OpCore Simplify | lzhoang2801 (LICENSE: "Copyright (c) 2024, lzhoang2601") | BSD-3-Clause | The EFI engine: compatibility, SSDTs, kext selection, config.plist. 1401 drives it headlessly and post-processes its output. |
| Hardware Sniffer | lzhoang2801 (same) | BSD-3-Clause | The hardware scan: Report.json plus the ACPI dump. |

Both license texts sit beside the code in `upstream/*/LICENSE`. 1401 never edits upstream files. Every change 1401
makes to their output lives in `p1401/` and is recorded per build as a named rule.

## Code adapted into 1401

| Where | From | License |
|---|---|---|
| `p1401/apple.py`: the recovery protocol, the chunklist format, Apple's EFI ROM public key | OpenCorePkg `Utilities/macrecovery/macrecovery.py`, Copyright (c) 2019, vit9696 (key recovery credited there to zhangyoufu) | BSD-3-Clause |

## Facts cross-checked, no text copied

| Where | Checked against | License of the source |
|---|---|---|
| `p1401/guide.py`: which BIOS settings macOS needs and why | Dortania, *OpenCore Install Guide* | CC BY-NC-SA 4.0. 1401 uses its facts only; every sentence in the guide is 1401's own, because NC-SA text cannot go into a GPL-3 program. |

## Downloaded at build or run time, verified, never redistributed by 1401

| What | From | How it is verified |
|---|---|---|
| OpenCorePkg release (bootloader, drivers, `ocvalidate`) | acidanthera, via the engine's pinned build repo | sha256 recorded in the engine's download history. `ocvalidate` refuses to run without one. |
| Kexts (Lilu, WhateverGreen, AppleALC, itlwm, ...) | Each author's release, chosen by the engine | Each keeps its own license. **Two currently have no sha256 in the engine's manifest (AppleIGB, AppleMCEReporterDisabler), which is an open 1401 issue.** |
| `acpidump.exe` (ACPICA R2024_12_12) | Intel ACPICA GitHub release | sha256 pinned in `p1401/scan.py`. ACPICA is dual BSD-3 / GPL-2. |
| macOS recovery image | **Apple**, from `osrecovery.apple.com` to the user's own USB stick | Apple's RSA-signed chunklist, with every chunk hash-checked as it streams |

## The NullMoth brand is not licensed

The license covers 1401's software and nothing else. The names **NullMoth** and **NullMoth Systems** and the moth logo
(`p1401/moth-mark.jpg`) are © 2026 NullMoth Systems, all rights reserved; no trademark rights are granted.

- Unmodified copies of 1401 may carry them exactly as shipped.
- A modified version must drop them: replace or delete `p1401/moth-mark.jpg` (or render with `mark=b""`), take the
  NullMoth names off the pages it generates, and never present itself as NullMoth's.

## Apple

1401 contains no Apple software and serves none. macOS downloads from Apple's servers directly onto the user's own
machine. 1401 ships no decryption keys and circumvents no Apple access control. The macOS license terms are
between the user and Apple, and 1401's README says so plainly.
