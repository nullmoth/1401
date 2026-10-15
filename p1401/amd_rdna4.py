"""RDNA 4 (Navi 48, RX 9070 / 9070 XT) display support.

macOS has no driver for RDNA 4: Apple's AMD support ends at RDNA 2 (Navi 2x), and the GPU cannot be spoofed as an older
one. A user with an RX 9070 therefore installs macOS on the firmware framebuffer (basic display) and otherwise gets no
display driver at all. The community project RX4Darwin/AMDRadeonRDNA4 (BSD-3) fills exactly that gap: a Lilu plugin that
extends Apple's generic IONDRVFramebuffer at runtime - the same mechanism WhateverGreen and NootRX use - to drive the
Navi 48 display engine (EDID over DP AUX / HDMI DDC, mode switching, a second display, hot-plug). It is a *display*
driver: rendering stays software, so this is not acceleration, and users report roughly 1080p-class use. The notice
says all of that.

Upstream ships no release asset, so - exactly as 1401 builds every other third-party kext it needs - the kext is built
from a pinned commit (on the build Mac, cross-compiled for x86_64, min macOS 11.0), hosted with its BSD-3 licence file, and
fetched at build time by size + SHA-256 through the same mirror as the rest (p1401/mirror.py records the bytes). The
engine's kext picker takes a direct download_info={"url","sha256"} as well as a GitHub repo, so no download plumbing is
added here.

BSD-3 permits redistribution of the built binary with the copyright notice and licence, which the packaged archive
carries (LICENSE-AMDRadeonRDNA4.txt). The kext claims only the two Navi 48 device IDs it actually handles (0x7550 RX
9070/9070 XT, 0x7551 R9700); it is turned on only when the scan shows one of them, so no other card ever loads it.
"""

# The two Navi 48 PCI device IDs the kext hooks (src/plugin.cpp): 0x7550 RX 9070/9070 XT, 0x7551 R9700. Upper-case
# "VENDOR-DEVICE" to match the scan and upstream pci_data. Navi 44 (RX 9060) is NOT handled by this kext and is not here.
NAVI48_IDS = ["1002-7550", "1002-7551"]

KEXT = "AMDRadeonRDNA4"

# The exact bytes built on the build Mac from the pinned commit (cross-compiled x86_64, min macOS 11.0). "url" is where the
# release hosts them; mirror.json records the same url -> {sha256,size} so a GitHub-blocked network gets them from the
# nullmothsystems.com mirror, byte-verified. If the host is unreachable and the bytes are not in the mirror manifest,
# the kext is simply not added (apply_kexts is fail-safe) - the RX 9070 still installs on the firmware framebuffer.
COMMIT = "49f7f20c00dd154384418078f8a09e79c400a06a"
PACKAGE = {
    "version": "0.1.0",
    "url": "https://github.com/nullmoth/amd-rdna4-macos/releases/download/v0.1.0-49f7f20c/AMDRadeonRDNA4-0.1.0-49f7f20c.zip",
    "sha256": "ac147a6ae7dc0e7768b48d122978d8debff4862b408fdb485339ce9757763e34",
    "size": 320980,
}

NOTICE = (
    "Graphics: AMD Radeon RX 9070 (RDNA 4 / Navi 48) - macOS has no built-in driver, so this build adds the community "
    "AMDRadeonRDNA4 display driver (RX4Darwin, BSD-3, built from a pinned source commit). It is a display driver only: "
    "it gives the monitor its real resolutions over EDID, mode switching and a second display, but there is no graphics "
    "acceleration (rendering is in software, roughly 1080p-class). It is experimental. To install macOS on the plain "
    "firmware framebuffer without it, remove AMDRadeonRDNA4.kext from the EFI."
)


def applies(hardware_report):
    """True when the scan found a Navi 48 GPU this kext handles."""
    for props in (hardware_report.get("GPU") or {}).values():
        if isinstance(props, dict) and (props.get("Device ID") or "").upper() in NAVI48_IDS:
            return True
    return False


def register():
    """Add the AMDRadeonRDNA4 kext to the loaded engine's dataset, fetched by direct URL + SHA-256 (no GitHub release
    exists). Idempotent. Importable only after the engine is on sys.path."""
    from Scripts.datasets import kext_data  # noqa: PLC0415

    if KEXT in kext_data.kext_index_by_name:
        return
    k = kext_data.KextInfo(
        name=KEXT,
        description="AMD RDNA 4 (RX 9070 / Navi 48) display driver - community, experimental, no acceleration",
        category="Graphics",
        requires_kexts=["Lilu"],   # a Lilu plugin: loads after Lilu.kext
        min_darwin_version=(20, 0, 0),  # built against the macOS 11 (Big Sur) KPI
        github_repo={},
        download_info={"url": PACKAGE["url"], "sha256": PACKAGE["sha256"]},
    )
    kext_data.kexts.append(k)
    kext_data.kext_index_by_name[KEXT] = len(kext_data.kexts) - 1


def apply_kexts(ocpe, customization, macos_version, notices):
    """Turn on AMDRadeonRDNA4 when the machine has a Navi 48 GPU, and add the honest notice. Fail-safe: any problem is
    reported as a notice, never raised, so it can never turn a good build into a failed one (the card still installs on
    the firmware framebuffer without the kext)."""
    try:
        if not applies(customization):
            return
        from Scripts.datasets import kext_data  # noqa: PLC0415
        idx = kext_data.kext_index_by_name.get(KEXT)
        if idx is None:
            return
        ocpe.k.check_kext(idx, macos_version)
        notices.append(NOTICE)
    except Exception as e:  # noqa: BLE001 - a GPU add-on must never break the whole build
        notices.append(f"AMD RDNA 4 display driver could not be applied: {type(e).__name__}: {e}")
