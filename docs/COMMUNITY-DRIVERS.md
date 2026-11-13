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
| Patches reviewed for merge into the AMD / Intel test driver (NMXGPU) and the NVIDIA driver | WTLIntelGfx, ArrowWhatever, NvGfx, nullarc, IrisXe-macos-driver, Meteor-Lake-Xe-LPG-Metal-Graphics, RedNavi | A patch is merged only where its licence allows it and the author is credited in the commit. The checklist is in "What to review" below. |
| Optional download, pinned | XPS13Plus-IrisXe-Tahoe (Thou Shalt Not Profit License) | Free to use, but a distributor must license copies under it, so it is never merged or hosted. On a Dell XPS 13 Plus the build notice gives the author's archive of one commit with its size and SHA-256 for the user to fetch and check. |
| Linked: the author's own release, fetched on the user's machine | nullarc 0.4.0-alpha (Phoenix / Hawk Point, machines with no NVIDIA card), Meteor-Lake-Xe-LPG-Metal-Graphics 0.3.21 (Dell Latitude 5350), Hackintosh-X1Carbon-G11-IrisXe-Tahoe V0.4 (ThinkPad X1 Carbon Gen 11), MyIntelGPU 4.4.121 (A7AC) | Whatever the licence, NullMoth never hosts, bundles or merges these. On a machine whose scan shows the hardware a project targets, the build notice gives the author's release file pinned by URL, size and SHA-256 (`LINKED_DOWNLOADS`), and the user's machine fetches it from the author. |
| Named in the build notice, nothing downloaded | nmx-intel, vibe-nullmoth-xe3-qemu, mothbridge-630 (no licence, all rights reserved, no release); RembrandtGfx (GPL-2.0, no release yet) | The notice links the author's page for the matching GPU. `docs/COMMUNITY-LICENCE-REQUEST.md` is the request to the authors for MIT or PolyForm Noncommercial. |
| Named in the build notice | PrimeBridge, WTLIntelGfx | When the scan shows a GPU the project targets, the notice says who made it, its licence and its state. Nothing is installed. |
| Not used | The rest | The reason is in the table: no licence and no useful driver, a licence we cannot meet, machine-written code, a copy of a project we already use, or not a driver for real hardware. |

Rules applied to every row:

- A project with no licence text is all rights reserved, whatever GitHub's label says. Only the LICENSE file counts. Its code is never hosted, bundled or merged. If it has a release for the user's hardware, the build notice links that release (pinned) so the user's machine fetches it from the author; otherwise it is only named, with a link to its author.
- Projects whose licence forbids any use with AI tools (the ChefKiss family: NootedRed and its forks, MetalCyan) are not read or listed here.
- NullMoth is free and noncommercial, and its own licence is PolyForm Noncommercial 1.0.0. A project under the same licence is
  compatible: its patches are reviewed for merge into NMXGPU and the driver with the author credited. 1401 itself downloads
  only what its licence lets 1401 use and credit.
- Code written by a coding assistant (the repository says so in its README, an assistant-instructions file in the tree, or commit
  trailers) is read for the idea and the implementation is written again. This is the rule used for PRs #479 and #524.
- Untrusted code was only read. No script or binary from these repositories was run on any NullMoth machine.

## All projects read

The commit is the head of the default branch on the date shown (2026-11-08 for the first read, 2026-11-13 for the census
of every project claiming Tahoe), except WhateverXe and WhateverXe Graphics, where it is the release that 1401 pins. Licence is what the LICENSE text says.

| Repo | Licence (read from the LICENSE text) | What it is | Verdict | How 1401 uses it, or why not | Commit read |
|---|---|---|---|---|---|
| b00t0x/WhateverXe | BSD-3-Clause | Intel Xe-LP graphics (Tiger, Alder, Raptor Lake) by running Apple's Tiger Lake driver; Lilu plugin | Integrated | release 0.8.0 (this commit) pinned in the Mac app; the Mac app already offered 0.6.1 (commit 68a2427) | `db438fd` (2026-11-08) |
| b00t0x/WhateverXe-Graphics | tools BSD-3 only; payloads not licensed | the graphics payloads WhateverXe needs, as an installer package | Integrated | release v0.4.1 pinned; fetched on the user's Mac from the author only, never mirrored (payloads are Apple's drivers) | `88d64a3` (2026-11-08) |
| carnations-botanica/IntelMKLFixup | GPL-3.0 | in-memory patch so Intel MKL applications run on AMD processors; Lilu plugin | Integrated | release 1.0.0 pinned in p1401/community.py, experimental opt-in, AMD processors only | `b77cd91` (2026-09-20) |
| RX4Darwin/AMDRadeonRDNA4.kext | BSD-3-Clause | RX 9070 / 9070 XT display driver (Lilu plugin over IONDRVFramebuffer), no acceleration | Integrated | already built from this commit and mirrored by NullMoth (p1401/amd_rdna4.py); experimental opt-in | `49f7f20` (2026-10-12) |
| myvoow/PrimeBridge | MIT (source, script, docs); NVRMFB patch is NullMoth's PolyForm code | internal screen of MUX-less Radeon 680M + NVIDIA laptops: forced HDMI head plus a copy into the firmware framebuffer | Idea built into our driver | release 0.4.8 needs NullMoth 2.6.3 exactly (hard-coded NVRMFB offsets); rebuilt in our driver as NMGopFB (AMD panel provider, 2.9) | `8c08c3e` (2026-11-02) |
| Helemen7/RedNavi | BSD-3-Clause | RX 7800 XT (Navi 32) display driver on its own DCN 3.2 kext; developer prototype | Reviewed for merge into NMXGPU / the driver | assistant-aided (263 commits), not installable; read for the DCN bring-up order that NMXGPU's RDNA 3 path needs | `587de1a` (2026-11-08) |
| Mountainatic/ArrowWhatever | PolyForm-NC (patches); MIT (scripts, docs) | ten patches over XeGfx 0.0.44 for Arrow Lake-HX: GGTT zero-copy scanout, 240 Hz HiDPI, Tile4/CCS scanout, colour | Reviewed for merge into NMXGPU / the driver | patches only (no code of its own to fetch); reviewed for NMXGPU and NMIntelFB, scanout ideas feed the hybrid import path | `555fbb2` (2026-11-06) |
| OscarrWu/780m-hackintosh | MIT | Radeon 780M kext with its own PSP/SMU/GMC power-up and RADV Darwin patches, staged bring-up notes | Reviewed for merge into NMXGPU / the driver | MIT and no release yet; its power-up order is reviewed for NMXGPU's RDNA 3 path beside nullarc | `a3a45d9` (2026-11-13) |
| samwu07/xegfx-thinkbook14plus-mtl | BSD-2-Clause | XeGfx on a ThinkBook 14+ 2024 (7D55): GuC band fix, framebuffer move, zero-copy flip, Sequoia 15.8.1 | Reviewed for merge into NMXGPU / the driver | Sequoia only; its GGTT and IOPresentment fixes are reviewed for NMXGPU and NMIntelFB | `f85a4d5` (2026-11-11) |
| taqieallah/ThinkPad-E16-ArrowLake-macOS | BSD-2-Clause | XeGfx on an Arrow Lake-H 255H (7D51): GPU-composited desktop, GGTT flip, deferred ordering, Tahoe | Reviewed for merge into NMXGPU / the driver | no release; its K9b ordering and flip work are reviewed for NMXGPU | `e2115d3` (2026-11-13) |
| watchthelight-labs/NvGfx | PolyForm-NC | fork of our NVIDIA driver (the base of XeGfx) | Reviewed for merge into NMXGPU / the driver | PolyForm Noncommercial is our own licence, so its patches can go back into NMXGPU and NVRM; reviewed there | `04f011e` (2026-10-31) |
| watchthelight-labs/WTLIntelGfx | BSD-2-Clause for shim/tools; PolyForm-NC for the forks of our code | i915 on XNU for Meteor Lake and Arrow Lake (Metal, Vulkan, GPU-composited desktop); renamed from XeGfx | Reviewed for merge into NMXGPU / the driver | its release is one bring-up kext (no accelerator, plugin or installer), so it is not a user package; patches reviewed for NMXGPU | `aac09a4` (2026-11-06) |
| wzh4869/Radeon-680M-Hackintosh | GPL-2.0 | RembrandtGfx: Radeon 680M (rev 02 -> c7 compatibility) with an accelerated Tahoe 26.7.2 desktop, 2560x1600 at 120 Hz, fixed 512 MiB | Reviewed for merge into NMXGPU / the driver | the only iGPU-only 680M route found; no release to fetch, so it is named for 680M machines without an NVIDIA card; its revision fix is reviewed for NMXGPU's Rembrandt path. One RedmiBook Pro 14 | `a34b37d` (2026-11-11) |
| zep245/IrisXe-macos-driver | PolyForm-NC (fork of our tree) | Tiger Lake Iris Xe through i915 + ANV: display, Metal, H.264/AV1 decode, HiDPI; fork of our tree | Reviewed for merge into NMXGPU / the driver | tester-grade, one laptop; overlaps WhateverXe on Tiger Lake. Its video-decode and PSR work is reviewed for NMXGPU | `c71dffc` (2026-11-06) |
| JulioNectar/Hackintosh-XPS13Plus-IrisXe-Tahoe | Thou Shalt Not Profit License 1.0 | Iris Xe on one Dell laptop through NootedGreen plus the XCPM power fix (EFI, build and install scripts) | Optional download, pinned | assistant-written (75 commits) and free to use, but a distributor must license copies under it: never merged into NullMoth code, never hosted; the build notice gives the author's archive pinned by commit and SHA-256 for a Dell XPS 13 Plus | `24450b4` (2026-11-03) |
| dssoftx/Hackintosh-X1Carbon-G11-IrisXe-Tahoe | none | JulioNectar's Tahoe Iris Xe stack ported to the ThinkPad X1 Carbon Gen 11 (Raptor Lake-U A7A1), 26.7.1 25G241 | Linked: fetched from its author on the user's machine | a whole EFI plus post-install package for one laptop; release V0.4 linked for that laptop only, never hosted | `5098a08` (2026-10-26) |
| luuumi-dev/nullarc | MIT or GPL-2.0 (own code); PolyForm-NC (derived from our tree) | Metal on Radeon 780M/760M/740M (Phoenix, Hawk Point) with a 120 Hz display kext and RADV | Linked: fetched from its author on the user's machine | release 0.4.0-alpha linked for machines with no NVIDIA card: its package installs its own NVMTLDriver.bundle, the same path as NullMoth's Metal plugin. Alpha, one machine, assistant-aided (83 commits); patches still reviewed for NMXGPU | `8aba872` (2026-11-09) |
| pongpan-bk/First-Custom-iGPU-Driver-for-Intel-Core-5-120U-on-macOS | none | stand-alone Raptor Lake-U (A7AC) kext | Linked: fetched from its author on the user's machine | no licence (all rights reserved) and assistant-written (README names its coding tool): never hosted or merged; its own installer v4.4.121 is linked for A7AC (author targets macOS 12+, Tahoe not shown) | `cbf8e37` (2026-11-13) |
| VedCloud/Meteor-Lake-Xe-LPG-Metal-Graphics | own licence: Apache-like for the original work only | Meteor Lake i915-on-LinuxKPI port with Metal; 6.8 GB repository with 874 binaries | Linked: fetched from its author on the user's machine | Tahoe Graphics-Audio 0.3.21 (2026-10-30) for the Dell Latitude 5350 (7D45) is linked, fetched from its author; derived from our tree and assistant-aided, so its patches are still only reviewed for NMXGPU, never merged as is | `62de794` (2026-10-30) |
| emirercan3459/nullmoth-nvidia-audio | none | multi-port HDMI/DP audio and volume for NVIDIA GPUs (NMHDA Lilu plugin) | Named in build notice only | no licence (all rights reserved) and assistant-written by its own statement; not named in a build notice because it applies to every NVIDIA card and NMXAudio is the supported audio path | `558dc64` (2026-10-19) |
| ericek111/vibe-nullmoth-xe3-qemu | none | 98 patches making NMXGPU drive a Panther Lake SR-IOV virtual function in a QEMU guest (Metal, GL, Vulkan) | Named in build notice only | no licence (all rights reserved): named in the build notice for Panther Lake, nothing downloaded; patches are not merged until the author grants a licence | `7246d38` (2026-10-18) |
| kitsuneislife/nmx-intel | none | NMIntelFB patches so a Raptor Lake laptop panel shows frames composited on an NVIDIA GPU | Named in build notice only | no licence (all rights reserved) and assistant-written (190 commits): named in the build notice for Raptor Lake-P laptops with an NVIDIA card, nothing downloaded; our own NMIntelFB already has copy and import paths | `b4bb3a0` (2026-10-30) |
| longurara/ArcMTL | none | Meteor Lake 155H (7D55) display + Metal 3 + Vulkan, or a headless Metal device beside the boot GPU, Tahoe and Sequoia | Named in build notice only | no licence and no release; XeGfx already covers 7D55, so it is catalogued and not noticed | `3acbe55` (2026-11-02) |
| nvsaim/mothbridge-630 | none | NVIDIA desktop on the UHD 630 (3E9B) panel of MUX-less Coffee Lake laptops, through NullMoth | Named in build notice only | no licence and no release: named for 3E9B beside an NVIDIA card; our Hybrid laptop mode covers the same job | `89a5348` (2026-11-08) |
| acidanthera/WhateverGreen | BSD-3-Clause | Lilu graphics patches for supported Intel and AMD GPUs | Not used | already in the engine's kext list; WhateverXe replaces it on Xe-LP | `093e76f` (2026-09-27) |
| akiffurkan/WhateverXe-0xA7A0 | BSD-3-Clause | WhateverXe 0.8.2 built for the XPS 13 Plus A7A0 eDP | Not used | machine build of upstream 0.8.2 | `c76768b` (2026-11-13) |
| AMD-OSX/AMD_Vanilla | none | AMD processor kernel patches (patches.plist) | Not used | no licence; 1401 writes its own AMD kernel patches (p1401/kernel_patches.py) | `eaf52ef` (2025-10-17) |
| belugaa-01/whateverxe-patched | BSD-3-Clause | WhateverXe with extra framebuffer patches for a 6-bit eDP panel (Alder Lake-U 46B3); release 0.2.0 | Not used | verified on one i3-1215U only; upstream WhateverXe 0.8.x covers 46B3 and reworks the eDP path | `cb29b1d` (2026-11-13) |
| change-48/xegfx-migrate | none | scratch patch scripts for an XeGfx migration | Not used | no licence; temporary scripts and 132 MB of build output | `eb07530` (2026-11-07) |
| dristotle/WhateverXe-ASUS-F15-eDP | BSD-3-Clause | WhateverXe 0.8.2 eDP test build for a Tiger Lake-H45 ASUS TUF F15 | Not used | machine test build, no release | `90806ab` (2026-11-13) |
| elezorn/whateverxe-tigerlakeh | BSD-3-Clause | fork of WhateverXe for Tiger Lake-H | Not used | the same commit as upstream WhateverXe 0.8.0 | `db438fd` (2026-11-08) |
| Harshshah6/PrimeBridge-nomux-hp-victus | MIT (as PrimeBridge) | fork of PrimeBridge for an HP Victus | Not used | a copy of PrimeBridge, which our NMGopFB already reimplements | `66bbf3b` (2026-11-12) |
| InSnh-Gd/WTLIntelGfx | BSD-2-Clause | fork of watchthelight-labs/WTLIntelGfx | Not used | a copy of the project above (same tree); read once there | `5ffc79f` (2026-11-01) |
| IT-EXPRESS-Bayern/LunarBridge-Hackintosh | GPL-3.0 | Lunar Lake Arc 130V (64A0) research on Tahoe | Not used | its own status: Metal and display blocked | `077fada` (2026-10-12) |
| jkbuha/WhateverXe | BSD-3-Clause | WhateverXe for the XPS 13 Plus 9320 (eDP, hibernate) | Not used | machine branch, no release | `09bd397` (2026-11-13) |
| kevin8717/TongFang-7840HS-Hackintosh | MIT | an EFI that runs nullarc's PhxBringup on a 780M (15BF) under Tahoe 26.7.2 | Not used | a machine EFI; the driver is nullarc, linked above | `6758dda` (2026-11-08) |
| lcrlcr666/WhateverXe-RGB8 | BSD-3-Clause | WhateverXe 0.8.1 with a forced RGB8 switch (upstream issue 74) | Not used | one switch over upstream, no release | `3afef31` (2026-11-13) |
| LuneFlu/AMDHelper | none | Ryzen power-limit helper (ryzenadj wrapper) | Not used | no licence; not a graphics driver; last commit 2024 | `b4cabfb` (2024-10-21) |
| m4j2rpf766-crypto/IntelIGPU-Tahoe | GPL-3.0 | Alder Lake (46A3) display, Metal desktop at ~120 fps on 144 Hz, backlight, HEVC service, GPU stall recovery on Tahoe 25G83 | Not used | source snapshot without the Apple binaries it needs and no release; WhateverXe already covers 46A3 with a release | `9baa4bb` (2026-09-28) |
| ManasSoni-2009/AlderXe | none | WhateverXe mod for Alder Lake-HX | Not used | no licence, no description of what it changes, no release | `e72c2b6` (2026-11-12) |
| medkintos/VP8MetalDecoder | none | VP8/VP9 decode on Metal compute as a VideoToolbox bundle | Not used | not a GPU driver; no licence | `d50764f` (2026-11-05) |
| Minorli/WhateverXe-Next | MIT | WhateverXe research fork on a Tiger Lake 96 EU, Tahoe 26.7.3 | Not used | research only; its author notes GPU queue hangs and forced shutdowns | `c2a6421` (2026-11-13) |
| mschiller890/Hackintosh-X13YogaG2-Iris | none | JulioNectar's stack on a ThinkPad X13 Yoga Gen 2 (Tiger Lake) | Not used | its own README says the Tahoe USB stops at EXITBS:START | `8d88daa` (2026-11-13) |
| NekoMirra/phoenix-hackintosh-toolkit | none | SMU and brightness tools for a Phoenix 8845H laptop | Not used | not a GPU driver; no licence | `32ee330` (2026-11-05) |
| pawan295/AppleIntelTGLDriver.kext | none | Tiger Lake controller skeleton | Not used | no licence; the author states it has no command submission and no Metal | `0da9a50` (2026-07-30) |
| retropineaple/whateverxe-hp-envy-x360 | none | WhateverXe set-up for an HP Envy x360 (46AA) OLED on Tahoe 26.7.1 | Not used | a machine guide; the driver is upstream WhateverXe | `3b52397` (2026-11-11) |
| samranahmad09/WhateverXe-RaptorLakeP | BSD-3-Clause | WhateverXe branch for Raptor Lake-P with native panel, Metal, OpenGL, sleep and wake | Not used | no release; its rplp-accel work is upstream's job | `565252f` (2026-11-11) |
| sgiammori/NootedGreen | none | Lilu plugin running Apple's Tiger Lake driver on Haswell to Raptor Lake | Not used | no licence, work in progress (still panics), no release; reaches users only through JulioNectar's project, which is already an optional download | `95f8189` (2026-05-23) |
| shandftk/RenoirDSBFix | MIT | dual-source-blend hang fix for Renoir under NootedRed | Not used | Sequoia only, and an add-on to a driver 1401 does not use | `8f8e80e` (2026-11-11) |
| taingo936-ui/whateverxe-alderlakes | BSD-3-Clause | WhateverXe fork with an experimental Lenovo LOQ 144 Hz eDP stage | Not used | machine-specific experimental branch of WhateverXe | `2373ede` (2026-11-03) |
| thatisjigen/whateverxe | BSD-3-Clause | fork of WhateverXe | Not used | a mirror of upstream (head by b00t0x), no changes of its own | `d0b7fb6` (2026-11-02) |
| TigerShota/WhateverXe | BSD-3-Clause | WhateverXe 0.7.0 for an Alder Lake-H 48 EU (46A3) 120 Hz panel | Not used | machine build of an older upstream | `25da561` (2026-11-08) |
| tqmane/reims-vgpu | GPL-2.0-or-later OR LGPL-3.0-or-later | virtual GPU for macOS guests in QEMU | Not used | not a driver for real hardware; 1,641 assistant-aided commits | `8f316b5` (2026-11-01) |
| vedprajapatiunitedkingdom-wq/CoreUltraGraphics | none | earlier Meteor Lake attempt by the same author | Not used | no licence file | `05b19dc` (2026-10-17) |
| wallali77666-cyber/iris-xe-macos-driver | none | Tiger Lake scaffold modelled on our tree | Not used | no licence; stubs only (phase D, acceleration, is 'research') | `9bf31c9` (2026-10-18) |
| watchthelight-labs/XeGfx | BSD-2-Clause | the earlier name of WTLIntelGfx | Not used | same commit as WTLIntelGfx | `aac09a4` (2026-11-06) |
| wkin-t/IntelIGPU-Tahoe | GPL-3.0 | fork of IntelIGPU-Tahoe | Not used | the same commit as the project above | `9baa4bb` (2026-11-09) |
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
| PrimeBridge | `1002-1681` (Radeon 680M) with any NVIDIA GPU in the same scan | Build notice. The author's release works with NullMoth 2.6.3 only; NullMoth 2.9 has the method built in (Mac app, Hybrid laptop mode). |
| WTLIntelGfx (XeGfx) | `8086-7D40 7D41 7D45 7D51 7D55 7D67 7DD1 7DD5` (the Meteor Lake and Arrow Lake IDs its README lists as running) | Build notice. |
| nullarc | `1002-1900 15BF 15C8` (Phoenix, Hawk Point) | Build notice with the pinned release. With an NVIDIA card in the scan the notice says not to install it: its package puts its own `NVMTLDriver.bundle` at the path of NullMoth's Metal driver. |
| Meteor-Lake-Xe-LPG-Metal-Graphics | `8086-7D45` on a board named Latitude 5350 | Build notice with the pinned Tahoe package. |
| Hackintosh-X1Carbon-G11-IrisXe-Tahoe | `8086-A7A1` on a board named X1 Carbon Gen 11 or machine type 21HM / 21HN | Build notice with the pinned EFI release (it replaces the EFI). |
| MyIntelGPU | `8086-A7AC` | Build notice with the author's installer. |
| RembrandtGfx | `1002-1681` with no NVIDIA GPU in the scan | Build notice, link only. |
| mothbridge-630 | `8086-3E9B` with an NVIDIA GPU in the scan | Build notice, link only. |

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
the direct-write probe can be added per chip as PrimeBridge does it. This is what was built: `NMGopFB` in the driver tree
(`kexts/NMGopFB`, docs/HYBRID-LAPTOPS.md in the driver repository), behind `nmhybrid`, for the AMD integrated GPUs and RDNA 3
and 4 cards macOS has no driver for. The Mac app's Hybrid laptop mode installs it in place of `NMIntelFB` when the scan
shows such a GPU. The direct-write probe is not built (staging copy only); it needs the per-chip register offsets and a
laptop to measure on. Nothing has run on hardware: the build notice still names PrimeBridge for its one proven ID.

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
