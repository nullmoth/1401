"""AMD GPU family classification: turns a scanned GPU's PCI device ID into the macOS path 1401 will take for it.

The scan records each GPU as "Device ID": "VVVV-DDDD" (PCI vendor-device, upper hex) and "Subsystem ID". For AMD
(vendor 1002) the 16-bit device ID names the ASIC, and the ASIC decides whether macOS has a driver at all:

- Polaris, Vega, and every Navi 1x/2x card is driven by Apple's own AMD driver - full acceleration after install.
- Navi 3x (RDNA 3, RX 7000) and Navi 4x (RDNA 4, RX 9070/9060) have no Apple driver. macOS installs and runs on the
  firmware framebuffer (basic display, no acceleration); acceleration is only an opt-in/experimental route.
- AMD APU graphics (Vega or RDNA integrated in a Ryzen) have no Apple driver either; the community NootedRed kext
  covers the Vega ones, but its licence stops 1401 from bundling it (policy.EXCLUDED_KEXTS).
- Pre-Polaris GCN (Tahiti..Fiji) was dropped by modern macOS; those cards get an older macOS or basic display.

Every device-id range here is from the Linux amdgpu pci id tables (drivers/gpu/drm/amd/amdgpu + include/drm/drm_pciids),
cross-checked against the AMD device IDs seen in real field uploads (support-cycle, 2026-10-14): Polaris 67EF, Cape Verde
683F, Mars 6660, Navi 10 731F, Navi 14 7340, Navi 21 73BF, Navi 22 73DF, Navi 23 73EF/73FF, Navi 32 747E, Navi 33 7480,
Navi 48 7550, and APUs 15D8/1636/1638/164E/1681/15BF/150E/13C0. First matching range wins, so narrower ASIC ranges
that sit inside a wider one are listed first.

This module only classifies and explains; it changes no config. policy.py and nullmoth.py own the OpenCore side.
"""

# Path each family takes. The value is what the user is told they will get.
NATIVE = "full"                # Apple's own AMD driver: full acceleration.
NATIVE_LEGACY = "legacy"       # Native only on an older macOS; basic display on 15/26.
RDNA3 = "rdna3"                # No Apple driver (RX 7000); basic display, opt-in test driver for acceleration.
RDNA4 = "rdna4"                # No Apple driver (RX 9070/9060); basic display, experimental community driver only.
APU_VEGA = "apu-vega"          # Ryzen Vega iGPU; NootedRed covers it but is not bundled; basic display otherwise.
APU_RDNA = "apu-rdna"          # Ryzen RDNA2/3 iGPU; no proven community driver; basic display.
UNKNOWN = "unknown"            # An AMD device ID no table here recognizes; basic display, ask the user to report it.

AMD_VENDOR = "1002"

# (lo, hi, family label, path). Inclusive 16-bit device-id ranges, narrowest first.
_RANGES = (
    # --- Pre-Polaris GCN: dropped by modern macOS (Bonaire is listed before Mars: its range sits inside Mars's) ---
    (0x6640, 0x665F, "Bonaire (GCN 2)", NATIVE_LEGACY),
    (0x6600, 0x6667, "Mars / Oland / Hainan (GCN 1)", NATIVE_LEGACY),
    (0x6780, 0x679F, "Tahiti (GCN 1)", NATIVE_LEGACY),
    (0x6800, 0x681F, "Pitcairn (GCN 1)", NATIVE_LEGACY),
    (0x6820, 0x684F, "Cape Verde (GCN 1)", NATIVE_LEGACY),
    (0x67A0, 0x67BF, "Hawaii (GCN 2)", NATIVE_LEGACY),
    (0x6900, 0x693F, "Tonga / Iceland (GCN 3)", NATIVE_LEGACY),
    (0x7300, 0x730F, "Fiji (GCN 3)", NATIVE_LEGACY),
    # --- Polaris / Vega: native on current macOS ---
    (0x66A0, 0x66AF, "Vega 20 - Radeon VII (GCN 5)", NATIVE),
    (0x67C0, 0x67DF, "Polaris 10/20/30 - RX 470-590", NATIVE),
    (0x67E0, 0x67FF, "Polaris 11/21 - RX 460-560", NATIVE),
    (0x6FDF, 0x6FDF, "Polaris 20 - RX 580 2048SP", NATIVE),
    (0x6980, 0x699F, "Polaris 12 - RX 540-550", NATIVE),
    (0x6860, 0x687F, "Vega 10 - RX Vega 56/64", NATIVE),
    (0x69A0, 0x69AF, "Vega 12 - Pro Vega 16/20", NATIVE),
    # --- Navi 1x / 2x (RDNA 1/2): native ---
    (0x7310, 0x731F, "Navi 10 - RX 5600/5700", NATIVE),
    (0x7340, 0x734F, "Navi 14 - RX 5300/5500", NATIVE),
    (0x7360, 0x736F, "Navi 12 - Pro 5600M", NATIVE),
    (0x73A0, 0x73BF, "Navi 21 - RX 6800/6900", NATIVE),
    (0x73C0, 0x73DF, "Navi 22 - RX 6700", NATIVE),
    (0x73E0, 0x73FF, "Navi 23 - RX 6600/6650", NATIVE),
    (0x7420, 0x743F, "Navi 24 - RX 6400/6500", NATIVE),
    # --- Navi 3x (RDNA 3): no Apple driver ---
    (0x7448, 0x745F, "Navi 31 - RX 7900", RDNA3),
    (0x7470, 0x747F, "Navi 32 - RX 7700/7800", RDNA3),
    (0x7480, 0x749F, "Navi 33 - RX 7600", RDNA3),
    # --- Navi 4x (RDNA 4): no Apple driver; experimental community only ---
    (0x7550, 0x756F, "Navi 48 - RX 9070", RDNA4),
    (0x7590, 0x75AF, "Navi 44 - RX 9060", RDNA4),
)

# APU integrated graphics (scattered device IDs, not contiguous). NootedRed (ChefKiss) covers the Vega ones; its
# RDNA2/3 iGPU support is partial or unproven in the field (users report no acceleration), so those stay basic display.
_APUS = {
    0x15DD: ("Raven Ridge (Vega iGPU)", APU_VEGA),
    0x15D8: ("Picasso / Raven2 (Vega iGPU)", APU_VEGA),
    0x15E7: ("Barcelo (Vega iGPU)", APU_VEGA),
    0x1636: ("Renoir (Vega iGPU)", APU_VEGA),
    0x164C: ("Lucienne (Vega iGPU)", APU_VEGA),
    0x1638: ("Cezanne (Vega iGPU)", APU_VEGA),
    0x163F: ("Van Gogh (RDNA 2 iGPU)", APU_RDNA),
    0x1506: ("Mendocino (RDNA 2 iGPU)", APU_RDNA),
    0x1681: ("Rembrandt (RDNA 2 iGPU)", APU_RDNA),
    0x164E: ("Raphael (RDNA 2 iGPU)", APU_RDNA),
    0x13C0: ("Granite Ridge (RDNA 2 iGPU)", APU_RDNA),
    0x15BF: ("Phoenix / Hawk Point (RDNA 3 iGPU)", APU_RDNA),
    0x15C8: ("Phoenix 2 (RDNA 3 iGPU)", APU_RDNA),
    0x150E: ("Strix Point (RDNA 3.5 iGPU)", APU_RDNA),
    0x1586: ("Strix Halo (RDNA 3.5 iGPU)", APU_RDNA),
    0x1900: ("Strix Halo (RDNA 3.5 iGPU)", APU_RDNA),
}

# The community RDNA 4 projects, named so the notice can point users at them. Both are source-only (no release asset to
# pin, checked 2026-10-15) and the authors report roughly 1080p, so 1401 does not bundle or auto-install either one.
RDNA4_COMMUNITY = ("RX4Darwin/AMDRadeonRDNA4 (BSD-3)", "Almosst-DEV/Cobalt64 (MIT)")


def device_id(gpu):
    """The 16-bit AMD device ID as an int, or None if this GPU is not an AMD (vendor 1002) device."""
    did = (gpu.get("Device ID") or "").upper()
    if not did.startswith(AMD_VENDOR + "-"):
        return None
    try:
        return int(did.split("-", 1)[1], 16)
    except (ValueError, IndexError):
        return None


def classify(gpu):
    """Return (family_label, path) for an AMD GPU, or None when it is not an AMD GPU.

    An AMD device ID that no table recognizes returns (label, UNKNOWN) rather than None, so an unclassified card is
    reported (basic display) instead of silently treated as having a driver. A '0000' placeholder ID from a card the
    scan could not read (report.py) is UNKNOWN too."""
    dev = device_id(gpu)
    if dev is None:
        return None
    if dev in _APUS:
        return _APUS[dev]
    for lo, hi, label, path in _RANGES:
        if lo <= dev <= hi:
            return label, path
    return ("AMD GPU %04X" % dev, UNKNOWN)


# User-facing notice per path. Each starts with "Graphics:" so the Windows app's support-notice filter shows it before
# the build (MainForm.IsSupportNotice). {name} is the scan's name for the card, {family} the label from classify().
_NOTE = {
    NATIVE: "Graphics: {name} ({family}) is supported by Apple's own AMD driver - full acceleration after macOS installs.",
    NATIVE_LEGACY: ("Graphics: {name} ({family}) is an older AMD card; current macOS (15/26) dropped its driver. "
                    "Choose an older macOS for acceleration, or it runs on the firmware framebuffer: the desktop and "
                    "apps work, but with no graphics acceleration and at the resolution the firmware picked."),
    RDNA3: ("Graphics: {name} ({family}) has no Apple driver. macOS installs and runs on the firmware framebuffer "
            "(basic display: desktop and apps work, no acceleration, firmware resolution). Acceleration is available "
            "only through the opt-in NullMoth test driver, which is experimental and unproven on this card."),
    RDNA4: ("Graphics: {name} ({family}) has no Apple driver. macOS installs and runs on the firmware framebuffer "
            "(basic display: desktop and apps work, no acceleration). The experimental community RDNA 4 drivers (" +
            ", ".join(RDNA4_COMMUNITY) + ") currently cover only the RX 9070 (Navi 48), not this card; full "
            "acceleration is not yet available for any RDNA 4 GPU."),
    APU_VEGA: ("Graphics: {name} ({family}) AMD integrated graphics has no Apple driver. macOS installs on the "
               "firmware framebuffer (basic display). The community NootedRed kext supports this iGPU, but its licence "
               "stops 1401 from bundling it; install NootedRed yourself for acceleration."),
    APU_RDNA: ("Graphics: {name} ({family}) AMD integrated graphics has no Apple driver and no proven community driver "
               "(NootedRed does not reliably accelerate RDNA iGPUs). macOS installs on the firmware framebuffer "
               "(basic display: desktop and apps work, no acceleration). Use a discrete supported GPU for acceleration."),
    UNKNOWN: ("Graphics: {name} ({family}) is an AMD card not yet in 1401's family table. macOS installs on the "
              "firmware framebuffer (basic display). Please report this device ID so it can be classified."),
}


def note(name, gpu):
    """The build notice for one AMD GPU named `name`, or None if it is not AMD."""
    c = classify(gpu)
    if c is None:
        return None
    family, path = c
    return _NOTE[path].format(name=name, family=family)


def notes(report, skip_ids=()):
    """Every AMD GPU's build notice, in scan order. Non-AMD GPUs are skipped, and so is any GPU whose device ID is in
    skip_ids (upper-case "VENDOR-DEVICE") - used for cards another pass describes in full, e.g. the Navi 48 cards the
    RDNA 4 display-driver pass covers, so they are not announced twice."""
    skip = {s.upper() for s in skip_ids}
    out = []
    for name, gpu in (report.get("GPU") or {}).items():
        if not isinstance(gpu, dict):
            continue
        if (gpu.get("Device ID") or "").upper() in skip:
            continue
        n = note(name, gpu)
        if n:
            out.append(n)
    return out
