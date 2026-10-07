"""Policy pass. Runs after the engine writes config.plist and only touches what these rules cover.

Every rule is here because the engine's output disagrees with a source we can point to. Every change is recorded
as (rule, before, after, why) so the summary screen and bug reports can show it.

SIP stays on unless something the user picked needs it lowered, and then only as far as that needs. The engine
writes csr-active-config 0x00000A03 (unsigned kexts, unrestricted FS, unapproved kexts, and unauthenticated root)
on every macOS 11+ build (upstream config_prodigy.csr_active_config) whether anything needs it or not.
Dortania's baseline is 0x00000000.
"""
import plistlib

from . import nullmoth

BOOT = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
SIP_ON = bytes(4)
# Dortania Tahoe page (extras/tahoe.md): VoodooHDA lives in /Library/Extensions and needs csr-active-config 03000000.
SIP_VOODOOHDA = bytes.fromhex("03000000")
TAHOE = (25, 0, 0)

# Dortania Tahoe page: "WhateverGreen has AMD connector patching issues on macOS 26 ... your only option is to remove
# WhateverGreen.kext entirely. If you require agdpmod=pikera to boot, manually apply this patch" -> Pike R. Alpha's
# AppleGraphicsDevicePolicy patch, the same board-id -> board-ix rename WhateverGreen's pikera mode performs.
PIKERA_PATCH = {
    "Arch": "x86_64", "Base": "", "Comment": "1401 | Pike R. Alpha | AGDP board-id -> board-ix (agdpmod=pikera without WhateverGreen) | 26+",
    "Count": 0, "Enabled": True, "Find": b"board-id", "Identifier": "com.apple.driver.AppleGraphicsDevicePolicy",
    "Limit": 0, "Mask": b"", "MaxKernel": "", "MinKernel": "25.0.0", "Replace": b"board-ix", "ReplaceMask": b"", "Skip": 0,
}


WEG_ARGS = ("-radcodec", "agdpmod=", "-igfx", "igfx", "-wegnoegpu", "-wegnoigpu", "shikigva=", "unfairgva=", "-radvesa",
            "radpg=", "-raddvi", "-rad24", "-wegbeta", "-wegoff", "-cdfon", "-cdfoff", "applbkl=", "gfxrst=")


def _darwin(v):
    return tuple(int(x) for x in (v.split(".") + ["0", "0"])[:3])


def _args(nv):
    return (nv.get("boot-args") or "").split()


def apply(config_path, result, policy):
    """Mutates config.plist in place (atomic write). Returns the list of changes."""
    with open(config_path, "rb") as fh:
        cfg = plistlib.load(fh)
    changes = []
    nv = cfg["NVRAM"]["Add"].setdefault(BOOT, {})
    kexts = cfg["Kernel"]["Add"]
    enabled = {k["BundlePath"].split("/")[-1] for k in kexts if k.get("Enabled")}
    tahoe = _darwin(result.macos_version) >= TAHOE
    gpus = (result.hardware or {}).get("GPU", {})
    amd_dgpu = any(g.get("Manufacturer") == "AMD" and g.get("Device Type") != "Integrated GPU" for n, g in gpus.items()
                   if n not in result.disabled_devices)
    intel_igpu = any(g.get("Manufacturer") == "Intel" and g.get("Device Type") == "Integrated GPU" for n, g in gpus.items()
                     if n not in result.disabled_devices)

    def change(rule, before, after, why):
        changes.append({"rule": rule, "before": before, "after": after, "why": why})

    # 1. Tahoe + AMD dGPU: WhateverGreen out, pikera as a kernel patch.
    if tahoe and amd_dgpu and "WhateverGreen.kext" in enabled:
        if intel_igpu:
            change("tahoe-weg-amd", "WhateverGreen", "WhateverGreen (kept)",
                   "Tahoe + AMD dGPU can panic in WhateverGreen (Dortania), but the Intel iGPU needs it - flagged, not removed")
        else:
            for k in kexts:
                if k["BundlePath"] == "WhateverGreen.kext":
                    k["Enabled"] = False
            args = _args(nv)
            # WhateverGreen's boot args do nothing without it, so drop them too.
            dead = [x for x in args if x != "agdpmod=pikera" and x.startswith(WEG_ARGS)]
            if dead:
                nv["boot-args"] = " ".join(x for x in args if x not in dead)
                args = _args(nv)
                change("tahoe-weg-args", " ".join(dead), "", "WhateverGreen boot args are inert without WhateverGreen"
                       + (" - -radcodec was HW video decode on a spoofed AMD GPU; that is lost on Tahoe" if "-radcodec" in dead else ""))
            if "agdpmod=pikera" in args:
                args.remove("agdpmod=pikera")
                nv["boot-args"] = " ".join(args)
                cfg["Kernel"]["Patch"].append(dict(PIKERA_PATCH))
                change("tahoe-weg-amd", "WhateverGreen + agdpmod=pikera", "no WhateverGreen + AGDP kernel patch",
                       "Dortania Tahoe page: WhateverGreen AMD connector patching panics on 26; pikera moves to Kernel->Patch")
            else:
                change("tahoe-weg-amd", "WhateverGreen", "no WhateverGreen",
                       "Dortania Tahoe page: WhateverGreen AMD connector patching panics on 26")

    # 2. Tahoe + Intel Bluetooth: -ibtcompatbeta.
    if tahoe and "IntelBluetoothFirmware.kext" in enabled and "-ibtcompatbeta" not in _args(nv):
        nv["boot-args"] = " ".join(_args(nv) + ["-ibtcompatbeta"])
        change("tahoe-intel-bt", "", "-ibtcompatbeta", "Dortania Tahoe page: Intel Bluetooth on macOS 26 needs -ibtcompatbeta")

    # 2b. Arrow Lake (Core Ultra 200): match the config that installed and runs macOS 15 on a Core Ultra 5 225F
    # (its live OpenCore config, read off the machine ). It keeps the upstream Comet Lake CPUID spoof (without it the
    # kernel never starts: hang at EXITBS:START) and does NOT load CpuTopologyRebuild or pass ctrsmt; with them the
    # installer froze right after "PCI configuration end". npci, IOPCIFamily patches and ProvideCurrentCpuInfo were
    # never in it, so they are not added here either.
    cpu = (result.hardware or {}).get("CPU", {})
    if "Arrow Lake" in (cpu.get("Codename") or ""):
        for k in kexts:
            if k["BundlePath"].split("/")[-1] == "CpuTopologyRebuild.kext" and k.get("Enabled"):
                k["Enabled"] = False
                change("arrow-lake-ctr", "CpuTopologyRebuild", "off", "the proven Arrow Lake config does not load it")
        args = _args(nv)
        if any(a.startswith("ctrsmt") for a in args):
            nv["boot-args"] = " ".join(a for a in args if not a.startswith("ctrsmt"))
            change("arrow-lake-ctrsmt", "ctrsmt", "", "goes with CpuTopologyRebuild")

    # 2c. The stick listed boot-args in NVRAM->Delete, so booting it once replaced the boot flags of a machine that
    # already runs macOS (its -no_compat_check went with them and macOS refused to boot). Without Delete, OpenCore still
    # writes boot-args when none exist (a new machine), and never overwrites someone's existing ones.
    dl = cfg["NVRAM"].setdefault("Delete", {}).setdefault(BOOT, [])
    if "boot-args" in dl:
        dl.remove("boot-args")
        change("keep-boot-args", "Delete boot-args", "keep existing boot-args", "never overwrite an installed system's boot flags")

    # 3. NullMoth driver: a GeForce RTX the engine kept (nullmoth.mark) gets the tested boot-args + SIP.
    driver = nullmoth.apply(cfg, result, change)
    # , measured on an RTX 5060 with Resizable BAR on: with the full BAR the installer's screen froze right after
    # "PCI configuration end" (macOS re-places the large BAR and the firmware framebuffer goes with it); with
    # ResizeAppleGpuBars 0 (Dortania: firmware with Resizable BAR) it boots on. The Mac helper sets the 8 GB BAR back after install.
    if driver:
        cfg["Booter"]["Quirks"]["ResizeAppleGpuBars"] = 0
        cfg["UEFI"]["Quirks"]["ResizeGpuBars"] = -1
        change("nullmoth-installer-bar", "", "ResizeAppleGpuBars=0", "keeps the installer's screen alive on a Resizable BAR NVIDIA card")

    # 4. SIP: the least that the chosen features need (the driver's tested value wins when it applies).
    voodoo = tahoe and policy.tahoe_audio == "voodoohda" and any(
        d.prompt.startswith("Select audio kext") for d in result.decisions)
    if result.needs_oclp:
        want, why = nv.get("csr-active-config"), "OCLP root patches need SIP lowered (the user was told, and chose it)"
    elif voodoo:
        want, why = SIP_VOODOOHDA, "VoodooHDA on Tahoe loads from /Library/Extensions (Dortania: csr 03000000)"
    else:
        want, why = SIP_ON, "nothing this machine uses needs SIP lowered"
    if not driver and nv.get("csr-active-config") != want:
        change("sip-minimal", (nv.get("csr-active-config") or b"").hex(), want.hex(), why)
        nv["csr-active-config"] = want

    tmp = config_path + ".tmp"
    with open(tmp, "wb") as fh:
        plistlib.dump(cfg, fh)
    import os  # noqa: PLC0415
    os.replace(tmp, config_path)
    return changes
