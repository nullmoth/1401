# Community drivers for Intel Xe and AMD graphics

NullMoth does not have to write every graphics driver alone. This page lists every community project for Intel Xe and AMD
graphics that came up in support chats and issues, what its licence lets us do, and what 1401 does with it. It was
written from a clone of each project at the commit shown, not from its README alone. The same data is in
`p1401/community_gpu.py`, and `tests/test_community_gpu.py` fails when they disagree.

## What 1401 does

| Kind | Projects | How |
|---|---|---|
| Downloaded from the author, pinned by URL, size and SHA-256 | WhateverXe 0.8.0 and WhateverXe Graphics v0.4.1 (Intel Xe-LP, Mac app opt-in); IntelMKLFixup 1.0.0 (AMD processors, experimental opt-in); the RX 9070 display driver (built by NullMoth from the pinned commit, experimental opt-in) | A project is added only if its licence lets 1401 use it (`p1401/licenses.json`, `tests/test_licenses.py`). Nothing is vendored. Credit and licence are in `NOTICE.md`. |
| Idea built into NullMoth's own driver | PrimeBridge | See "PrimeBridge and the hybrid path" below. |
| Patches reviewed for the AMD / Intel test driver (NMXGPU) | WTLIntelGfx, ArrowWhatever, nullarc, IrisXe-macos-driver, vibe-nullmoth-xe3-qemu, Meteor-Lake-Xe-LPG-Metal-Graphics, RedNavi, nmx-intel | A patch is merged only where its licence allows it and the author is credited in the commit. The checklist is in "What to review" below. |
| Named in the build notice | PrimeBridge, WTLIntelGfx, nullarc | When the scan shows a GPU the project targets, the notice says who made it, its licence and its state. Nothing is installed. |
| Not used | The rest | The reason is in the table: no licence, a licence that bars redistribution or commercial use, assistant-written code, a copy of a project we already use, or not a driver for real hardware. |

Rules applied to every row:

- A project with no licence text is not used, whatever GitHub's label says. Only the LICENSE file counts.
- PolyForm Noncommercial is the licence of NullMoth's own tree, so a fork of our tree under that licence can go back into it;
  it cannot go into anything NullMoth must be free to relicense, and 1401 does not download it.
- Code written by a coding assistant (the repository says so in its README, an assistant-instructions file in the tree, or commit
  trailers) is read for the idea and the implementation is written again. This is the rule used for PRs #479 and #524.
- Untrusted code was only read. No script or binary from these repositories was run on any NullMoth machine.

## All projects read

The commit is the head of the default branch on 2026-11-08, except WhateverXe and WhateverXe Graphics, where it is the
release that 1401 pins. Licence is what the LICENSE text says.

| Repo | Licence (read from the LICENSE text) | What it is | Verdict | How 1401 uses it, or why not | Commit read |
|---|---|---|---|---|---|
| b00t0x/WhateverXe | BSD-3-Clause | Intel Xe-LP graphics (Tiger, Alder, Raptor Lake) by running Apple's Tiger Lake driver; Lilu plugin | Integrated | release 0.8.0 (this commit) pinned in the Mac app; the Mac app already offered 0.6.1 (commit 68a2427) | `db438fd` (2026-11-08) |
| b00t0x/WhateverXe-Graphics | tools BSD-3 only; payloads not licensed | the graphics payloads WhateverXe needs, as an installer package | Integrated | release v0.4.1 pinned; fetched on the user's Mac from the author only, never mirrored (payloads are Apple's drivers) | `88d64a3` (2026-11-08) |
| carnations-botanica/IntelMKLFixup | GPL-3.0 | in-memory patch so Intel MKL applications run on AMD processors; Lilu plugin | Integrated | release 1.0.0 pinned in p1401/community.py, experimental opt-in, AMD processors only | `b77cd91` (2026-09-20) |
| RX4Darwin/AMDRadeonRDNA4.kext | BSD-3-Clause | RX 9070 / 9070 XT display driver (Lilu plugin over IONDRVFramebuffer), no acceleration | Integrated | already built from this commit and mirrored by NullMoth (p1401/amd_rdna4.py); experimental opt-in | `49f7f20` (2026-10-12) |
| myvoow/PrimeBridge | MIT (source, script, docs); NVRMFB patch is NullMoth's PolyForm code | internal screen of MUX-less Radeon 680M + NVIDIA laptops: forced HDMI head plus a copy into the firmware framebuffer | Idea built into our driver | release 0.4.8 needs NullMoth 2.6.3 exactly (hard-coded NVRMFB offsets); the design is rebuilt in our own driver, see docs | `8c08c3e` (2026-11-02) |
| ericek111/vibe-nullmoth-xe3-qemu | none | 98 patches making NMXGPU drive a Panther Lake SR-IOV virtual function in a QEMU guest (Metal, GL, Vulkan) | Patches reviewed for NMXGPU | no licence: patches are not used until the author grants one; the series list is the review checklist for NMXGPU | `7246d38` (2026-10-18) |
| Helemen7/RedNavi | BSD-3-Clause | RX 7800 XT (Navi 32) display driver on its own DCN 3.2 kext; developer prototype | Patches reviewed for NMXGPU | assistant-aided (263 commits), not installable; read for the DCN bring-up order that NMXGPU's RDNA 3 path needs | `587de1a` (2026-11-08) |
| kitsuneislife/nmx-intel | none | NMIntelFB patches so a Raptor Lake laptop panel shows frames composited on an NVIDIA GPU | Patches reviewed for NMXGPU | no licence and assistant-written (190 commits): read for the idea only; our own NMIntelFB already has copy and import paths | `b4bb3a0` (2026-10-30) |
| luuumi-dev/nullarc | MIT or GPL-2.0 (own code); PolyForm-NC (derived from our tree) | Metal on Radeon 780M/760M/740M (Phoenix, Hawk Point) with a 120 Hz display kext and RADV | Patches reviewed for NMXGPU | alpha, one machine, assistant-aided (83 commits); its Phoenix bring-up and RADV patches are reviewed for NMXGPU | `8aba872` (2026-11-09) |
| Mountainatic/ArrowWhatever | PolyForm-NC (patches); MIT (scripts, docs) | ten patches over XeGfx 0.0.44 for Arrow Lake-HX: GGTT zero-copy scanout, 240 Hz HiDPI, Tile4/CCS scanout, colour | Patches reviewed for NMXGPU | patches only (no code of its own to fetch); reviewed for NMXGPU and NMIntelFB, scanout ideas feed the hybrid import path | `555fbb2` (2026-11-06) |
| VedCloud/Meteor-Lake-Xe-LPG-Metal-Graphics | own licence: Apache-like for the original work only | Meteor Lake i915-on-LinuxKPI port with Metal; 6.8 GB repository with 874 binaries | Patches reviewed for NMXGPU | derived from our tree; the licence excludes every file derived from a third-party component, which is most of it; assistant-aided | `62de794` (2026-10-30) |
| watchthelight-labs/WTLIntelGfx | BSD-2-Clause for shim/tools; PolyForm-NC for the forks of our code | i915 on XNU for Meteor Lake and Arrow Lake (Metal, Vulkan, GPU-composited desktop); renamed from XeGfx | Patches reviewed for NMXGPU | its release is one bring-up kext (no accelerator, plugin or installer), so it is not a user package; patches reviewed for NMXGPU | `aac09a4` (2026-11-06) |
| zep245/IrisXe-macos-driver | PolyForm-NC (fork of our tree) | Tiger Lake Iris Xe through i915 + ANV: display, Metal, H.264/AV1 decode, HiDPI; fork of our tree | Patches reviewed for NMXGPU | tester-grade, one laptop; overlaps WhateverXe on Tiger Lake. Its video-decode and PSR work is reviewed for NMXGPU | `c71dffc` (2026-11-06) |
| acidanthera/WhateverGreen | BSD-3-Clause | Lilu graphics patches for supported Intel and AMD GPUs | Not used | already in the engine's kext list; WhateverXe replaces it on Xe-LP | `093e76f` (2026-09-27) |
| AMD-OSX/AMD_Vanilla | none | AMD processor kernel patches (patches.plist) | Not used | no licence; 1401 writes its own AMD kernel patches (p1401/kernel_patches.py) | `eaf52ef` (2025-10-17) |
| belugaa-01/whateverxe-patched | BSD-3-Clause | two-check patch to WhateverXe 0.6.1 for a 6-bit eDP panel (Alder Lake-U 46B3) | Not used | targets 0.6.1, verified on one machine; WhateverXe 0.8.0 reworks the eDP path, so the patch no longer applies | `1ac73a3` (2026-11-06) |
| change-48/xegfx-migrate | none | scratch patch scripts for an XeGfx migration | Not used | no licence; temporary scripts and 132 MB of build output | `eb07530` (2026-11-07) |
| elezorn/whateverxe-tigerlakeh | BSD-3-Clause | fork of WhateverXe for Tiger Lake-H | Not used | the same commit as upstream WhateverXe 0.8.0 | `db438fd` (2026-11-08) |
| emirercan3459/nullmoth-nvidia-audio | none | multi-port HDMI/DP audio and volume for NVIDIA GPUs (NMHDA Lilu plugin) | Not used | no licence; assistant-written by its own statement; NMXAudio is the supported audio path | `558dc64` (2026-10-19) |
| InSnh-Gd/WTLIntelGfx | BSD-2-Clause | fork of watchthelight-labs/WTLIntelGfx | Not used | a copy of the project above (same tree); read once there | `5ffc79f` (2026-11-01) |
| JulioNectar/Hackintosh-XPS13Plus-IrisXe-Tahoe | Thou Shalt Not Profit License 1.0 | Iris Xe on one Dell laptop through NootedGreen plus the XCPM power fix | Not used | assistant-written (75 commits); the licence forces our distribution under it and bars profit; WhateverXe already credits it for the ideas | `24450b4` (2026-11-03) |
| LuneFlu/AMDHelper | none | Ryzen power-limit helper (ryzenadj wrapper) | Not used | no licence; not a graphics driver; last commit 2024 | `b4cabfb` (2024-10-21) |
| pawan295/AppleIntelTGLDriver.kext | none | Tiger Lake controller skeleton | Not used | no licence; the author states it has no command submission and no Metal | `0da9a50` (2026-07-30) |
| pongpan-bk/First-Custom-iGPU-Driver-for-Intel-Core-5-120U-on-macOS | none | stand-alone Raptor Lake-U (A7AC) kext | Not used | no licence; assistant-written (README names its coding tool); prebuilt objects in the tree | `f8a98b7` (2026-11-04) |
| taingo936-ui/whateverxe-alderlakes | BSD-3-Clause | WhateverXe fork with an experimental Lenovo LOQ 144 Hz eDP stage | Not used | machine-specific experimental branch of WhateverXe | `2373ede` (2026-11-03) |
| thatisjigen/whateverxe | BSD-3-Clause | fork of WhateverXe | Not used | a mirror of upstream (head by b00t0x), no changes of its own | `d0b7fb6` (2026-11-02) |
| tqmane/reims-vgpu | GPL-2.0-or-later OR LGPL-3.0-or-later | virtual GPU for macOS guests in QEMU | Not used | not a driver for real hardware; 1,641 assistant-aided commits | `8f316b5` (2026-11-01) |
| vedprajapatiunitedkingdom-wq/CoreUltraGraphics | none | earlier Meteor Lake attempt by the same author | Not used | no licence file | `05b19dc` (2026-10-17) |
| wallali77666-cyber/iris-xe-macos-driver | none | Tiger Lake scaffold modelled on our tree | Not used | no licence; stubs only (phase D, acceleration, is 'research') | `9bf31c9` (2026-10-18) |
| watchthelight-labs/NvGfx | PolyForm-NC | fork of our NVIDIA driver (the base of XeGfx) | Not used | a fork of our own tree; nothing to take that we do not have | `04f011e` (2026-10-31) |
| watchthelight-labs/XeGfx | BSD-2-Clause | the earlier name of WTLIntelGfx | Not used | same commit as WTLIntelGfx | `aac09a4` (2026-11-06) |
| yt42c2mvn2-cmd/nullarc-760m | as nullarc | fork of nullarc for a Radeon 760M laptop | Not used | a fork of the project above | `f08b898` (2026-11-08) |

The last two WhateverXe forks that look like extra support (`belugaa-01`, `taingo936-ui`) change one or two checks for one
laptop each on top of an older WhateverXe; WhateverXe 0.8.0 reworked the same code (internal panels, Alder Lake-U), so they
were not taken. Open an issue upstream with the panel type if a laptop still fails.

## Which machines each project applies to

`p1401/community_gpu.options(report)` reads the PCI IDs of the scanned GPUs ("VVVV-DDDD", upper case). The fingerprints
are the IDs each project documents as running; `tests/test_community_gpu.py` runs them offline.

| Project | Matches | Result |
|---|---|---|
| WhateverXe | Intel Tiger Lake, Alder Lake, Raptor Lake: the 60 IDs of WhateverXe 0.8.0 (`intel_gpu.WHATEVERXE_IDS`, `App.xeIds` in the Mac app, the list in `nullmoth-setup.sh`; a test keeps the three equal) | The Mac app offers Intel Xe graphics after install (macOS 15.8 and later, 26.7 and later). New in 0.8.0: Tiger Lake `9A59 9AC0 9AC9 9AD9 9AF8`, Alder Lake `4626 4628 462A 46A0-46A2 46B0-46B2 46C0-46C2`, Raptor Lake `A720 A721`. |
| IntelMKLFixup | CPU manufacturer AMD | Added to the EFI as an experimental driver, only when the user turns on experimental drivers. Intel processors never get it. |
| PrimeBridge | `1002-1681` (Radeon 680M) with any NVIDIA GPU in the same scan | Build notice. The author's release works with NullMoth 2.6.3 only. |
| WTLIntelGfx (XeGfx) | `8086-7D40 7D41 7D45 7D51 7D55 7D67 7DD1 7DD5` (the Meteor Lake and Arrow Lake IDs its README lists as running) | Build notice. |
| nullarc | `1002-1900 15BF 15C8` (Phoenix, Hawk Point) | Build notice. |

A scan with none of these IDs gets no community notice. AMD IDs the engine drives natively (Polaris, Vega, Navi 1x and 2x)
and every NVIDIA card are untouched.

One correction came out of this: `amd_gpu.py` labelled `1002:1900` "Strix Halo". nullarc's author measured that ID on a
Ryzen 7 7840HS Radeon 780M, which is Phoenix; Strix Halo is `1586`. The label is fixed; the path (basic display) is unchanged.

## PrimeBridge and the hybrid path

PrimeBridge (myvoow, MIT) shows the macOS desktop on the internal screen of a laptop whose panel is wired only to an AMD
Radeon 680M, while macOS renders on the NVIDIA GPU through NullMoth. It runs daily on one laptop (Ryzen 5 7535HS, RTX 4050
Laptop, macOS 26.7.2, NullMoth 2.6.3).

What it does, from `PrimeBridge-source/` and `NVRMFB-patch/nvfbforce.patch`:

1. `nvfbforce=1` makes NVRMFB report the first HDMI connector as connected, with a built-in 1920x1080 EDID, when nothing is
   plugged into the NVIDIA card. Head 0 then exists, so the accelerator starts.
2. The accelerator copies each composited frame with the CPU into the address NVRMFB gave it (`fKva`). PrimeBridge replaces
   that address: first a cached staging buffer (a timer compares rows with a shadow and writes changed rows into the
   firmware framebuffer the iGPU is scanning out), then, after a probe, the firmware framebuffer itself.
3. The probe reads `GCMC_VM_FB_OFFSET` through BAR5 to find the iGPU's memory, checks that what it reads there matches what
   it wrote through BAR0, times three mappings, and goes direct only if rows take under 3 microseconds.
4. OpenCore's "Fix PAT" patch must be off, because it makes write-combined memory uncached (39.7 microseconds per row
   instead of 2.0; the desktop falls back to the staging copy).

Comparison with NullMoth's hybrid path (`docs/HYBRID-LAPTOPS.md`, `kexts/NVRM/accel/nm_hybrid.h`):

| | PrimeBridge | NullMoth hybrid (`nmhybrid`) |
|---|---|---|
| Needs a panel driver for the iGPU | No. It uses the framebuffer the firmware left behind. | Yes: `NMIntelFB` (Intel display versions 12 to 20) or the NMXGPU framebuffer (AMD, never run on hardware). |
| AMD iGPU panel | One chip (1681), proven on one laptop | NMXGPU copy path, unproven |
| Intel iGPU panel | Not supported | Copy and, on display versions 12 and 13, an import path with no copy and no tearing |
| Copying | Row diff into staging, or direct write after a probe | Changed-pixel copy against a shadow frame |
| Tearing | Possible (single buffer) | None on the import path |
| Backlight | None | `NMIntelFB` has it; AMD does not |
| Tied to a driver version | NVRMFB 2.6.3 offsets hard-coded | Same tree, no offsets |
| Fake HDMI head | Yes, to make head 0 exist | Not needed: the panel is published as head 4 |

Conclusion: PrimeBridge does not beat the hybrid path on Intel, where ours has the import path. It does beat it on AMD, where
we have no working panel driver, because it needs none. The fake HDMI head is only needed when no panel head is published;
a generic firmware-framebuffer panel provider that publishes head 4 (a small framebuffer kext modelled on `NMIntelFB`, with
PrimeBridge's boot-framebuffer mapping, MIT) would give every MUX-less laptop the copy path without any iGPU driver, and
the direct-write probe can be added per chip as PrimeBridge does it. This is a driver change, tracked with the hybrid work;
it is not in 1401. Until it ships the build notice only names PrimeBridge for the one ID it supports.

### Permission and credit for PrimeBridge

PrimeBridge's LICENSE is MIT (Copyright (c) 2026 myvoow, with a link to its repository) for `PrimeBridge-source/`, the install
script and the documents. That already permits use, copying, modification and distribution, provided the notice is kept.
Its author also told the NullMoth maintainers that NullMoth may use and link the project (November 2026). The MIT notice is
kept in `NOTICE.md` and goes into any file that uses the project's code. `NVRMFB-patch/` and the shipped `NVRMFB.kext` are
NullMoth's own PolyForm code and are not reused.

## What to review for NMXGPU

These projects are forks of NullMoth's tree, or ports of the Linux and FreeBSD drivers it runs. Their patches are the
cheapest source of findings for the AMD / Intel test driver. Hardware these authors tested is hardware we do not own.

| Project | Where the work is | Licence for merging |
|---|---|---|
| WTLIntelGfx | `shim/`, `xkpi/` (GuC firmware linked into the kext because the auxiliary collection serves no resources; devfs clone minor numbers; ioctls through the accelerator's user client when WindowServer's sandbox refuses `/dev/dri`); `kexts/NMIntelFB` changes | BSD-2 files: merge with credit. PolyForm files: our licence |
| ArrowWhatever | `patches/` 0001-0010 over XeGfx 0.0.44: userptr pin race, GGTT zero-copy scanout with deferred flip, Tile4 and CCS scanout, SLPC floor on late frames | PolyForm: merge with credit; its MIT scripts and docs need only the notice |
| ericek111 (Panther Lake VF) | `patches/` 47 for the driver tree, 50 for xkpi, libdrm 5, Mesa 8, drm-kmod 1, QEMU 4 | No licence: ask the author before merging; until then use `SERIES.md` as a checklist |
| IrisXe-macos-driver (zep245) | Tiger Lake: H.264 and AV1 decode through the video engine, PSR1, RC6, HiDPI, `nmxgtawake=2` for a firmware that stops at `71 vmap` | PolyForm fork of our tree: merge with credit |
| nullarc | Phoenix bring-up (`src/phxbringup`), `PhxAMDFB` backlight, boot-time `doWaitSeq` backoff, RADV patches | Own code MIT or GPL-2.0, derived parts PolyForm; assistant-aided, so reimplement from the findings |
| RedNavi | Navi 32 DCN 3.2 bring-up order, PSP/DMCUB firmware chain | BSD-3 but assistant-aided: reimplement |
| nmx-intel | `source-fixes/0001-0019`, `docs/knowledge/pitfalls.md` | No licence, assistant-written: findings only |
| Meteor-Lake-Xe-LPG-Metal-Graphics | Dell Latitude 5350 bring-up notes | Own licence covers original work only; assistant-aided: findings only |

## Updating a pin

1. Read the release notes and the LICENSE text at the new tag; compare the supported IDs and the macOS range.
2. Download on a build machine into an empty folder; compute the SHA-256 and compare it with the author's `SHA256SUMS`.
3. Change the URL, size and hash in one place (`p1401/community.py`, or `mac/Resources/nullmoth-setup.sh` for WhateverXe),
   the commit in `p1401/community_gpu.py` and this page, and the version in `NOTICE.md`.
4. Run `python3 -m unittest tests.test_community tests.test_community_gpu tests.test_licenses tests.test_intel_gpu` and
   `python3 mac/tools/test_xe_whateverxe.py`.

WhateverXe moved from 0.6.1 to 0.8.0 this way. Its requirements did not change (Lilu, the modified AMFIPass build,
`csr-active-config` 0x803, `-allow3d -disablegfxfirmware`, macOS 15.8 or 26.7 and later); the AMFIPass file has the same
SHA-256 as before; only the kext, the graphics package and the uninstall script changed.
