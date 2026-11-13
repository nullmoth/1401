"""Community graphics projects for Intel Xe and AMD integrated GPUs: what 1401 does with each, and which scanned
machines it applies to.

Every project below was read from a clone pinned at `commit` (licence text, README, source layout, history). The verdict
says what became of it:

- INTEGRATED: 1401 downloads the author's release, pinned by URL, size and SHA-256 (WhateverXe through the Mac app,
  IntelMKLFixup and the RDNA 4 display driver through the engine). Credit and licence text are in NOTICE.md.
- DRIVER_IDEA: the idea is implemented in NullMoth's own driver; the author's code is used under its licence, with credit.
- PORT_REVIEW: a fork or port of NullMoth's own tree (or of the Linux/FreeBSD drivers it runs). Not offered to users;
  its patches are reviewed for the AMD/Intel test driver (NMXGPU) and merged with the author's credit where the licence
  allows. PolyForm-Noncommercial forks of our tree stay under that licence, which is the licence of the tree they go
  back into.
- OPTIONAL: a licence that is free to use but obliges anyone who distributes it (Thou Shalt Not Profit). 1401 never
  copies it into NullMoth code or hosts it; the build notice gives the author's archive pinned by commit, size and SHA-256
  for the user to fetch.
- LINKED: a released driver whatever its licence (including none, and including packages that carry Apple's own drivers).
  1401 never hosts, bundles or merges it. The build notice links the author's own release file, pinned by URL, size and
  SHA-256 (LINKED_DOWNLOADS), and only on a machine whose scan shows the hardware it targets, so the user's machine fetches
  it from its author when it needs it.
- NAMED: a useful driver with no licence (all rights reserved) and no release to fetch. 1401 names it in the build notice
  with a link to the author's page for matching hardware, and downloads or redistributes nothing. docs/COMMUNITY-LICENCE-REQUEST.md asks the
  authors for MIT or PolyForm Noncommercial.
- EXCLUDED: not used. The reason is one of: no licence, a licence that forbids redistribution or commercial use of the
  part we would need, assistant-written code, not a GPU driver for real hardware, or a fork identical to an upstream we
  already use.

A project with a verdict other than EXCLUDED may also be named in the build notice (options() below) when the scan shows
hardware it targets; the notice says who made it, its licence and its state, and nothing is downloaded or installed.

docs/COMMUNITY-DRIVERS.md carries the same table with the evidence. tests/test_community_gpu.py fails when the two
disagree or when a pinned commit is not a full hash.
"""
from . import intel_gpu

INTEGRATED, DRIVER_IDEA, PORT_REVIEW, OPTIONAL, LINKED, NAMED, EXCLUDED = (
    "integrated", "driver-idea", "port-review", "optional-download", "linked-download", "named-only", "excluded")
VERDICTS = (INTEGRATED, DRIVER_IDEA, PORT_REVIEW, OPTIONAL, LINKED, NAMED, EXCLUDED)


def _p(repo, commit, date, licence, verdict, what, why):
    return {"repo": repo, "commit": commit, "date": date, "licence": licence, "verdict": verdict, "what": what, "why": why}


# commit = the head of the default branch when it was read, except where the row says a release tag.
PROJECTS = (
    _p("b00t0x/WhateverXe", "db438fdf4d5fe903f5dfbc65537ed3884e2ea980", "2026-11-08", "BSD-3-Clause", INTEGRATED,
       "Intel Xe-LP graphics (Tiger, Alder, Raptor Lake) by running Apple's Tiger Lake driver; Lilu plugin",
       "release 0.8.0 (this commit) pinned in the Mac app; the Mac app already offered 0.6.1 (commit 68a2427)"),
    _p("b00t0x/WhateverXe-Graphics", "88d64a340e6f0d52e3f32a136c920d190ac43c53", "2026-11-08", "tools BSD-3 only; payloads not licensed",
       INTEGRATED, "the graphics payloads WhateverXe needs, as an installer package",
       "release v0.4.1 pinned; fetched on the user's Mac from the author only, never mirrored (payloads are Apple's drivers)"),
    _p("carnations-botanica/IntelMKLFixup", "b77cd912b74846cc3d625d18b15b33e0c68a68f8", "2026-09-20", "GPL-3.0", INTEGRATED,
       "in-memory patch so Intel MKL applications run on AMD processors; Lilu plugin",
       "release 1.0.0 pinned in p1401/community.py, experimental opt-in, AMD processors only"),
    _p("RX4Darwin/AMDRadeonRDNA4.kext", "49f7f20c00dd154384418078f8a09e79c400a06a", "2026-10-12", "BSD-3-Clause", INTEGRATED,
       "RX 9070 / 9070 XT display driver (Lilu plugin over IONDRVFramebuffer), no acceleration",
       "already built from this commit and mirrored by NullMoth (p1401/amd_rdna4.py); experimental opt-in"),
    _p("myvoow/PrimeBridge", "8c08c3e4efa612a49d3c4ce330ef381b9bafdb16", "2026-11-02", "MIT (source, script, docs); NVRMFB patch is NullMoth's PolyForm code",
       DRIVER_IDEA, "internal screen of MUX-less Radeon 680M + NVIDIA laptops: forced HDMI head plus a copy into the firmware framebuffer",
       "release 0.4.8 needs NullMoth 2.6.3 exactly (hard-coded NVRMFB offsets); rebuilt in our driver as NMGopFB (AMD panel provider, 2.9)"),
    _p("watchthelight-labs/WTLIntelGfx", "aac09a43ab77133878222522922b90a8428d5796", "2026-11-06", "BSD-2-Clause for shim/tools; PolyForm-NC for the forks of our code",
       PORT_REVIEW, "i915 on XNU for Meteor Lake and Arrow Lake (Metal, Vulkan, GPU-composited desktop); renamed from XeGfx",
       "its release is one bring-up kext (no accelerator, plugin or installer), so it is not a user package; patches reviewed for NMXGPU"),
    _p("InSnh-Gd/WTLIntelGfx", "5ffc79fb9e53eb820899edd644b83681bea3aa39", "2026-11-01", "BSD-2-Clause", EXCLUDED,
       "fork of watchthelight-labs/WTLIntelGfx", "a copy of the project above (same tree); read once there"),
    _p("watchthelight-labs/XeGfx", "aac09a43ab77133878222522922b90a8428d5796", "2026-11-06", "BSD-2-Clause", EXCLUDED,
       "the earlier name of WTLIntelGfx", "same commit as WTLIntelGfx"),
    _p("Mountainatic/ArrowWhatever", "555fbb2f3c29a1a1b2c5a298ee2107222d28baf4", "2026-11-06", "PolyForm-NC (patches); MIT (scripts, docs)",
       PORT_REVIEW, "ten patches over XeGfx 0.0.44 for Arrow Lake-HX: GGTT zero-copy scanout, 240 Hz HiDPI, Tile4/CCS scanout, colour",
       "patches only (no code of its own to fetch); reviewed for NMXGPU and NMIntelFB, scanout ideas feed the hybrid import path"),
    _p("VedCloud/Meteor-Lake-Xe-LPG-Metal-Graphics", "62de794b8a810c51369901a5b98579a4dfb17db9", "2026-10-30",
       "own licence: Apache-like for the original work only", LINKED,
       "Meteor Lake i915-on-LinuxKPI port with Metal; 6.8 GB repository with 874 binaries",
       "Tahoe Graphics-Audio 0.3.21 (2026-10-30) for the Dell Latitude 5350 (7D45) is linked, fetched from its author; derived from "
       "our tree and assistant-aided, so its patches are still only reviewed for NMXGPU, never merged as is"),
    _p("vedprajapatiunitedkingdom-wq/CoreUltraGraphics", "05b19dc81db6aedcf4058525981f7326f57c04e2", "2026-10-17", "none", EXCLUDED,
       "earlier Meteor Lake attempt by the same author", "no licence file"),
    _p("kitsuneislife/nmx-intel", "b4bb3a0c653248ce125ce7d36b920d216e53c16f", "2026-10-30", "none", NAMED,
       "NMIntelFB patches so a Raptor Lake laptop panel shows frames composited on an NVIDIA GPU",
       "no licence (all rights reserved) and assistant-written (190 commits): named in the build notice for Raptor Lake-P laptops with an NVIDIA card, nothing downloaded; our own NMIntelFB already has copy and import paths"),
    _p("zep245/IrisXe-macos-driver", "c71dffcdfc0fa7b23e694b1066dfa6d6d0ea6b28", "2026-11-06", "PolyForm-NC (fork of our tree)",
       PORT_REVIEW, "Tiger Lake Iris Xe through i915 + ANV: display, Metal, H.264/AV1 decode, HiDPI; fork of our tree",
       "tester-grade, one laptop; overlaps WhateverXe on Tiger Lake. Its video-decode and PSR work is reviewed for NMXGPU"),
    _p("ericek111/vibe-nullmoth-xe3-qemu", "7246d386e94a2f5e8fe4f8a17099d11514b0ae40", "2026-10-18", "none", NAMED,
       "98 patches making NMXGPU drive a Panther Lake SR-IOV virtual function in a QEMU guest (Metal, GL, Vulkan)",
       "no licence (all rights reserved): named in the build notice for Panther Lake, nothing downloaded; patches are not merged until the author grants a licence"),
    _p("luuumi-dev/nullarc", "8aba872560a3c9b7dc7a0ddebfad001c6dddf315", "2026-11-09", "MIT or GPL-2.0 (own code); PolyForm-NC (derived from our tree)",
       LINKED, "Metal on Radeon 780M/760M/740M (Phoenix, Hawk Point) with a 120 Hz display kext and RADV",
       "release 0.4.0-alpha linked for machines with no NVIDIA card: its package installs its own NVMTLDriver.bundle, the "
       "same path as NullMoth's Metal plugin. Alpha, one machine, assistant-aided (83 commits); patches still reviewed for NMXGPU"),
    _p("yt42c2mvn2-cmd/nullarc-760m", "f08b89803c88daf627ef5e551e2b476b77be519d", "2026-11-08", "as nullarc", EXCLUDED,
       "fork of nullarc for a Radeon 760M laptop", "a fork of the project above"),
    _p("Helemen7/RedNavi", "587de1af7bf7685c080139fb298eefa5e63cf7ff", "2026-11-08", "BSD-3-Clause", PORT_REVIEW,
       "RX 7800 XT (Navi 32) display driver on its own DCN 3.2 kext; developer prototype",
       "assistant-aided (263 commits), not installable; read for the DCN bring-up order that NMXGPU's RDNA 3 path needs"),
    _p("JulioNectar/Hackintosh-XPS13Plus-IrisXe-Tahoe", "24450b476d7ca025b83c85d7b8362caf3234d2f2", "2026-11-03",
       "Thou Shalt Not Profit License 1.0", OPTIONAL, "Iris Xe on one Dell laptop through NootedGreen plus the XCPM power fix (EFI, build and install scripts)",
       "assistant-written (75 commits) and free to use, but a distributor must license copies under it: never merged into NullMoth code, never hosted; the build notice gives the author's archive pinned by commit and SHA-256 for a Dell XPS 13 Plus"),
    _p("pongpan-bk/First-Custom-iGPU-Driver-for-Intel-Core-5-120U-on-macOS", "cbf8e3746aa3ef05f9cca959773288e52045a785", "2026-11-13", "none",
       LINKED, "stand-alone Raptor Lake-U (A7AC) kext", "no licence (all rights reserved) and assistant-written (README names its coding tool): "
       "never hosted or merged; its own installer v4.4.121 is linked for A7AC (author targets macOS 12+, Tahoe not shown)"),
    _p("wallali77666-cyber/iris-xe-macos-driver", "9bf31c915e84293e3545bc1d090595799a3234f8", "2026-10-18", "none", EXCLUDED,
       "Tiger Lake scaffold modelled on our tree", "no licence; stubs only (phase D, acceleration, is 'research')"),
    _p("pawan295/AppleIntelTGLDriver.kext", "0da9a50d19502b6b57c31bc07879194b9bb4c24e", "2026-07-30", "none", EXCLUDED,
       "Tiger Lake controller skeleton", "no licence; the author states it has no command submission and no Metal"),
    _p("change-48/xegfx-migrate", "eb07530591ed170545bacf31e5a72dfe29d3b9a0", "2026-11-07", "none", EXCLUDED,
       "scratch patch scripts for an XeGfx migration", "no licence; temporary scripts and 132 MB of build output"),
    _p("belugaa-01/whateverxe-patched", "cb29b1d67f3b8100d78c8d7e7387e007fffea58a", "2026-11-13", "BSD-3-Clause", EXCLUDED,
       "WhateverXe with extra framebuffer patches for a 6-bit eDP panel (Alder Lake-U 46B3); release 0.2.0",
       "verified on one i3-1215U only; upstream WhateverXe 0.8.x covers 46B3 and reworks the eDP path"),
    _p("taingo936-ui/whateverxe-alderlakes", "2373eded960ba6103731d47c0fc9de0d99b52821", "2026-11-03", "BSD-3-Clause", EXCLUDED,
       "WhateverXe fork with an experimental Lenovo LOQ 144 Hz eDP stage", "machine-specific experimental branch of WhateverXe"),
    _p("thatisjigen/whateverxe", "d0b7fb6275ca51fde088fa7e91595462bd457ec9", "2026-11-02", "BSD-3-Clause", EXCLUDED,
       "fork of WhateverXe", "a mirror of upstream (head by b00t0x), no changes of its own"),
    _p("elezorn/whateverxe-tigerlakeh", "db438fdf4d5fe903f5dfbc65537ed3884e2ea980", "2026-11-08", "BSD-3-Clause", EXCLUDED,
       "fork of WhateverXe for Tiger Lake-H", "the same commit as upstream WhateverXe 0.8.0"),
    _p("watchthelight-labs/NvGfx", "04f011e4c671eeda34db87e13bac138e90cffc68", "2026-10-31", "PolyForm-NC", PORT_REVIEW,
       "fork of our NVIDIA driver (the base of XeGfx)", "PolyForm Noncommercial is our own licence, so its patches can go back into NMXGPU and NVRM; reviewed there"),
    _p("emirercan3459/nullmoth-nvidia-audio", "558dc644996fdeb05ff4f80b4e112527d384b9fe", "2026-10-19", "none", NAMED,
       "multi-port HDMI/DP audio and volume for NVIDIA GPUs (NMHDA Lilu plugin)",
       "no licence (all rights reserved) and assistant-written by its own statement; not named in a build notice because it applies to every NVIDIA card and NMXAudio is the supported audio path"),
    _p("tqmane/reims-vgpu", "8f316b5f21908ddeb1e454ce50356ed6e1d2f6cf", "2026-11-01", "GPL-2.0-or-later OR LGPL-3.0-or-later", EXCLUDED,
       "virtual GPU for macOS guests in QEMU", "not a driver for real hardware; 1,641 assistant-aided commits"),
    _p("acidanthera/WhateverGreen", "093e76fec5655001f38b367dd22459c756ee89fa", "2026-09-27", "BSD-3-Clause", EXCLUDED,
       "Lilu graphics patches for supported Intel and AMD GPUs", "already in the engine's kext list; WhateverXe replaces it on Xe-LP"),
    _p("AMD-OSX/AMD_Vanilla", "eaf52ef292abf4ebec899df6d48626569ba50cc6", "2025-10-17", "none", EXCLUDED,
       "AMD processor kernel patches (patches.plist)", "no licence; 1401 writes its own AMD kernel patches (p1401/kernel_patches.py)"),
    _p("LuneFlu/AMDHelper", "b4cabfb762bcecb2866697adc0055a68ff81e5e6", "2024-10-21", "none", EXCLUDED,
       "Ryzen power-limit helper (ryzenadj wrapper)", "no licence; not a graphics driver; last commit 2024"),
    # --- 2026-11-13 census: every iGPU project found that claims Tahoe, read at the commit shown ---------------------------
    _p("wzh4869/Radeon-680M-Hackintosh", "a34b37d2839dff3223315188dad7851ca58060d7", "2026-11-11", "GPL-2.0", PORT_REVIEW,
       "RembrandtGfx: Radeon 680M (rev 02 -> c7 compatibility) with an accelerated Tahoe 26.7.2 desktop, 2560x1600 at 120 Hz, fixed 512 MiB",
       "the only iGPU-only 680M route found; no release to fetch, so it is named for 680M machines without an NVIDIA card; "
       "its revision fix is reviewed for NMXGPU's Rembrandt path. One RedmiBook Pro 14"),
    _p("OscarrWu/780m-hackintosh", "a3a45d9ccc5eee1d1f6cc297eae7c681e7524315", "2026-11-13", "MIT", PORT_REVIEW,
       "Radeon 780M kext with its own PSP/SMU/GMC power-up and RADV Darwin patches, staged bring-up notes",
       "MIT and no release yet; its power-up order is reviewed for NMXGPU's RDNA 3 path beside nullarc"),
    _p("m4j2rpf766-crypto/IntelIGPU-Tahoe", "9baa4bbe36c4a0085efac41d07feb420f841ac6a", "2026-09-28", "GPL-3.0", EXCLUDED,
       "Alder Lake (46A3) display, Metal desktop at ~120 fps on 144 Hz, backlight, HEVC service, GPU stall recovery on Tahoe 25G83",
       "source snapshot without the Apple binaries it needs and no release; WhateverXe already covers 46A3 with a release"),
    _p("wkin-t/IntelIGPU-Tahoe", "9baa4bbe36c4a0085efac41d07feb420f841ac6a", "2026-11-09", "GPL-3.0", EXCLUDED,
       "fork of IntelIGPU-Tahoe", "the same commit as the project above"),
    _p("sgiammori/NootedGreen", "95f81898be65cb9f7b3d370ca78054be4cc8a62d", "2026-05-23", "none", EXCLUDED,
       "Lilu plugin running Apple's Tiger Lake driver on Haswell to Raptor Lake", "no licence, work in progress (still panics), no "
       "release; reaches users only through JulioNectar's project, which is already an optional download"),
    _p("dssoftx/Hackintosh-X1Carbon-G11-IrisXe-Tahoe", "5098a08c68cd03f279670027e8742488011dd245", "2026-10-26", "none", LINKED,
       "JulioNectar's Tahoe Iris Xe stack ported to the ThinkPad X1 Carbon Gen 11 (Raptor Lake-U A7A1), 26.7.1 25G241",
       "a whole EFI plus post-install package for one laptop; release V0.4 linked for that laptop only, never hosted"),
    _p("mschiller890/Hackintosh-X13YogaG2-Iris", "8d88daa046da13426958bcdcea0d751e8b7fd864", "2026-11-13", "none", EXCLUDED,
       "JulioNectar's stack on a ThinkPad X13 Yoga Gen 2 (Tiger Lake)", "its own README says the Tahoe USB stops at EXITBS:START"),
    _p("samranahmad09/WhateverXe-RaptorLakeP", "565252faaf62ff9734d328452ea435c07aa81744", "2026-11-11", "BSD-3-Clause", EXCLUDED,
       "WhateverXe branch for Raptor Lake-P with native panel, Metal, OpenGL, sleep and wake", "no release; its rplp-accel work is upstream's job"),
    _p("akiffurkan/WhateverXe-0xA7A0", "c76768b461d6f49878e62ef6306231ea908f7b29", "2026-11-13", "BSD-3-Clause", EXCLUDED,
       "WhateverXe 0.8.2 built for the XPS 13 Plus A7A0 eDP", "machine build of upstream 0.8.2"),
    _p("TigerShota/WhateverXe", "25da56121126e83aff8da3a34c59bd37098cea66", "2026-11-08", "BSD-3-Clause", EXCLUDED,
       "WhateverXe 0.7.0 for an Alder Lake-H 48 EU (46A3) 120 Hz panel", "machine build of an older upstream"),
    _p("jkbuha/WhateverXe", "09bd397eb40d68ef3c57ba7373bf2321276dfc89", "2026-11-13", "BSD-3-Clause", EXCLUDED,
       "WhateverXe for the XPS 13 Plus 9320 (eDP, hibernate)", "machine branch, no release"),
    _p("dristotle/WhateverXe-ASUS-F15-eDP", "90806abb3874f51490dc0edbc29845bc37a67cf3", "2026-11-13", "BSD-3-Clause", EXCLUDED,
       "WhateverXe 0.8.2 eDP test build for a Tiger Lake-H45 ASUS TUF F15", "machine test build, no release"),
    _p("lcrlcr666/WhateverXe-RGB8", "3afef31f3b93a391f407f43f093b3f41dd39ddbb", "2026-11-13", "BSD-3-Clause", EXCLUDED,
       "WhateverXe 0.8.1 with a forced RGB8 switch (upstream issue 74)", "one switch over upstream, no release"),
    _p("ManasSoni-2009/AlderXe", "e72c2b604123c644ae1af40bdf745689be61a934", "2026-11-12", "none", EXCLUDED,
       "WhateverXe mod for Alder Lake-HX", "no licence, no description of what it changes, no release"),
    _p("Minorli/WhateverXe-Next", "c2a64215ef2ea8fe807f74918a75b4501e49282c", "2026-11-13", "MIT", EXCLUDED,
       "WhateverXe research fork on a Tiger Lake 96 EU, Tahoe 26.7.3", "research only; its author notes GPU queue hangs and forced shutdowns"),
    _p("retropineaple/whateverxe-hp-envy-x360", "3b52397bc6a58cab92c62c57ef506ae3ccdd1fb7", "2026-11-11", "none", EXCLUDED,
       "WhateverXe set-up for an HP Envy x360 (46AA) OLED on Tahoe 26.7.1", "a machine guide; the driver is upstream WhateverXe"),
    _p("longurara/ArcMTL", "3acbe5557b6d7f3ed079bfa65218d9292e130eaa", "2026-11-02", "none", NAMED,
       "Meteor Lake 155H (7D55) display + Metal 3 + Vulkan, or a headless Metal device beside the boot GPU, Tahoe and Sequoia",
       "no licence and no release; XeGfx already covers 7D55, so it is catalogued and not noticed"),
    _p("samwu07/xegfx-thinkbook14plus-mtl", "f85a4d5932e98a0bfce1eaee4334a561d3f20f4a", "2026-11-11", "BSD-2-Clause", PORT_REVIEW,
       "XeGfx on a ThinkBook 14+ 2024 (7D55): GuC band fix, framebuffer move, zero-copy flip, Sequoia 15.8.1",
       "Sequoia only; its GGTT and IOPresentment fixes are reviewed for NMXGPU and NMIntelFB"),
    _p("taqieallah/ThinkPad-E16-ArrowLake-macOS", "e2115d3ed6e06815310e93e2c91c6ee71f18a1f5", "2026-11-13", "BSD-2-Clause", PORT_REVIEW,
       "XeGfx on an Arrow Lake-H 255H (7D51): GPU-composited desktop, GGTT flip, deferred ordering, Tahoe",
       "no release; its K9b ordering and flip work are reviewed for NMXGPU"),
    _p("IT-EXPRESS-Bayern/LunarBridge-Hackintosh", "077fadac2a4bf4a6ad600dc720e25999fa6c01d6", "2026-10-12", "GPL-3.0", EXCLUDED,
       "Lunar Lake Arc 130V (64A0) research on Tahoe", "its own status: Metal and display blocked"),
    _p("nvsaim/mothbridge-630", "89a5348cfb41dd4370023e70b366405cac4f3523", "2026-11-08", "none", NAMED,
       "NVIDIA desktop on the UHD 630 (3E9B) panel of MUX-less Coffee Lake laptops, through NullMoth",
       "no licence and no release: named for 3E9B beside an NVIDIA card; our Hybrid laptop mode covers the same job"),
    _p("medkintos/VP8MetalDecoder", "d50764f8dd96ed86fed4b42de135aa4591724ec2", "2026-11-05", "none", EXCLUDED,
       "VP8/VP9 decode on Metal compute as a VideoToolbox bundle", "not a GPU driver; no licence"),
    _p("shandftk/RenoirDSBFix", "8f8e80e24bf992b04d8d9c4b72628b2a2ac6eb11", "2026-11-11", "MIT", EXCLUDED,
       "dual-source-blend hang fix for Renoir under NootedRed", "Sequoia only, and an add-on to a driver 1401 does not use"),
    _p("kevin8717/TongFang-7840HS-Hackintosh", "6758dda39c6f3b29306cc7f97fe0e9969c4f69ab", "2026-11-08", "MIT", EXCLUDED,
       "an EFI that runs nullarc's PhxBringup on a 780M (15BF) under Tahoe 26.7.2", "a machine EFI; the driver is nullarc, linked above"),
    _p("Harshshah6/PrimeBridge-nomux-hp-victus", "66bbf3b65b28830799bba7220c1e7275496dfc18", "2026-11-12", "MIT (as PrimeBridge)", EXCLUDED,
       "fork of PrimeBridge for an HP Victus", "a copy of PrimeBridge, which our NMGopFB already reimplements"),
    _p("NekoMirra/phoenix-hackintosh-toolkit", "32ee33063dc6d0624a0c3289e87921cf7597a0d3", "2026-11-05", "none", EXCLUDED,
       "SMU and brightness tools for a Phoenix 8845H laptop", "not a GPU driver; no licence"),
)

# --- hardware fingerprints. Upper-case "VVVV-DDDD" as the scan writes them. ---------------------------------------------

# The Meteor Lake and Arrow Lake IDs the XeGfx README lists as running (its compatibility table).
XEGFX_IDS = ("8086-7D40", "8086-7D41", "8086-7D45", "8086-7D51", "8086-7D55", "8086-7D67", "8086-7DD1", "8086-7DD5")
# PrimeBridge matches only the Rembrandt / Rembrandt-R Radeon 680M (its Info.plist).
PRIMEBRIDGE_IDS = ("1002-1681",)
# Phoenix and Hawk Point (gfx1103): nullarc's kext personality lists 1900, 15BF, 15C8 (and 164E, a Raphael ID that the
# engine classifies separately and that nullarc does not describe as supported hardware, so it is left out here).
NULLARC_IDS = ("1002-1900", "1002-15BF", "1002-15C8")

# Dell XPS 13 Plus (9320), the machine the XPS13Plus project is built on: its Raptor Lake-P GPU and the board name.
XPS13PLUS_IDS = ("8086-A7A0",)
XPS13PLUS_BOARDS = ("xps 13 9320", "xps 13 plus")
# Raptor Lake-P Iris Xe with an NVIDIA card: the one GPU nmx-intel documents (a7a8). Raptor Lake-U A7AC: MyIntelGPU.
NMXINTEL_IDS = ("8086-A7A8",)
MYINTELGPU_IDS = ("8086-A7AC",)
# 2026-11-13 census. Meteor Lake-P 7D45 in a Dell Latitude 5350 (VedCloud's packages are built for that laptop's profile).
VEDCLOUD_IDS = ("8086-7D45",)
VEDCLOUD_BOARDS = ("latitude 5350",)
# Raptor Lake-U A7A1 in a ThinkPad X1 Carbon Gen 11 (machine types 21HM / 21HN), the laptop dssoftx's EFI is built for.
X1C11_IDS = ("8086-A7A1",)
X1C11_BOARDS = ("x1 carbon gen 11", "21hm", "21hn")
# Radeon 680M with no NVIDIA card (with one, PrimeBridge / Hybrid laptop mode is the route): RembrandtGfx.
RADEON680M_IDS = ("1002-1681",)
# Coffee Lake UHD 630 driving the panel of a MUX-less laptop with an NVIDIA card: mothbridge-630.
MOTHBRIDGE_IDS = ("8086-3E9B",)
PANTHER_LAKE_IDS = ("8086-B080", "8086-B081", "8086-B082", "8086-B083", "8086-B08F", "8086-B090", "8086-B0A0", "8086-B0B0")

# The author's archive of the commit read, for the user to fetch. 1401 never downloads or hosts it. Verify with
# shasum -a 256 before use. Thou Shalt Not Profit License 1.0: free to use; whoever distributes copies must license them under it.
OPTIONAL_DOWNLOADS = {
    "JulioNectar/Hackintosh-XPS13Plus-IrisXe-Tahoe": {
        "url": "https://github.com/JulioNectar/Hackintosh-XPS13Plus-IrisXe-Tahoe/archive/24450b476d7ca025b83c85d7b8362caf3234d2f2.tar.gz",
        "size": 48295678, "sha256": "472bca121f24cb67ec89fd6f14618ca07aa7048cd338a91b284c82bbad7bb64c",
        "licence": "Thou Shalt Not Profit License 1.0",
    },
}

# The author's own release files for the LINKED projects: fetched on the user's machine from the author, never hosted by
# NullMoth. Size and SHA-256 were measured on the files as published on the date in the PROJECTS row; any other bytes are
# refused. "tahoe" says whether the author shows it running on macOS 26.
LINKED_DOWNLOADS = {
    "luuumi-dev/nullarc": {
        "tag": "v0.4.0-alpha", "tahoe": True,
        "files": (("https://github.com/luuumi-dev/nullarc/releases/download/v0.4.0-alpha/nullarc-0.4.0-alpha.zip",
                   55827407, "dcfeaa04917719683487b24259933b6ea84513a840cc862a68cd91205af47bbb"),),
    },
    "VedCloud/Meteor-Lake-Xe-LPG-Metal-Graphics": {
        "tag": "dell-packages-20261030", "tahoe": True,
        "files": (("https://github.com/VedCloud/Meteor-Lake-Xe-LPG-Metal-Graphics/releases/download/dell-packages-20261030/"
                   "Tahoe-Graphics-Audio-0.3.21-20261030.tar.gz",
                   95400938, "857afd7048634087e33c848d14c1f0c1d3922fa51173196f4acdfa0ee1944e87"),),
    },
    "pongpan-bk/First-Custom-iGPU-Driver-for-Intel-Core-5-120U-on-macOS": {
        "tag": "v4.4.121", "tahoe": False,
        "files": (("https://github.com/pongpan-bk/First-Custom-iGPU-Driver-for-Intel-Core-5-120U-on-macOS/releases/download/v4.4.121/"
                   "MyIntelGPU-4.4.120.pkg", 73259, "fa375047c3ff541f2dbe1fa7b725829b4aa9166fcaf192e4f35cbfd342151c64"),),
    },
    "dssoftx/Hackintosh-X1Carbon-G11-IrisXe-Tahoe": {
        "tag": "V0.4", "tahoe": True,
        "files": (("https://github.com/dssoftx/Hackintosh-X1Carbon-G11-IrisXe-Tahoe/releases/download/V0.4/EFI-Install.zip",
                   16145391, "75799dd12164c26de34c911177754ee946469d218e3bbd134cccabfdf3782f84"),
                  ("https://github.com/dssoftx/Hackintosh-X1Carbon-G11-IrisXe-Tahoe/releases/download/V0.4/EFI-PostInstall.zip",
                   30795853, "b9b86de640ae7d3b8d74a5c7c7b18226b5d96728fe7fd12a19649cb92afdd9ca")),
    },
}


def _files(repo):
    """The pinned files of a LINKED project as one line per file for a build notice."""
    return " ".join("%s (size %d bytes, SHA-256 %s)" % f for f in LINKED_DOWNLOADS[repo]["files"])


_NOTES = {
    "xegfx": ("Graphics: {name} ({family}) - a developer-stage community driver for this GPU exists: XeGfx (WTLIntelGfx by "
              "watchthelight, BSD-2 for its core, PolyForm Noncommercial for the parts forked from NullMoth). Its author reports "
              "Metal and an accelerated desktop on Arrow Lake and Meteor Lake laptops, and an open kernel panic. It is not part of "
              "this build and NullMoth has not tested it; NullMoth's AMD / Intel test driver is the supported route."),
    "primebridge": ("Graphics: {name} drives this laptop's internal screen and macOS has no driver for it, so the NVIDIA card "
                    "has no screen of its own here. The community project PrimeBridge (myvoow, MIT) copies the NVIDIA desktop "
                    "to this exact GPU (1002:1681); its own release works with NullMoth 2.6.3 only and is not part of this build. "
                    "NullMoth 2.9 has the same method built in: turn on Hybrid laptop mode in the Mac app after installing "
                    "(it adds the AMD panel driver NMGopFB), or use an external monitor on the NVIDIA card."),
    "xps13plus": ("Graphics: {name} on a Dell XPS 13 Plus - the community project Hackintosh-XPS13Plus-IrisXe-Tahoe (JulioNectar) "
                  "reports Iris Xe acceleration on this laptop on macOS Tahoe 26.7.1, plus a CPU power fix. Its licence (Thou Shalt Not "
                  "Profit License 1.0) lets you use it free; NullMoth does not include or host it. Fetch it yourself from its author: "
                  "{url} (size {size} bytes, SHA-256 {sha256}; check it with shasum -a 256 first). It builds and installs its own "
                  "EFI: keep your current one."),
    "nmxintel": ("Graphics: {name} - a community project, nmx-intel (kitsuneislife), shows an NVIDIA-rendered desktop on this kind of "
                 "Raptor Lake laptop panel; tested by its author on one laptop. It has no licence, so NullMoth cannot include or "
                 "download it: https://github.com/kitsuneislife/nmx-intel. NullMoth's own Hybrid laptop mode (Mac app) covers the "
                 "same job."),
    "myintelgpu": ("Graphics: {name} - a community project (pongpan-bk) writes a kernel driver for this Raptor Lake-U GPU. It has no "
                   "licence, so NullMoth cannot include or download it: "
                   "https://github.com/pongpan-bk/First-Custom-iGPU-Driver-for-Intel-Core-5-120U-on-macOS. Unreviewed by NullMoth."),
    "xe3": ("Graphics: {name} (Panther Lake, Xe3) - a community project (ericek111) drives this GPU with NullMoth's AMD / Intel test "
            "driver in a virtual machine. It has no licence, so NullMoth cannot include or download it: "
            "https://github.com/ericek111/vibe-nullmoth-xe3-qemu."),
    "nullarc": ("Graphics: {name} ({family}) - a community project, nullarc (luuumi-dev), reports Metal on this family of AMD "
                "Phoenix and Hawk Point graphics on macOS Tahoe, tested by its author on one machine, alpha, with parts "
                "licensed PolyForm Noncommercial. NullMoth does not include or host it and has not tested it. Its release, "
                "fetched from its author: {files}; check it with shasum -a 256 first."),
    "nullarc_nvidia": ("Graphics: {name} ({family}) - the community project nullarc (luuumi-dev) drives this GPU, but its package "
                       "installs its own NVMTLDriver.bundle at the same path as NullMoth's Metal driver, so on this machine it would "
                       "replace the driver for your NVIDIA card. Do not install it here; NullMoth's Hybrid laptop mode is the route."),
    "myintelgpu": ("Graphics: {name} - a community project (pongpan-bk) writes a kernel driver for this Raptor Lake-U GPU. It has no "
                   "licence, so NullMoth does not include, host or review it; its author targets macOS 12 and later and does not show "
                   "it on Tahoe. Its own installer, fetched from its author: {files}. Page: "
                   "https://github.com/pongpan-bk/First-Custom-iGPU-Driver-for-Intel-Core-5-120U-on-macOS"),
    "vedcloud": ("Graphics: {name} on a Dell Latitude 5350 - the community project Meteor-Lake-Xe-LPG-Metal-Graphics (VedCloud) "
                 "reports Metal, Vulkan and an accelerated desktop on this laptop on macOS Tahoe 26.7.1. NullMoth does not include, "
                 "host or test it. Its Tahoe package, fetched from its author: {files}; check it with shasum -a 256 first."),
    "x1c11": ("Graphics: {name} on a ThinkPad X1 Carbon Gen 11 - the community project Hackintosh-X1Carbon-G11-IrisXe-Tahoe "
              "(dssoftx, a port of JulioNectar's work) reports Iris Xe acceleration on this laptop on macOS Tahoe 26.7.1 (25G241 only). "
              "It replaces your EFI: keep your current one. NullMoth does not include or host it. From its author: {files}"),
    "radeon680m": ("Graphics: {name} - a community project, RembrandtGfx (wzh4869, GPL-2.0), reports an accelerated desktop on a "
                   "Radeon 680M on macOS Tahoe 26.7.2 (one RedmiBook Pro 14). It has no release yet, so NullMoth includes and "
                   "downloads nothing: https://github.com/wzh4869/Radeon-680M-Hackintosh"),
    "mothbridge": ("Graphics: {name} drives this laptop's panel - a community project, mothbridge-630 (nvsaim), shows the NVIDIA "
                   "desktop on the UHD 630 panel of MUX-less Coffee Lake laptops. It has no licence and no release, so NullMoth "
                   "cannot include or download it: https://github.com/nvsaim/mothbridge-630. NullMoth's Hybrid laptop mode (Mac app) "
                   "covers the same job."),
}


def _gpus(report):
    return {n: g for n, g in ((report or {}).get("GPU") or {}).items() if isinstance(g, dict)}


def _id(gpu):
    return str(gpu.get("Device ID") or "").upper()


def options(report):
    """-> list of {"project", "action", "gpu", "text"} for the community projects that target hardware in this scan.
    action is "mac-app" (WhateverXe, offered by the 1401 Mac app after install; the Intel Xe build notice already says so)
    or "pointer" (named in the build notice, nothing installed)."""
    out = []
    gpus = _gpus(report)
    has_nvidia = any(_id(g).startswith("10DE-") for g in gpus.values())
    for name, g in gpus.items():
        did = _id(g)
        c = intel_gpu.classify(g)
        if c and c[1] == intel_gpu.WHATEVERXE:
            out.append({"project": "b00t0x/WhateverXe", "action": "mac-app", "gpu": name, "text": None})
        if did in XEGFX_IDS:
            out.append({"project": "watchthelight-labs/WTLIntelGfx", "action": "pointer", "gpu": name,
                        "text": _NOTES["xegfx"].format(name=name, family=c[0] if c else "Intel Xe-LPG")})
        if did in PRIMEBRIDGE_IDS and has_nvidia:
            out.append({"project": "myvoow/PrimeBridge", "action": "pointer", "gpu": name,
                        "text": _NOTES["primebridge"].format(name=name)})
        board = str(((report or {}).get("Motherboard") or {}).get("Name", "")).lower()
        if did in XPS13PLUS_IDS and any(b in board for b in XPS13PLUS_BOARDS):
            d = OPTIONAL_DOWNLOADS["JulioNectar/Hackintosh-XPS13Plus-IrisXe-Tahoe"]
            out.append({"project": "JulioNectar/Hackintosh-XPS13Plus-IrisXe-Tahoe", "action": "pointer", "gpu": name,
                        "text": _NOTES["xps13plus"].format(name=name, **d)})
        if did in NMXINTEL_IDS and has_nvidia:
            out.append({"project": "kitsuneislife/nmx-intel", "action": "pointer", "gpu": name, "text": _NOTES["nmxintel"].format(name=name)})
        if did in MYINTELGPU_IDS:
            r = "pongpan-bk/First-Custom-iGPU-Driver-for-Intel-Core-5-120U-on-macOS"
            out.append({"project": r, "action": "pointer", "gpu": name, "text": _NOTES["myintelgpu"].format(name=name, files=_files(r))})
        if did in PANTHER_LAKE_IDS:
            out.append({"project": "ericek111/vibe-nullmoth-xe3-qemu", "action": "pointer", "gpu": name, "text": _NOTES["xe3"].format(name=name)})
        if did in NULLARC_IDS:
            key = "nullarc_nvidia" if has_nvidia else "nullarc"
            out.append({"project": "luuumi-dev/nullarc", "action": "pointer", "gpu": name,
                        "text": _NOTES[key].format(name=name, family="Phoenix / Hawk Point, RDNA 3", files=_files("luuumi-dev/nullarc"))})
        if did in VEDCLOUD_IDS and any(b in board for b in VEDCLOUD_BOARDS):
            r = "VedCloud/Meteor-Lake-Xe-LPG-Metal-Graphics"
            out.append({"project": r, "action": "pointer", "gpu": name, "text": _NOTES["vedcloud"].format(name=name, files=_files(r))})
        if did in X1C11_IDS and any(b in board for b in X1C11_BOARDS):
            r = "dssoftx/Hackintosh-X1Carbon-G11-IrisXe-Tahoe"
            out.append({"project": r, "action": "pointer", "gpu": name, "text": _NOTES["x1c11"].format(name=name, files=_files(r))})
        if did in RADEON680M_IDS and not has_nvidia:
            out.append({"project": "wzh4869/Radeon-680M-Hackintosh", "action": "pointer", "gpu": name,
                        "text": _NOTES["radeon680m"].format(name=name)})
        if did in MOTHBRIDGE_IDS and has_nvidia:
            out.append({"project": "nvsaim/mothbridge-630", "action": "pointer", "gpu": name, "text": _NOTES["mothbridge"].format(name=name)})
    return out


def notes(report):
    """The build notices for the pointer projects (WhateverXe is described by intel_gpu.notes)."""
    return [o["text"] for o in options(report) if o["action"] == "pointer"]
