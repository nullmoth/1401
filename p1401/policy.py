"""Policy pass. Runs after the engine writes config.plist and only touches what these rules cover.

Every rule is here because the engine's output disagrees with a source we can point to. Every change is recorded
as (rule, before, after, why) so the summary screen and bug reports can show it.

SIP stays on unless something the user picked needs it lowered, and then only as far as that needs. The engine
writes csr-active-config 0x00000A03 (unsigned kexts, unrestricted FS, unapproved kexts, and unauthenticated root)
on every macOS 11+ build (upstream config_prodigy.csr_active_config) whether anything needs it or not.
Dortania's baseline is 0x00000000.
"""
import json
import os
import plistlib
import re

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


# AMD chipsets whose firmware needs SetupVirtualMap (pre-Zen 2 boards; Dortania AMD Zen/Bulldozer configs).
# AMD platforms whose MMIO layout needs DevirtualiseMmio (Dortania: TRx40); everything else boots with it off.
AMD_DEVMMIO_ON = {"TRX40", "TRX50"}
AMD_SVM_ON = {"AM1", "A68H", "A75", "A78", "A85X", "A88X", "A320", "B350", "X370", "X399"}


# Zen 4 / Zen 5 by the scan's codename, or by the model number when the codename is missing. Desktop: 7x00, 8x00F/G,
# 9x00 (with X, X3D or F); laptops: the third digit of a 7000/8000 model is the Zen generation (7840HS = Zen 4,
# 7735HS = Zen 3+), and every "Ryzen AI" part is Zen 5.
ZEN45_CODENAMES = ("raphael", "phoenix", "hawk point", "dragon range", "granite ridge", "strix", "krackan", "fire range")
_ZEN45_NAME = re.compile(r"Ryzen AI\b|Ryzen [3579] (?:[79]\d\d0(?:X3D|X|F)?|8\d00[FG])\b|Ryzen [3579] [78]\d[45]\d(?:HX3D|HX|HS|H|U)\b", re.I)


def is_zen4_or_later(cpu):
    code = str(cpu.get("Codename") or "").lower()
    if any(c in code for c in ZEN45_CODENAMES):
        return True
    return bool(_ZEN45_NAME.search(str(cpu.get("Processor Name") or "")))


def _known_machines():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "known_machines.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh).get("machines", [])
    except (OSError, ValueError):
        return []  # a missing or broken table never stops a build; it only means no machine-specific settings


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
                   if not nullmoth.gpu_disabled(n, g, result.disabled_devices))
    intel_igpu = any(g.get("Manufacturer") == "Intel" and g.get("Device Type") == "Integrated GPU" for n, g in gpus.items()
                     if not nullmoth.gpu_disabled(n, g, result.disabled_devices))

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

    # 2d. Logs onto the stick: when macOS hangs or panics before it reaches a desktop, the only record is the screen.
    # OpenCore writes its log as a file on the partition it started from (Target bit 0x40, with 0x01 = logging on),
    # AppleDebug adds Apple's boot.efi log to it, and ApplePanic saves a macOS kernel panic there as panic-*.txt. The
    # Windows app finds those files on the stick and sends them, so a PC that never reaches macOS still reports why.
    dbg = cfg.setdefault("Misc", {}).setdefault("Debug", {})
    want = int(dbg.get("Target", 0) or 0) | 0x41
    if int(dbg.get("Target", 0) or 0) != want or dbg.get("AppleDebug") is not True or dbg.get("ApplePanic") is not True:
        before = f"Target {dbg.get('Target', 0)}, AppleDebug {dbg.get('AppleDebug')}, ApplePanic {dbg.get('ApplePanic')}"
        dbg["Target"] = want; dbg["AppleDebug"] = True; dbg["ApplePanic"] = True
        change("boot-logs-on-stick", before, f"Target {want}, AppleDebug, ApplePanic",
               "boot and panic logs are written to the stick, so a failed start can be reported from Windows")
    # 2d2. The installer on a 1401 stick is Apple's recovery image (com.apple.recovery.boot), which OpenCore lists as an
    # AUXILIARY entry: with HideAuxiliary on (552 of the configs users sent) the picker showed only Windows until Space
    # was pressed ("it didn't see macOS in OpenCore, only Windows", 10-09). Dortania: HideAuxiliary off for installers.
    boot = cfg.setdefault("Misc", {}).setdefault("Boot", {})
    if boot.get("HideAuxiliary") is not False:
        before = str(boot.get("HideAuxiliary"))
        boot["HideAuxiliary"] = False
        change("show-installer-entry", f"HideAuxiliary={before}", "HideAuxiliary=False",
               "the macOS installer on the stick is a recovery entry; it was hidden in the boot picker")
    # 2e. The Mac app proves which partition OpenCore started from by OpenCore's boot-path variable, which OpenCore
    # publishes only with Misc > Security > ExposeSensitiveData bit 0x1; the usual 6 leaves it out, and the Mac app then
    # stopped with one OpenCore partition in sight. Bit 0x1 exposes the booter path only - no serials.
    sec = cfg.setdefault("Misc", {}).setdefault("Security", {})
    esd = int(sec.get("ExposeSensitiveData", 6) or 0)
    if not esd & 0x1:
        sec["ExposeSensitiveData"] = esd | 0x1
        change("expose-boot-path", str(esd), str(esd | 0x1), "lets the Mac app confirm which partition OpenCore started from")

    # 10-07: the engine listed SSDT-Disable_Network_GPP7.aml twice in ACPI > Add (two network cards
    # behind the same bridge), and ocvalidate refuses a duplicated entry, so the whole build failed. OpenCore would load
    # the same table twice; the second copy does nothing. Keep the first of each Path (and each kext BundlePath).
    for section, key, label in (("ACPI", "Path", "ACPI > Add"), ("Kernel", "BundlePath", "Kernel > Add")):
        seen, kept, dups = set(), [], []
        for e in cfg.get(section, {}).get("Add", []):
            k = e.get(key) if isinstance(e, dict) else None
            if k and k in seen:
                dups.append(k)
                continue
            seen.add(k)
            kept.append(e)
        if dups:
            cfg[section]["Add"][:] = kept   # in place: `kexts` above is this same list
            change("dedupe-add", ", ".join(dups), "one entry each",
                   f"{label} listed the same file twice; OpenCore's validator refuses that")

    # 10-07 (stick logs + their configs): boot.efi stopped with
    # EB.MM.AKM Err(0xE) / STOP 0x16 ("Couldn't allocate runtime area") on Ryzen boards with SetupVirtualMap on. The engine
    # turns it off only for chipsets it can NAME (B450 X470 A520 B550 X570 TRX40), and Hardware Sniffer reads an AMD chipset
    # only from the board's product name - every AM4/AM5 FCH has the same PCI ID - so most boards report plain "AMD" and
    # AM5 (A620 B650 X670 X870) is not on the list at all. Dortania (AMD Zen config, Booter > Quirks): SetupVirtualMap off on
    # those boards. Keep it on only for the chipsets known to need it.
    cpu = (result.hardware or {}).get("CPU", {}) or {}
    chipset = ((result.hardware or {}).get("Motherboard", {}) or {}).get("Chipset", "")
    quirks = cfg.get("Booter", {}).get("Quirks", {})
    if cpu.get("Manufacturer") == "AMD" and chipset not in AMD_SVM_ON and quirks.get("SetupVirtualMap") is True:
        quirks["SetupVirtualMap"] = False
        change("amd-setupvirtualmap", "SetupVirtualMap=True", "SetupVirtualMap=False",
               f"Ryzen board (chipset reported as {chipset or 'unknown'}): boot.efi cannot allocate the kernel's memory with it on")
    # 10-07 (1401 1.0.14): a Ryzen board with SetupVirtualMap already off
    # still stopped at EB.MM.AKM / STOP 0x16 - with DevirtualiseMmio on (and a 2-entry MmioWhitelist). Every Ryzen stick
    # that passed boot.efi had it off. Dortania AMD Zen config: DevirtualiseMmio NO, YES only on
    # TRx40 (whose MMIO layout needs it).
    # Zen 4 and Zen 5 (Ryzen 7000/8000/9000, AM5 and their laptops) are the exception. Measured over every stick log
    # received through 2026-10-10: with DevirtualiseMmio off, family 19h models 60h-7Fh and family 1Ah stopped at
    # EB.MM.AKM in 60 boots and reached the kernel hand-off in 14; with it on, 6 stops (all one board) and 35 hand-offs.
    # AM4 and older Zen boot with it off (1 stop in more than 150 boots), so the rule above still holds for them. The
    # set that reached the desktop on an AM5 board is DevirtualiseMmio on with SetupVirtualMap off; the boot-log
    # ladder (bootfix.py) moves on from there if a board still stops.
    zen45 = cpu.get("Manufacturer") == "AMD" and is_zen4_or_later(cpu)
    if cpu.get("Manufacturer") == "AMD" and chipset not in AMD_DEVMMIO_ON and not zen45 and quirks.get("DevirtualiseMmio") is True:
        quirks["DevirtualiseMmio"] = False
        change("amd-devirtualisemmio", "DevirtualiseMmio=True", "DevirtualiseMmio=False",
               f"Ryzen board (chipset reported as {chipset or 'unknown'}): boot.efi cannot allocate the kernel's memory with it on")
    if zen45 and quirks.get("DevirtualiseMmio") is not True:
        quirks["DevirtualiseMmio"] = True
        if chipset not in AMD_SVM_ON:
            quirks["SetupVirtualMap"] = False
        change("amd-zen4-devirtualisemmio", "DevirtualiseMmio=False", "DevirtualiseMmio=True",
               f"{cpu.get('Processor Name') or 'Zen 4/5 Ryzen'}: boot.efi stops at EB.MM.AKM on these CPUs with it off")
    # Whitelist entries are inert whenever DevirtualiseMmio is off. This includes configurations whose quirk was
    # already off before the policy pass; ocvalidate rejects enabled entries in either case.
    if quirks.get("DevirtualiseMmio") is False:
        wl = [w for w in cfg.get("Booter", {}).get("MmioWhitelist", []) if isinstance(w, dict) and w.get("Enabled")]
        for w in wl:
            w["Enabled"] = False
        if wl:
            change("mmiowhitelist-without-quirk", f"{len(wl)} MmioWhitelist entr{'y' if len(wl) == 1 else 'ies'} enabled",
                   "disabled", "they only apply with DevirtualiseMmio on, and ocvalidate refuses them without it")

    # boot.efi stopped with STOP 0x16 (EB.MM.AKMr2: no room in low memory for the kernel) on 14 sticks, Intel and AMD,
    # although ProvideCustomSlide had picked a valid slide. OpenCore's AllowRelocationBlock loads the kernel through a
    # scratch block in the lower 4 GB and is used only when no slide fits (OpenCore Configuration, Booter > Quirks), so
    # machines that boot today never touch it. It needs ProvideCustomSlide and AvoidRuntimeDefrag on.
    if quirks.get("ProvideCustomSlide") is True and quirks.get("AvoidRuntimeDefrag") is True \
            and quirks.get("AllowRelocationBlock") is not True:
        quirks["AllowRelocationBlock"] = True
        change("relocation-block", "AllowRelocationBlock=False", "AllowRelocationBlock=True",
               "boot.efi stops (STOP 0x16) when low memory has no room for the kernel; the block is used only then")

    # 10-07: two fetched AMD kernel patches set Replace bits where ReplaceMask is 0, and ocvalidate refuses
    # that ("Replace requires ReplaceMask to be active for corresponding bits"). OpenCore writes (orig & ~mask) | (replace &
    # mask), so clearing those bits changes nothing it writes - it only makes the patch say what it does.
    fixed = []
    for i, pt in enumerate(cfg.get("Kernel", {}).get("Patch", [])):
        rep, msk = pt.get("Replace"), pt.get("ReplaceMask")
        if isinstance(rep, bytes) and isinstance(msk, bytes) and msk and len(rep) == len(msk):
            clean = bytes(r & m for r, m in zip(rep, msk))
            if clean != rep:
                pt["Replace"] = clean
                fixed.append(f"{i} ({pt.get('Comment') or pt.get('Identifier') or '?'})")
    if fixed:
        change("replace-under-mask", ", ".join(fixed), "Replace & ReplaceMask",
               "patch bits outside ReplaceMask are never written; ocvalidate refuses them")

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

    # 4b. Known machines (known_machines.json): a board + CPU whose own boots showed the settings it needs gets them on
    # every build, so its owner does not have to fail, send logs and rebuild again (Jake 10-09: keep each machine that
    # works and build it in). Checked before 5, so a newer failed boot's own log still wins.
    mb = ((result.hardware or {}).get("Motherboard") or {}).get("Name", "").lower()
    cpu_name = ((result.hardware or {}).get("CPU") or {}).get("Processor Name", "").lower()
    for known in _known_machines():
        if known["board"].lower() in mb and known["cpu"].lower() in cpu_name:
            q = cfg.setdefault("Booter", {}).setdefault("Quirks", {})
            for k, v in known.get("booter_quirks", {}).items():
                if q.get(k) != v:
                    change("known-machine", f"{k}={q.get(k)}", f"{k}={v}",
                           f"{known['board']} + {known['cpu']} ({known['status']}): {known['source']}")
                    q[k] = v
            break

    # 5. A failed boot's own log (the stick's opencore-*.txt), when the app passed one: see bootfix.py.
    if getattr(policy, "boot_logs", None) or getattr(policy, "stopped_at", ""):
        from . import bootfix  # noqa: PLC0415
        texts = bootfix.read_logs(policy.boot_logs)
        bootfix.apply(cfg, result, texts, change, getattr(policy, "stopped_at", ""))
        for note in bootfix.apply_after_handoff(cfg, texts, policy.stopped_at, change)["report"]:
            change("bootlog-note", "", note, "from the last failed start")

    tmp = config_path + ".tmp"
    with open(tmp, "wb") as fh:
        plistlib.dump(cfg, fh)
    import os  # noqa: PLC0415
    os.replace(tmp, config_path)
    return changes
