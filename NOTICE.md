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

## Downloaded at build or run time, verified

| What | From | How it is verified |
|---|---|---|
| OpenCorePkg release (bootloader, drivers, `ocvalidate`) | acidanthera, via the engine's pinned build repo | sha256 recorded in the engine's download history. `ocvalidate` refuses to run without one. |
| Kexts (Lilu, WhateverGreen, AppleALC, itlwm, ...) | Each author's release, chosen by the engine | Each keeps its own license. **Two currently have no sha256 in the engine's manifest (AppleIGB, AppleMCEReporterDisabler), which is an open 1401 issue.** |
| SimpleMtkBtFw (MediaTek Bluetooth), by laobamac | The project's `1.0.0` GitHub release (`SimpleMtkBtFw-1.0.0-RELEASE.zip`) | **GPL-3.0** (`LICENSE` in the repo). Pinned to the exact asset and sha256 `b6afbe45…dc84954`, verified on download. Source for this binary is the tagged release at `github.com/laobamac/SimpleMtkBtFw` (tag `1.0.0`). |
| AirportRTW (Realtek Wi-Fi), by souissiak1-maker | Release `V2.1.0`, the Sequoia or Tahoe build | **GPL-2.0**. Pinned by size and sha256 (`p1401/community.py`); source: the `V2.1.0` tag. Opt-in (experimental drivers). |
| AirportMtkWlan (MediaTek Wi-Fi on macOS 26), by flxxxxddd, from laobamac's SimpleMtkWlan | Release `v1.5.0` | **GPL-2.0**. Pinned; source: the `v1.5.0` tag. Opt-in. |
| AirportWCN7850 (Qualcomm WCN7850 Wi-Fi), by razvanccr | Release `v0.0.2` | **GPL-2.0** (OpenBSD `qwz(4)` port, ISC parts; firmware from linux-firmware). Pinned; source: the `v0.0.2` tag. Opt-in, macOS 26. |
| BluetoothWCN7850 (Qualcomm WCN7850 Bluetooth), by razvanccr | Release `v1.0.0` | **MIT**. Pinned. Added for the USB IDs it matches. |
| XhciNudge and KernReserveLow (AMD laptop USB fixes), by MonkaKokosowa | Releases `1.0` | **MIT**. Pinned. Opt-in, for AMD xHCI 1022:161D/161E/15D6/15D7. |
| LegionCbmrFix, LegionI2CArrowLake, LegionITEKbdFix, LegionCpuPower, by watchthelight | Releases `1.0.0`, `1.1.0`, `1.0.0`, `0.3.3` | **BSD-3-Clause** (CbmrFix), **ISC** (the others). Pinned. CbmrFix and CpuPower are opt-in. |

### The download mirror

`nullmothsystems.com/mirror` keeps byte-identical copies for networks that cannot reach GitHub (`p1401/mirror.py`). It
holds only what each project's licence lets NullMoth redistribute (`p1401/licenses.json`, checked by
`tests/test_licenses.py`): permissive projects as published, copyleft projects with the source of that exact commit or
tag beside the binary. Projects with no licence, a restrictive licence, or files that come from inside another tool
(OpenCore Legacy Patcher's payloads, the engine author's file host) are never copied there; the engine downloads those
from their authors as before.

## The Python runtime in the Windows package

Pinned by URL and SHA-256 in `windows/release-inputs.json`, installed by `tools/windows_release.py`, unmodified.

| What | From | License |
|---|---|---|
| CPython 3.13.17 (Windows embeddable package) | python.org | PSF License 2.0 (`LICENSE.txt` in the runtime folder) |
| pywin32 312 | PyPI | PSF License |
| WMI 1.5.1, by Tim Golden | PyPI | MIT |
| certifi 2026.10.23 (Mozilla's CA list) | PyPI | MPL-2.0 |

## Built and redistributed by 1401 (with source), verified by hash

| What | Upstream | License and source |
|---|---|---|
| SimpleMtkWlan (MediaTek Wi-Fi) kext, by laobamac | `github.com/laobamac/SimpleMtkWlan` at commit `37ba676`, built by 1401 against acidanthera/MacKernelSDK (BSD-3) at commit `3f75008` with the macOS 15 SDK (`tools/build_mtkwlan.sh`) | **GPL-2.0** (`LICENSE` in the repo). 1401 distributes the built kext because the project ships no release, so it also hosts the exact matching source: the kext is `nullmothsystems.com/mirror/da0ef982…ee18f9` (sha256) and its GPL-2.0 source is `nullmothsystems.com/mirror/3109381a…cd49fa` (sha256), both pinned in `p1401/mirror.json` and `p1401/netsupport.py` and verified on download. MacKernelSDK is BSD-3 and keeps its own notice. |
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
