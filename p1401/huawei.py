"""Huawei MateBook X Pro 2023 (MRGFG-XX) profile: what this exact machine's scan means.

The generic builder already picks the right pieces for this hardware; this module adds what is specific to the
machine and what is still unverified, without changing any generic rule:

  - Iris Xe 8086:A7A0 is in WhateverXe's table (Raptor Lake-P), and the EFI includes WhateverXe.kext.
  - AX211 (8086:51F1) uses itlwm, so Wi-Fi is joined with HeliPort after macOS starts, not by the installer.
  - GXTP786 is the I2C touchpad and GXTP738X is the I2C touchscreen: two different devices, never one map for both.
  - The TBU405Pro is an external USB NVMe enclosure; 1401 never treats a USB disk as the install target.

Nothing here claims a boot that was not observed. notes() returns lines for the build report; the matching
machine_recipes.json row carries the CPUID topology setting and its status.
"""
import os

BOARD_TOKENS = ("MRGFG-XX", "MateBook X Pro")
CPU_TOKENS = ("i7-1360P",)
GPU_DEVICE = "8086-A7A0"
WIFI_DEVICE = "8086-51F1"
TOUCHPAD_DEVICE = "GXTP786"
TOUCHSCREEN_DEVICE = "GXTP738X"
EXTERNAL_BRIDGE = "TBU405"


def matches(hardware):
    """True for this machine's scan: board and CPU both named, not just a similar CPU."""
    board = str(((hardware or {}).get("Motherboard") or {}).get("Name") or "").lower()
    cpu = str(((hardware or {}).get("CPU") or {}).get("Processor Name") or "").lower()
    return (any(t.lower() in board for t in BOARD_TOKENS)
            and any(t.lower() in cpu for t in CPU_TOKENS))


def _gpu(hardware):
    for props in ((hardware or {}).get("GPU") or {}).values():
        if isinstance(props, dict) and str(props.get("Device ID") or "").upper() == GPU_DEVICE:
            return props
    return None


def _input_device(hardware, device):
    for name, props in ((hardware or {}).get("Input") or {}).items():
        if isinstance(props, dict) and str(props.get("Device") or "").upper() == device:
            return name
    return None


def _external(hardware):
    for props in ((hardware or {}).get("Storage Drives") or {}).values():
        if (isinstance(props, dict) and str(props.get("Bus Type") or "").upper() == "USB"
                and EXTERNAL_BRIDGE in str(props.get("Model") or "").upper()):
            return props
    return None


def notes(hardware, kexts=(), net_status=None):
    """Build notices for this machine. Empty for any other scan."""
    if not matches(hardware):
        return []
    chosen = set(kexts or ())
    out = []
    gpu = _gpu(hardware)
    if gpu is not None:
        if "WhateverXe" in chosen:
            out.append("Huawei profile: the Iris Xe A7A0 (Raptor Lake-P) is in WhateverXe's device table and this EFI "
                       "includes WhateverXe.kext. macOS starts on the firmware framebuffer; the full graphics package "
                       "is the opt-in 1401 Mac-app step for macOS 15.8 or 26.7 and later.")
        else:
            out.append("Huawei profile: the Iris Xe A7A0 is present but WhateverXe.kext was not selected; expect the "
                       "firmware framebuffer only.")
    net = (hardware or {}).get("Network") or {}
    if any(isinstance(v, dict) and str(v.get("Device ID") or "").upper() == WIFI_DEVICE for v in net.values()):
        if net_status is not None and net_status.get("offline_recommended"):
            out.append("Huawei profile: the AX211 (8086:51F1) uses itlwm, which joins Wi-Fi through HeliPort after "
                       "macOS starts and is not available in the installer. The build has already said the installer "
                       "needs Ethernet or a full offline installer; both are true for this machine.")
        else:
            out.append("Huawei profile: the AX211 (8086:51F1) uses itlwm; join Wi-Fi with HeliPort after macOS starts, "
                       "not from the menu bar.")
    pad = _input_device(hardware, TOUCHPAD_DEVICE)
    screen = _input_device(hardware, TOUCHSCREEN_DEVICE)
    if pad:
        out.append(f"Huawei profile: {pad} (GXTP786) is the I2C touchpad. VoodooI2C/VoodooI2CHID and "
                   f"VoodooPS2Controller are included for it, with -vi2c-force-polling. It is the touchpad, not the "
                   f"touchscreen.")
    if screen:
        out.append(f"Huawei profile: {screen} (GXTP738X) is the I2C touchscreen, not the touchpad. macOS has no "
                   f"touchscreen driver, so 1401 does not count it as the trackpad and does not promise it works.")
    external = _external(hardware)
    if external is not None:
        size = int(external.get("Size") or 0)
        out.append(f"Huawei profile: {external.get('Model')} ({size / (1 << 30):.1f} GiB, USB) is an external USB NVMe "
                   f"enclosure, not the internal install target. 1401 never treats a USB disk as the target: erase it "
                   f"as APFS in Disk Utility and boot through the stick's OpenCore. UASP, sleep/wake and booting from "
                   f"this bridge are unverified on this machine.")
    return out
