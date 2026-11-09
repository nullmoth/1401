"""Intel Xe GPU classification: turns a scanned Intel GPU's PCI device ID into the macOS path it gets, for the build notice.

macOS's own Intel graphics drivers stop at Ice Lake (Gen 11). Every Intel GPU from Tiger Lake on (Xe, Gen 12 and later,
integrated or discrete Arc) has no Apple driver, so the PC installs on the firmware framebuffer: the desktop and apps
work, with no acceleration. Two groups follow from that:

- WHATEVERXE: the Tiger Lake, Alder Lake and Raptor Lake IDs that b00t0x's WhateverXe (BSD-3) selects a backend for.
  After macOS is installed, the 1401 Mac app offers WhateverXe as an opt-in test (setup --xe). The list is the one the
  Mac app and its setup script already check (mac/Sources/main.swift App.xeIds, mac/Resources/nullmoth-setup.sh);
  tests/test_intel_gpu.py fails if the three ever differ.
- NO_DRIVER: other Xe-generation IDs (Rocket Lake, the rest of Tiger Lake and Alder Lake-P, Meteor Lake, Arrow Lake,
  Lunar Lake, Panther Lake, and discrete Arc / Battlemage / DG1). No driver exists for them yet; basic display only.

Every ID not listed here (Gen 9 to Gen 11, Atom-class and anything unknown) returns None and the build says nothing new
about it, so the notice for a GPU macOS or WhateverGreen already drives cannot change.

Device IDs are from the Linux i915/xe pci id tables (include/drm/intel/pciids.h). This module only classifies and
explains; it changes no config, adds no kext and sets no boot argument.
"""

WHATEVERXE = "whateverxe"   # no Apple driver; basic display at install, opt-in WhateverXe from the Mac app afterwards
NO_DRIVER = "none"          # no Apple driver and no driver 1401 can offer yet; basic display

INTEL_VENDOR = "8086"

# The IDs WhateverXe 0.8.0 selects a backend for (its docs/device-selection.md). Same order as App.xeIds.
WHATEVERXE_IDS = (
    "9A40", "9A49", "9A59", "9A60", "9A68", "9A70", "9A78", "9AC0", "9AC9", "9AD9", "9AF8", "46D0", "46D1", "46D2",
    "46D3", "46D4", "4626", "4628", "462A", "46A0", "46A1", "46A2", "46A3", "46A6", "46A8", "46AA", "46B0", "46B1",
    "46B2", "46B3", "46C0", "46C1", "46C2", "46C3", "A720", "A7A0", "A7A8", "A7AA", "A7AB", "A721", "A7A1", "A7A9",
    "A7AC", "A7AD", "4680", "4682", "4688", "468A", "468B", "4690", "4692", "4693", "A780", "A781", "A782", "A783",
    "A788", "A789", "A78A", "A78B",
)

# Family label per ID group. A WhateverXe ID takes its family from here too; its path comes from WHATEVERXE_IDS.
_FAMILIES = (
    ("Tiger Lake (Xe-LP)", ("9A40", "9A49", "9A59", "9A60", "9A68", "9A70", "9A78", "9AC0", "9AC9", "9AD9", "9AF8")),
    ("Rocket Lake (Xe-LP)", ("4C80", "4C8A", "4C8B", "4C8C", "4C90", "4C9A")),
    ("Alder Lake-S (Xe-LP)", ("4680", "4682", "4688", "468A", "468B", "4690", "4692", "4693")),
    ("Alder Lake-P (Xe-LP)", ("46A0", "46A1", "46A2", "46A3", "46A6", "46A8", "46AA", "462A", "4626", "4628",
                              "46B0", "46B1", "46B2", "46B3", "46C0", "46C1", "46C2", "46C3")),
    ("Alder Lake-N (Xe-LP)", ("46D0", "46D1", "46D2", "46D3", "46D4")),
    ("Raptor Lake-S (Xe-LP)", ("A780", "A781", "A782", "A783", "A788", "A789", "A78A", "A78B")),
    ("Raptor Lake-P (Xe-LP)", ("A720", "A721", "A7A0", "A7A1", "A7A8", "A7A9", "A7AA", "A7AB", "A7AC", "A7AD")),
    ("Meteor Lake / Arrow Lake (Xe-LPG)", ("7D40", "7D41", "7D45", "7D51", "7D55", "7D60", "7D67", "7DD1", "7DD5")),
    ("Lunar Lake (Xe2)", ("6420", "64A0", "64B0")),
    ("Panther Lake (Xe3)", ("B080", "B081", "B082", "B083", "B08F", "B090", "B0A0", "B0B0")),
    ("Iris Xe discrete (DG1)", ("4905", "4906", "4907", "4908", "4909")),
    ("Arc A-series (Alchemist)", ("5690", "5691", "5692", "5693", "5694", "5695", "5696", "5697", "5698",
                                  "56A0", "56A1", "56A2", "56A3", "56A4", "56A5", "56A6",
                                  "56B0", "56B1", "56B2", "56B3", "56BA", "56BB", "56BC", "56BD", "56C0", "56C1")),
    ("Arc B-series (Battlemage)", ("E202", "E20B", "E20C", "E20D", "E210", "E211", "E212", "E215", "E216")),
)
_FAMILY = {did: label for label, ids in _FAMILIES for did in ids}


def device_id(gpu):
    """The 4-hex-digit Intel device ID (upper case), or None if this GPU is not an Intel (vendor 8086) device."""
    did = (gpu.get("Device ID") or "").upper()
    if not did.startswith(INTEL_VENDOR + "-"):
        return None
    dev = did.split("-", 1)[1]
    return dev if len(dev) == 4 else None


def classify(gpu):
    """(family_label, path) for an Intel Xe-generation GPU, or None for any other GPU (non-Intel, or an Intel GPU
    macOS or WhateverGreen already covers, or one no table here names)."""
    dev = device_id(gpu)
    if dev is None or dev not in _FAMILY:
        return None
    return _FAMILY[dev], (WHATEVERXE if dev in WHATEVERXE_IDS else NO_DRIVER)


# Each starts with "Graphics:" so the Windows app's support-notice filter shows it before the build
# (MainForm.IsSupportNotice). {name} is the scan's name for the GPU, {family} the label from classify().
_BASIC = ("macOS installs and runs on the screen the firmware sets up (basic display: the desktop and apps work, no "
          "graphics acceleration, the resolution the firmware picked)")
_NOTE = {
    WHATEVERXE: ("Graphics: {name} ({family}) has no Apple driver. " + _BASIC + ". After macOS is installed, the 1401 "
                 "Mac app offers Intel Xe graphics through b00t0x's WhateverXe as an opt-in test, for macOS 15.8 or "
                 "26.7 and later. It is off unless you turn it on."),
    NO_DRIVER: ("Graphics: {name} ({family}) has no Apple driver, and no driver 1401 can offer for it yet. " + _BASIC
                + "."),
}
_WITH_NVIDIA = (" WhateverXe has not been tested together with the NullMoth NVIDIA driver on the same machine.")


def note(name, gpu, nvidia=False):
    """The build notice for one Intel Xe GPU named `name`, or None. nvidia=True when the build also selected an NVIDIA
    card for the NullMoth driver: the WhateverXe notice then says that pairing is untested."""
    c = classify(gpu)
    if c is None:
        return None
    family, path = c
    text = _NOTE[path].format(name=name, family=family)
    return text + _WITH_NVIDIA if (nvidia and path == WHATEVERXE) else text


def notes(report, nvidia=False):
    """Every Intel Xe GPU's build notice, in scan order."""
    out = []
    for name, gpu in (report.get("GPU") or {}).items():
        if isinstance(gpu, dict):
            n = note(name, gpu, nvidia)
            if n:
                out.append(n)
    return out
