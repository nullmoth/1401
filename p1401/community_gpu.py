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
- NAMED: a useful driver with no licence (all rights reserved). 1401 names it in the build notice with a link to the
  author's page for matching hardware, and downloads or redistributes nothing. docs/COMMUNITY-LICENCE-REQUEST.md asks the
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

INTEGRATED, DRIVER_IDEA, PORT_REVIEW, OPTIONAL, NAMED, EXCLUDED = ("integrated", "driver-idea", "port-review", "optional-download",
                                                                   "named-only", "excluded")
VERDICTS = (INTEGRATED, DRIVER_IDEA, PORT_REVIEW, OPTIONAL, NAMED, EXCLUDED)


def _p(repo, commit, date, licence, verdict, what, why):
    return {"repo": repo, "commit": commit, "date": date, "licence": licence, "verdict": verdict, "what": what, "why": why}


# commit = the head of the default branch when it was read (2026-11-08), except where the row says a release tag.
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
       "own licence: Apache-like for the original work only", PORT_REVIEW,
       "Meteor Lake i915-on-LinuxKPI port with Metal; 6.8 GB repository with 874 binaries",
       "derived from our tree; the licence excludes every file derived from a third-party component, which is most of it; assistant-aided"),
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
       PORT_REVIEW, "Metal on Radeon 780M/760M/740M (Phoenix, Hawk Point) with a 120 Hz display kext and RADV",
       "alpha, one machine, assistant-aided (83 commits); its Phoenix bring-up and RADV patches are reviewed for NMXGPU"),
    _p("yt42c2mvn2-cmd/nullarc-760m", "f08b89803c88daf627ef5e551e2b476b77be519d", "2026-11-08", "as nullarc", EXCLUDED,
       "fork of nullarc for a Radeon 760M laptop", "a fork of the project above"),
    _p("Helemen7/RedNavi", "587de1af7bf7685c080139fb298eefa5e63cf7ff", "2026-11-08", "BSD-3-Clause", PORT_REVIEW,
       "RX 7800 XT (Navi 32) display driver on its own DCN 3.2 kext; developer prototype",
       "assistant-aided (263 commits), not installable; read for the DCN bring-up order that NMXGPU's RDNA 3 path needs"),
    _p("JulioNectar/Hackintosh-XPS13Plus-IrisXe-Tahoe", "24450b476d7ca025b83c85d7b8362caf3234d2f2", "2026-11-03",
       "Thou Shalt Not Profit License 1.0", OPTIONAL, "Iris Xe on one Dell laptop through NootedGreen plus the XCPM power fix (EFI, build and install scripts)",
       "assistant-written (75 commits) and free to use, but a distributor must license copies under it: never merged into NullMoth code, never hosted; the build notice gives the author's archive pinned by commit and SHA-256 for a Dell XPS 13 Plus"),
    _p("pongpan-bk/First-Custom-iGPU-Driver-for-Intel-Core-5-120U-on-macOS", "f8a98b7344241db69dc9cdd850ccbf65e62bf5c0", "2026-11-04", "none",
       NAMED, "stand-alone Raptor Lake-U (A7AC) kext", "no licence (all rights reserved) and assistant-written (README names its coding tool): named in the build notice for A7AC, nothing downloaded"),
    _p("wallali77666-cyber/iris-xe-macos-driver", "9bf31c915e84293e3545bc1d090595799a3234f8", "2026-10-18", "none", EXCLUDED,
       "Tiger Lake scaffold modelled on our tree", "no licence; stubs only (phase D, acceleration, is 'research')"),
    _p("pawan295/AppleIntelTGLDriver.kext", "0da9a50d19502b6b57c31bc07879194b9bb4c24e", "2026-07-30", "none", EXCLUDED,
       "Tiger Lake controller skeleton", "no licence; the author states it has no command submission and no Metal"),
    _p("change-48/xegfx-migrate", "eb07530591ed170545bacf31e5a72dfe29d3b9a0", "2026-11-07", "none", EXCLUDED,
       "scratch patch scripts for an XeGfx migration", "no licence; temporary scripts and 132 MB of build output"),
    _p("belugaa-01/whateverxe-patched", "1ac73a39359107727c58c08ee54e83abd985f964", "2026-11-06", "BSD-3-Clause", EXCLUDED,
       "two-check patch to WhateverXe 0.6.1 for a 6-bit eDP panel (Alder Lake-U 46B3)",
       "targets 0.6.1, verified on one machine; WhateverXe 0.8.0 reworks the eDP path, so the patch no longer applies"),
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
)

# --- hardware fingerprints. Upper-case "VVVV-DDDD" as the scan writes them. ---------------------------------------------

# The Meteor Lake and Arrow Lake IDs the XeGfx README lists as running (its "Does it work on my machine?" table).
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
                "licensed PolyForm Noncommercial. It is not part of this build and NullMoth has not tested it."),
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
            out.append({"project": "pongpan-bk/First-Custom-iGPU-Driver-for-Intel-Core-5-120U-on-macOS", "action": "pointer", "gpu": name,
                        "text": _NOTES["myintelgpu"].format(name=name)})
        if did in PANTHER_LAKE_IDS:
            out.append({"project": "ericek111/vibe-nullmoth-xe3-qemu", "action": "pointer", "gpu": name, "text": _NOTES["xe3"].format(name=name)})
        if did in NULLARC_IDS:
            out.append({"project": "luuumi-dev/nullarc", "action": "pointer", "gpu": name,
                        "text": _NOTES["nullarc"].format(name=name, family="Phoenix / Hawk Point, RDNA 3")})
    return out


def notes(report):
    """The build notices for the pointer projects (WhateverXe is described by intel_gpu.notes)."""
    return [o["text"] for o in options(report) if o["action"] == "pointer"]
