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
| `mac/RuntimeCheck/tcc_grant.m`: granting microphone, camera and screen recording through TCC.framework's `TCCAccessSetForBundle` with the `com.apple.private.tcc.manager` entitlement | tccplus, Copyright (c) 2020 Jeremy Legendre, https://github.com/jslegendre/tccplus | MIT |

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
| AMDRadeonRDNA4 (AMD RX 9070 / R9700 display driver), by Sunneva N. Mariu (RX4Darwin) | Built by NullMoth from commit `49f7f20` of RX4Darwin/AMDRadeonRDNA4, package `0.1.0` | **BSD-3-Clause**; the package carries its licence (`LICENSE-AMDRadeonRDNA4.txt`). Pinned by size and sha256 (`p1401/amd_rdna4.py`). Opt-in (experimental drivers), only for 1002:7550 and 1002:7551. Display only, no acceleration. |
| WhateverXe (Intel Xe graphics, Mac app, opt-in), by b00t0x | Release `0.8.0` (commit `db438fd`) | **BSD-3-Clause**. Pinned by sha256 in `mac/Resources/nullmoth-setup.sh`; only offered for the Intel GPU IDs it supports. |
| WhateverXe Graphics, its AMFIPass build and its uninstall script, by b00t0x | Release `v0.4.1` and commit `88d64a3` of WhateverXe-Graphics | Downloaded on the user's Mac from the author's GitHub only, each pinned by sha256. Never mirrored or redistributed by NullMoth: the package holds Apple's Intel graphics drivers as adapted by its author. |
| IntelMKLFixup (Intel MKL compatibility for AMD processors), by carnations-botanica | Release `1.0.0` | **GPL-3.0** (`LICENSE` in the repo). Pinned by size and sha256 (`p1401/community.py`); source: the `1.0.0` tag. Opt-in (experimental drivers), AMD processors only. |

## Community graphics projects read for NullMoth's own drivers

Nothing in this table is downloaded or shipped by 1401. NullMoth's own drivers use the idea, and where code is reused it
keeps the author's notice and licence. The full list (32 projects, licence and verdict for each, pinned commits) is
`docs/COMMUNITY-DRIVERS.md`.

| Project | License | What NullMoth takes |
|---|---|---|
| PrimeBridge, by myvoow (https://github.com/myvoow/PrimeBridge) | MIT, Copyright (c) 2026 myvoow. Its author allowed NullMoth to use and link it (stated to the NullMoth maintainers, November 2026) | The method of showing an NVIDIA-rendered desktop on the internal screen of a laptop whose panel belongs to an AMD integrated GPU: copy each frame into the firmware framebuffer, and write straight into it once the iGPU's memory window has been verified. Any code taken from `PrimeBridge-source/` keeps the MIT notice above. Its `NVRMFB-patch/` is NullMoth's own PolyForm code and is not reused. |
| Hackintosh-XPS13Plus-IrisXe-Tahoe, by JulioNectar | Thou Shalt Not Profit License 1.0 | Not included and not hosted. For a Dell XPS 13 Plus the build notice gives the author's archive of one commit, pinned by SHA-256, for the user to fetch from the author's GitHub. |
| WTLIntelGfx (XeGfx), by watchthelight | BSD-2-Clause for the shim, tools and docs; the parts forked from NullMoth stay PolyForm Noncommercial | Reviewed patches for the AMD / Intel test driver (Meteor Lake and Arrow Lake bring-up). |
| nullarc by luuumi-dev, ArrowWhatever by Mountainatic, IrisXe-macos-driver by zep245, vibe-nullmoth-xe3-qemu by ericek111, Meteor-Lake-Xe-LPG-Metal-Graphics by VedCloud, RedNavi by Helemen7 | Per project (`docs/COMMUNITY-DRIVERS.md`) | Read for findings on Radeon 780M, Arrow Lake, Tiger Lake, Panther Lake and Navi 32 bring-up. A patch is merged only where its licence allows it and the author is credited in the commit. |

### Written again in NullMoth's own code

Where a community project showed what a machine needs, 1401 carries its own implementation, with its own tests. Nothing
below was copied; the project is named as the source of the finding.

| Project | What it showed | Where it is in 1401 |
|---|---|---|
| Hackintosh-XPS13Plus-IrisXe-Tahoe, by JulioNectar | A 4 performance + 8 efficiency core Raptor Lake-P laptop freezes right after EXITBS with the efficiency cores on, because the kernel divides the logical-processor count by a core count that is 128 under ProvideCurrentCpuInfo; CPUID leaf 1 reporting 128 fixes it | `p1401/machine_recipes.json` and `policy.py` (`set_cpuid1_logical_per_package`), `tests/test_machine_recipes.py` |
| AMDHelper, by LuneFlu | A Ryzen laptop is helped by a power-limit profile applied at start and refreshed | `mac/Resources/nullmoth-ryzen-power.sh`, `tests/test_ryzen_power.py`. The profile calls RyzenAdj (FlyGoat/RyzenAdj, LGPL-3.0), tag v0.19.0, commit ea71739b4a3e1a0a624dfd1c9c268a31cb2a4182. Upstream has no macOS port, so NullMoth wrote the OS layer (`mac/Resources/ryzenadj-macos/osdep_macos.c`, LGPL-3.0, combined with the unmodified tag; this folder plus the tag is the complete source) and the NMSMN kext it talks to (driver tree, opt-in with nmsmn=1, SMU mailbox registers only). The pinned build's SHA-256 is in `mac/Resources/ryzenadj.sha256`: 77846bfa1bb575e6dea7bc6fff8bec4a99b6ed44fe7a8212c0d1d225286979fb |
| AMD_Vanilla, by AMD-OSX | The kernel patches AMD processors need | The build already uses the maintained fork's list, which covers it; `tools/compare_amd_kernel_patches.py` shows that (two of its patches are stale for macOS 26) |

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
