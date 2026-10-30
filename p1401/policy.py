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


# Hybrid-core Intel: Core Ultra (Meteor, Arrow, Lunar Lake) and 12th/13th/14th-generation Core (Alder, Raptor Lake).
# They carry a mix of performance and efficiency cores and stop at the kernel hand-off (EXITBS:START) with a type-14
# page fault far more often than earlier Intel; the levers below are keyed on this class.
_INTEL_HYBRID_CODENAMES = ("meteor lake", "arrow lake", "lunar lake", "alder lake", "raptor lake")
_INTEL_HYBRID_NAME = re.compile(r"Core\(TM\) Ultra|1[234]th Gen.*Core\(TM\)", re.I)


def is_intel_hybrid(cpu):
    if (cpu or {}).get("Manufacturer") != "Intel":
        return False
    code = str((cpu or {}).get("Codename") or "").lower()
    if any(c in code for c in _INTEL_HYBRID_CODENAMES):
        return True
    return bool(_INTEL_HYBRID_NAME.search(str((cpu or {}).get("Processor Name") or "")))


def _known_machines():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "known_machines.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh).get("machines", [])
    except (OSError, ValueError):
        return []  # a missing or broken table never stops a build; it only means no machine-specific settings


# Kexts under the ChefKiss licence (GitHub reports a custom licence for all four, 10-11). Never shipped by 1401: rule 0.
EXCLUDED_KEXTS = ("NootedRed.kext", "NootRX.kext", "SMCRadeonSensors.kext", "ForgedInvariant.kext")

# Emulated NVRAM is set up exactly as OpenCore's Configuration doc (section 11.11, "Managing macOS updates when using
# emulated NVRAM") requires. The three GUIDs are OpenCore's own permissive LegacySchema: with <string>*</string> every
# variable macOS saves - including the fmm-mobileme tokens iMessage/Apple ID need - is captured to nvram.plist.
EMULATED_NVRAM_DRIVER = "OpenVariableRuntimeDxe.efi"
EMULATED_NVRAM_SCHEMA = ("36C28AB5-6566-4C50-9EBD-CBB920F83843", "7C436110-AB2A-4BBB-A880-FE41995C9F82",
                         "8BE4DF61-93CA-11D2-AA0D-00E098032B8C")


def _enable_emulated_nvram(cfg, config_path, change):
    """OpenCore emulated NVRAM on an AMD guard board, opt-in only. Returns (True, None) once it is fully in place, or
    (False, reason) when it is not - OpenVariableRuntimeDxe.efi ships only inside the verified OpenCore release, so a
    release without it (or a release that cannot be verified) keeps the firmware-write guard instead. Three pieces,
    all from the SAME sha256-checked zip the engine already downloaded (validate.release_archive):
      - OpenVariableRuntimeDxe.efi with LoadEarly=true, ordered immediately before OpenRuntime.efi (also LoadEarly=true);
        this is the order the doc requires for RequestBootVarRouting, and validate.release_components then re-checks the
        driver's bytes against the release like every other boot file.
      - LegacySchema populated with the three permissive GUIDs so the LogoutHook saves every variable macOS writes.
      - the LogoutHook staged on the ESP at EFI/NullMoth/LogoutHook for the Mac app to install (it saves NVRAM to
        nvram.plist at shutdown; without it the emulated store is never written back).
    ExposeSensitiveData bit 0x1 (set earlier in this pass) makes the boot-path variable the LogoutHook reads available.
    Any failure returns a reason and changes nothing a half-built driver could make OpenCore load; the caller keeps the
    guard. The caller turns DisableVariableWrite OFF only on success, because it would otherwise block the same macOS
    writes before they reached the emulated store."""
    import io  # noqa: PLC0415
    import zipfile  # noqa: PLC0415
    from . import validate  # noqa: PLC0415
    drivers = cfg.setdefault("UEFI", {}).setdefault("Drivers", [])
    ort_i = next((i for i, d in enumerate(drivers)
                  if isinstance(d, dict) and d.get("Path") == "OpenRuntime.efi"), None)
    if ort_i is None:
        return False, "OpenRuntime.efi is not in the driver list"
    try:
        data = validate.release_archive()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = set(z.namelist())
            member = "X64/EFI/OC/Drivers/" + EMULATED_NVRAM_DRIVER
            if member not in names:
                return False, f"{EMULATED_NVRAM_DRIVER} is not in this OpenCore release"
            drv_bytes = z.read(member)
            hook = {os.path.basename(n): z.read(n) for n in names
                    if n.startswith("Utilities/LogoutHook/") and not n.endswith("/")}
    except Exception as e:  # noqa: BLE001 - an opt-in enhancement must never stop a build; fall back to the guard
        return False, f"the verified OpenCore release could not be read ({type(e).__name__}: {e})"
    if "Launchd.command" not in hook or "nvramdump" not in hook:
        return False, "the OpenCore release has no Utilities/LogoutHook to save NVRAM with"

    oc_dir = os.path.dirname(config_path)          # .../EFI/OC
    efi_dir = os.path.dirname(oc_dir)              # .../EFI

    def _atomic_write(path, blob, mode=None):
        tmp = path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(blob)
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)

    # 1. the driver file beside OpenRuntime.efi
    ddir = os.path.join(oc_dir, "Drivers")
    os.makedirs(ddir, exist_ok=True)
    _atomic_write(os.path.join(ddir, EMULATED_NVRAM_DRIVER), drv_bytes)

    # 2. the driver entry (LoadEarly, immediately before OpenRuntime.efi, which also becomes LoadEarly). Mirror
    #    OpenRuntime's own key shape so ocvalidate reads a known entry, whatever keys this OpenCore version carries.
    if not any(isinstance(d, dict) and d.get("Path") == EMULATED_NVRAM_DRIVER for d in drivers):
        entry = dict(drivers[ort_i])
        entry["Path"] = EMULATED_NVRAM_DRIVER
        entry["Comment"] = "1401 | emulated NVRAM (persistent NVRAM on AMD guard boards)"
        entry["Enabled"] = True
        entry["LoadEarly"] = True
        entry["Arguments"] = ""
        drivers.insert(ort_i, entry)
        ort_i += 1
        change("amd-emulated-nvram-driver", "", f"{EMULATED_NVRAM_DRIVER} (LoadEarly, before OpenRuntime.efi)",
               "OpenCore emulated NVRAM gives these boards a writable NVRAM store without touching the fragile firmware flash")
    if drivers[ort_i].get("LoadEarly") is not True:
        drivers[ort_i]["LoadEarly"] = True
        change("amd-emulated-openruntime-early", "OpenRuntime.efi LoadEarly=False", "OpenRuntime.efi LoadEarly=True",
               "emulated NVRAM needs OpenRuntime loaded early, after OpenVariableRuntimeDxe (OpenCore Configuration 11.11)")

    # 3. LegacySchema: the three permissive GUIDs
    schema = cfg.setdefault("NVRAM", {}).setdefault("LegacySchema", {})
    before = {g: schema.get(g) for g in EMULATED_NVRAM_SCHEMA}
    if any(schema.get(g) != ["*"] for g in EMULATED_NVRAM_SCHEMA):
        for g in EMULATED_NVRAM_SCHEMA:
            schema[g] = ["*"]
        change("amd-emulated-legacyschema", str(before), "three GUIDs -> *",
               "lets the LogoutHook save every NVRAM variable macOS writes (incl. the iMessage/Apple ID tokens) to nvram.plist")

    # 4. the LogoutHook staged on the ESP for the Mac app to install
    hook_dir = os.path.join(efi_dir, "NullMoth", "LogoutHook")
    os.makedirs(hook_dir, exist_ok=True)
    for name, blob in hook.items():
        _atomic_write(os.path.join(hook_dir, name), blob, 0o755 if name in ("Launchd.command", "nvramdump") else None)
    change("amd-emulated-logouthook", "", "EFI/NullMoth/LogoutHook staged",
           "the Mac app installs this OpenCore LaunchDaemon, which saves NVRAM to nvram.plist at shutdown")
    return True, None


def apply(config_path, result, policy):
    """Mutates config.plist in place (atomic write). Returns the list of changes."""
    with open(config_path, "rb") as fh:
        cfg = plistlib.load(fh)
    changes = []
    nv = cfg["NVRAM"]["Add"].setdefault(BOOT, {})
    # 0. The upstream builder picks NootedRed (AMD APU graphics), NootRX (Navi 22), SMCRadeonSensors and ForgedInvariant
    # for some machines. Their licence
    # restricts the use and distribution of derivative packages, so 1401 never ships them: the entries and the files go, and
    # those GPUs run on the firmware framebuffer (basic display) until NullMoth's own driver covers them.
    gone = [k["BundlePath"] for k in cfg["Kernel"]["Add"] if k.get("BundlePath", "").split("/")[0] in EXCLUDED_KEXTS]
    if gone:
        cfg["Kernel"]["Add"] = [k for k in cfg["Kernel"]["Add"] if k.get("BundlePath", "").split("/")[0] not in EXCLUDED_KEXTS]
        import shutil  # noqa: PLC0415
        for name in EXCLUDED_KEXTS:
            shutil.rmtree(os.path.join(os.path.dirname(config_path), "Kexts", name), ignore_errors=True)
        change_early = {"rule": "excluded-kexts", "before": ", ".join(sorted(set(gone))), "after": "",
                        "why": "licence restrictions prevent inclusion; this GPU gets basic display until NullMoth's own driver covers it"}
        changes.append(change_early)
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

    # 2a. Tahoe refuses to boot, and refuses to finish an update from Sequoia, on a Mac model Apple did not ship it for:
    # the installer and the upgrade both end at the prohibited sign. macOS 26 added a secure-boot model-version check;
    # RestrictEvents answers it with revpatch=sbvmm (the same bypass OCLP applies on unsupported Macs). RestrictEvents is
    # already in a 26 build (it follows the SMBIOS the engine picks), so this only sets the boot argument that turns it on.
    if tahoe and "RestrictEvents.kext" in enabled:
        args = _args(nv)
        rev = next((a for a in args if a.startswith("revpatch=")), None)
        vals = [v for v in (rev.split("=", 1)[1].split(",") if rev else []) if v]
        if "sbvmm" not in vals:
            vals.append("sbvmm")
            nv["boot-args"] = " ".join([a for a in args if not a.startswith("revpatch=")] + ["revpatch=" + ",".join(vals)]).strip()
            change("tahoe-sbvmm", rev or "", "revpatch=" + ",".join(vals),
                   "Tahoe's secure-boot model-version check stops an unsupported Mac model at boot and during an update")

    # 2b. Arrow Lake (Core Ultra 200): match the config that installed and runs macOS 15 on a Core Ultra 5 225F
    # (its live OpenCore config, read off the machine ). It keeps the upstream Comet Lake CPUID spoof (without it the
    # kernel never starts: hang at EXITBS:START) and does NOT load CpuTopologyRebuild or pass ctrsmt; with them the
    # installer froze right after "PCI configuration end". npci, IOPCIFamily patches and ProvideCurrentCpuInfo were
    # never in it, so they are not added here either.
    cpu = (result.hardware or {}).get("CPU", {})
    platform = ((result.hardware or {}).get("Motherboard") or {}).get("Platform", "")
    is_laptop = platform == "Laptop"
    # The desktop Arrow Lake config that installed and runs macOS 15 does not load CpuTopologyRebuild. Laptops are the
    # exception: their firmware usually hides the Hyper-Threading and E-core switches, so CpuTopologyRebuild is the only
    # way to re-map the cores for the kernel, and it stays on there.
    if "Arrow Lake" in (cpu.get("Codename") or "") and not is_laptop:
        for k in kexts:
            if k["BundlePath"].split("/")[-1] == "CpuTopologyRebuild.kext" and k.get("Enabled"):
                k["Enabled"] = False
                change("arrow-lake-ctr", "CpuTopologyRebuild", "off", "the desktop Arrow Lake config that boots does not load it")
        args = _args(nv)
        if any(a.startswith("ctrsmt") for a in args):
            nv["boot-args"] = " ".join(a for a in args if not a.startswith("ctrsmt"))
            change("arrow-lake-ctrsmt", "ctrsmt", "", "goes with CpuTopologyRebuild")

    # 2b'. Intel Core Ultra (Meteor, Arrow, Lunar Lake): the kernel hangs at EXITBS:START with VT-d's DMAR table present,
    # DisableIoMapper on or not (every Core Ultra stick config uploaded had it on; 1401 #10/#11 and chat, 245KF-290HX).
    # Every Core Ultra machine that reached the desktop had VT-d off: three users by turning it off in the BIOS (one
    # found it only on the overclocking page), and the 225F test machine, whose firmware gives macOS no DMAR. Dropping
    # DMAR in OpenCore is the same for macOS and works where the BIOS hides the switch. Linux and Windows keep it.
    name = str(cpu.get("Processor Name") or "")
    if cpu.get("Manufacturer") == "Intel" and ("Core(TM) Ultra" in name or any(c in (cpu.get("Codename") or "") for c in ("Meteor Lake", "Arrow Lake", "Lunar Lake"))):
        dele = cfg.setdefault("ACPI", {}).setdefault("Delete", [])
        if not any(isinstance(d, dict) and d.get("TableSignature") == b"DMAR" and d.get("Enabled") for d in dele):
            dele.append({"All": True, "Comment": "Drop VT-d DMAR (Core Ultra hangs at the kernel hand-off with it)", "Enabled": True,
                         "OemTableId": bytes(8), "TableLength": 0, "TableSignature": b"DMAR"})
            change("core-ultra-drop-dmar", "DMAR present", "ACPI > Delete DMAR",
                   "Core Ultra PCs hang at EXITBS:START with VT-d's table; every one that booted had VT-d off")
        kq = cfg.setdefault("Kernel", {}).setdefault("Quirks", {})
        if kq.get("DisableIoMapper") is not True:
            kq["DisableIoMapper"] = True
            change("core-ultra-iomapper", "DisableIoMapper=False", "True", "VT-d stays out of macOS on Core Ultra")

    # 2b''. Hybrid-core Intel (Core Ultra and 12th/13th/14th-gen Core): the kernel hand-off faults (EXITBS:START,
    # type 14) before macOS starts. On stuck machines, limiting the kernel to one CPU reached the installer's APFS
    # volume, and so did turning DevirtualiseMmio off - boot.efi faults on the firmware's devirtualised MMIO. The
    # Intel baseline keeps DevirtualiseMmio off, so turn it off when the engine left it on.
    # 10-25: laptops only. Over 448 hybrid-Intel machines in the stick uploads, the ones that got macOS onto their disk
    # had DevirtualiseMmio on as often or more often than off in every slice (desktops 16% on / 13% off, Arrow Lake
    # desktops 2 of 20 on / 0 of 11 off), and the Core Ultra 5 225F desktop that runs macOS 26 boots with it on. The
    # laptops are the case for off: 1401 #6 (13650HX) took a type-14 fault at CR2 0xFF00004C with it on, and six of seven
    # public laptop EFIs that run macOS on these CPUs have it off. Arrow Lake desktops get the 225F's setting.
    if is_intel_hybrid(cpu):
        bq = cfg.setdefault("Booter", {}).setdefault("Quirks", {})
        if is_laptop and bq.get("DevirtualiseMmio") is True:
            bq["DevirtualiseMmio"] = False
            change("hybrid-intel-devmmio", "DevirtualiseMmio=True", "DevirtualiseMmio=False",
                   "hybrid-core Intel laptops fault in boot.efi (EXITBS:START, type 14) with firmware MMIO devirtualised")
        elif not is_laptop and "Arrow Lake" in (cpu.get("Codename") or "") and bq.get("DevirtualiseMmio") is not True:
            bq["DevirtualiseMmio"] = True
            change("arrow-lake-desktop-devmmio", f"DevirtualiseMmio={bq.get('DevirtualiseMmio')}", "DevirtualiseMmio=True",
                   "the Arrow Lake desktop that runs macOS boots with it on, and Arrow Lake desktops did better with it on")
        # CpuTopologyRebuild re-maps the performance and efficiency cores so the kernel accepts the topology; it is the
        # software stand-in for the BIOS "disable Hyper-Threading / E-cores" that many laptops hide. The kext does not
        # always clear the stop on its own, so name the BIOS switch too when it is available.
        ctr_on = any(k["BundlePath"].split("/")[-1] == "CpuTopologyRebuild.kext" and k.get("Enabled") for k in kexts)
        note = ("If this PC stops at EXITBS:START before macOS starts, turn off Hyper-Threading (or the E-cores) in the "
                "BIOS. " + ("This build re-maps the cores in software (CpuTopologyRebuild) for firmware that hides the "
                            "switch, but the BIOS setting is the surest fix when it is there."
                            if ctr_on else
                            "This build does not re-map the cores, so the BIOS setting is required."))
        change("hybrid-intel-bios", "", note, "hybrid-core Intel stops at the kernel hand-off (EXITBS:START)")

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
    # 2d3. The same entries have to be reachable later, when the driver adds "Remove NVIDIA driver" as an OpenCore tool:
    # the picker must appear on its own (ShowPicker), and it has to be a picker that lists tools. Apple's own picker
    # (PickerMode Apple) shows only bootable OSes, so a user whose desktop the driver broke could not find the Remove
    # entry even after pressing Space ("remove nvidia driver doesnt exist even when i press space"). Builtin and
    # External (OpenCanopy) both list tools; only Apple is moved off, to the always-present Builtin text picker.
    if boot.get("ShowPicker") is not True:
        before = str(boot.get("ShowPicker"))
        boot["ShowPicker"] = True
        change("show-picker", f"ShowPicker={before}", "ShowPicker=True",
               "the boot picker has to appear so the macOS installer and the driver's Remove entry can be chosen")
    if boot.get("PickerMode") == "Apple":
        boot["PickerMode"] = "Builtin"
        change("picker-lists-tools", "PickerMode=Apple", "PickerMode=Builtin",
               "Apple's boot picker never lists OpenCore tools, so the driver's Remove entry could not appear in it")
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

    # Two kexts that do the same job, both enabled. Field panics "[kalloc.type.var*.16]: element modified after free"
    # (21 reports, some before any NullMoth kext loads) had one of these pairs in all 11 configs that came with them,
    # and none of the 49 other panics did: USBInjectAll beside USBToolBox (two USB port maps), IntelMausi beside
    # IntelSnowMausi (two drivers for the same Ethernet controller). USBToolBox is the map the builder makes, and
    # IntelMausi is the current driver, so the other one of each pair goes off.
    # (literal rule names in change(): tests/test_efi_rules.py reads them with a parser)
    def drop_second(keep, drop):
        on = {k["BundlePath"].split("/")[-1] for k in kexts if isinstance(k, dict) and k.get("Enabled")}
        if keep not in on or drop not in on:
            return False
        for k in kexts:
            if isinstance(k, dict) and k.get("BundlePath", "").split("/")[-1] == drop:
                k["Enabled"] = False
        return True
    why = "two kexts doing the same job; configs with both crashed with 'element modified after free'"
    if drop_second("USBToolBox.kext", "USBInjectAll.kext"):
        change("kext-conflict-usb", "USBToolBox.kext and USBInjectAll.kext both enabled", "USBInjectAll.kext off", why)
    if drop_second("IntelMausi.kext", "IntelSnowMausi.kext"):
        change("kext-conflict-mausi", "IntelMausi.kext and IntelSnowMausi.kext both enabled", "IntelSnowMausi.kext off", why)

    # 10-07 (stick logs + their configs): boot.efi stopped with
    # EB.MM.AKM Err(0xE) / STOP 0x16 ("Couldn't allocate runtime area") on Ryzen boards with SetupVirtualMap on. The engine
    # turns it off only for chipsets it can NAME (B450 X470 A520 B550 X570 TRX40), and Hardware Sniffer reads an AMD chipset
    # only from the board's product name - every AM4/AM5 FCH has the same PCI ID - so most boards report plain "AMD" and
    # AM5 (A620 B650 X670 X870) is not on the list at all. Dortania (AMD Zen config, Booter > Quirks): SetupVirtualMap off on
    # those boards. Keep it on only for the chipsets known to need it.
    cpu = (result.hardware or {}).get("CPU", {}) or {}
    chipset = ((result.hardware or {}).get("Motherboard", {}) or {}).get("Chipset", "")
    quirks = cfg.get("Booter", {}).get("Quirks", {})
    zen45 = cpu.get("Manufacturer") == "AMD" and is_zen4_or_later(cpu)
    if cpu.get("Manufacturer") == "AMD" and chipset not in AMD_SVM_ON and not zen45 and quirks.get("SetupVirtualMap") is True:
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
    # AM4 and older Zen boot with it off (1 stop in more than 150 boots), so the rule above still holds for them.
    # The same machines prove it, not only the totals: five AM5 boards (B650M DS3H, TUF B650M-PLUS, B850 AORUS ELITE,
    # X870E CARBON, B850 TOMAHAWK) stopped at AKM with both quirks off and passed boot.efi on their next stick with
    # DevirtualiseMmio AND SetupVirtualMap on; a 7500F went on/pass, off/AKM, on/pass. Both on is the set with the
    # most passes (31 hand-offs); the boot-log ladder (bootfix.py) moves on from there if a board still stops.
    if cpu.get("Manufacturer") == "AMD" and chipset not in AMD_DEVMMIO_ON and not zen45 and quirks.get("DevirtualiseMmio") is True:
        quirks["DevirtualiseMmio"] = False
        change("amd-devirtualisemmio", "DevirtualiseMmio=True", "DevirtualiseMmio=False",
               f"Ryzen board (chipset reported as {chipset or 'unknown'}): boot.efi cannot allocate the kernel's memory with it on")
    if zen45 and not (quirks.get("DevirtualiseMmio") is True and quirks.get("SetupVirtualMap") is True):
        before = f"DevirtualiseMmio={quirks.get('DevirtualiseMmio')}, SetupVirtualMap={quirks.get('SetupVirtualMap')}"
        quirks["DevirtualiseMmio"] = True
        quirks["SetupVirtualMap"] = True
        change("amd-zen4-memory-map", before, "DevirtualiseMmio=True, SetupVirtualMap=True",
               f"{cpu.get('Processor Name') or 'Zen 4/5 Ryzen'}: boot.efi stops at EB.MM.AKM on these CPUs with them off")
    # 1401 issue #30 (10-11): Ryzen 9950X/X870, 9700X/X870, 9800X3D/B850 froze hard about 19 minutes into the macOS
    # install (Caps Lock dead) on 1.10-1.13, past a new SSD, stick and port. ReleaseUsbOwnership was already on in every
    # 1401 EFI (172 of 175 uploaded Ryzen configs); DisableVariableWrite was off in 173 of 175, and the 9800X3D's owner
    # reported the install finished once it was on. These boards run with the firmware memory map rewritten (the two quirks
    # above), and the installer's NVRAM writes go through the firmware's runtime services; with this quirk OpenRuntime
    # refuses them before they reach the firmware. Needs OpenRuntime.efi, which every 1401 EFI loads. macOS cannot keep its
    # own NVRAM changes (startup disk choice) on these machines; OpenCore's config still sets every variable at boot.
    if zen45 and quirks.get("DisableVariableWrite") is not True:
        before = f"DisableVariableWrite={quirks.get('DisableVariableWrite')}"
        quirks["DisableVariableWrite"] = True
        change("amd-zen4-variable-write", before, "DisableVariableWrite=True",
               f"{cpu.get('Processor Name') or 'Zen 4/5 Ryzen'}: the installer froze about 19 minutes in while writing NVRAM")
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
    # every build, so a verified setup remains reproducible. Checked before 5, so a newer failed boot's own log still wins.
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
    texts = []
    if getattr(policy, "boot_logs", None) or getattr(policy, "stopped_at", ""):
        from . import bootfix  # noqa: PLC0415
        texts = bootfix.read_logs(policy.boot_logs)
        bootfix.apply(cfg, result, texts, change, getattr(policy, "stopped_at", ""))
        for note in bootfix.apply_after_handoff(cfg, texts, policy.stopped_at, change)["report"]:
            change("bootlog-note", "", note, "from the last failed start")

    # 5b. NVRAM writes through a rewritten memory map. Boards stopped POSTing after macOS wrote NVRAM through the firmware
    # with SetupVirtualMap or DevirtualiseMmio on (AM5 X870/B650 and an AM4 5600X, chat 10-10..10-15, some needing BIOS
    # flashback or an RMA). Every report was an EFI without DisableVariableWrite: built before 1.14, hand-edited, or not
    # Zen 4/5 by name. The rule follows the risk, not the CPU name, and runs after the boot-log ladder, which can turn
    # either quirk on. It needs OpenRuntime.efi, which hosts the quirk.
    if cpu.get("Manufacturer") == "AMD":
        bq = cfg.setdefault("Booter", {}).setdefault("Quirks", {})
        remapped = bq.get("SetupVirtualMap") is True or bq.get("DevirtualiseMmio") is True
        ort = any(isinstance(d, dict) and d.get("Path") == "OpenRuntime.efi" and d.get("Enabled", True)
                  for d in cfg.get("UEFI", {}).get("Drivers", []))
        if remapped and ort:
            # Opt-in (Policy.persistent_nvram_amd): OpenCore's emulated NVRAM replaces the guard. macOS writes then reach
            # an in-memory store that the LogoutHook saves to nvram.plist on the ESP, so iMessage, Apple ID and the
            # startup-disk choice persist, while the fragile firmware flash is still never written. DisableVariableWrite
            # is turned OFF only in that case, because it is implemented in OpenRuntime.efi - the OUTERMOST driver in the
            # LoadEarly order the doc requires - so with it on it would reject the same macOS writes before they reached
            # the emulated store, and nothing would persist. Default builds (and an opt-in build whose OpenCore release
            # has no OpenVariableRuntimeDxe) keep the guard: switching it off is unproven on real AMD hardware until
            # testers confirm it.
            emulated, why_not = (False, None)
            if getattr(policy, "persistent_nvram_amd", False):
                emulated, why_not = _enable_emulated_nvram(cfg, config_path, change)
            if emulated:
                if bq.get("DisableVariableWrite") is True:
                    bq["DisableVariableWrite"] = False
                    change("amd-nvram-emulated-write", "DisableVariableWrite=True", "DisableVariableWrite=False",
                           "emulated NVRAM replaces the guard: macOS writes go to the in-memory store and nvram.plist, "
                           "never the fragile firmware flash")
            elif bq.get("DisableVariableWrite") is not True:
                before = f"DisableVariableWrite={bq.get('DisableVariableWrite')}"
                bq["DisableVariableWrite"] = True
                why = "AMD with the firmware memory map rewritten: macOS NVRAM writes have stopped boards from POSTing"
                if why_not:
                    why += f" (persistent-NVRAM opt-in kept the guard: {why_not})"
                change("amd-nvram-write-guard", before, "DisableVariableWrite=True", why)

    # 6. The cosmetic EFI logo is an explicit opt-in. Default builds disable an existing entry
    # after reported firmware hangs; no other boot driver or recovery entry is changed.
    import shutil  # noqa: PLC0415
    logo_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "NullMothLogo.efi")
    drivers = cfg.setdefault("UEFI", {}).setdefault("Drivers", [])
    # A firmware that refused the logo driver at the stick's last start (a Gigabyte AORUS: "NullMothLogo.efi at 3 cannot
    # be loaded - Unsupported!", and OpenCore went no further) gets it turned off, opt-in or not.
    refused = any(re.search(r"NullMothLogo\.efi at \d+ cannot be (loaded|found)", t or "") for t in (texts or []))
    if refused:
        for entry in drivers:
            if isinstance(entry, dict) and entry.get("Path") == "NullMothLogo.efi" and entry.get("Enabled"):
                entry["Enabled"] = False
                change("boot-logo", "enabled", "disabled", "this PC's firmware refused the logo driver at the last start")
    if not refused and getattr(policy, "boot_logo", False) and os.path.isfile(logo_src) and not any(d.get("Path") == "NullMothLogo.efi" for d in drivers):
        ddir = os.path.join(os.path.dirname(config_path), "Drivers")
        os.makedirs(ddir, exist_ok=True)
        shutil.copyfile(logo_src, os.path.join(ddir, "NullMothLogo.efi"))
        entry = {"Arguments": "", "Comment": "NullMoth boot logo", "Enabled": True, "LoadEarly": False, "Path": "NullMothLogo.efi"}
        if drivers and "HideVerbose" in drivers[0]:   # only the keys this OpenCore's own entries carry
            entry["HideVerbose"] = False
        drivers.append(entry)
        change("boot-logo", "Apple logo", "NullMoth logo", "explicit diagnostic opt-in; default builds leave the cosmetic EFI driver disabled")

    if not refused and getattr(policy, "boot_logo", False) and os.path.isfile(logo_src):
        for entry in drivers:
            if isinstance(entry, dict) and entry.get("Path") == "NullMothLogo.efi" and not entry.get("Enabled"):
                ddir = os.path.join(os.path.dirname(config_path), "Drivers")
                os.makedirs(ddir, exist_ok=True)
                shutil.copyfile(logo_src, os.path.join(ddir, "NullMothLogo.efi"))
                entry["Enabled"] = True
                change("boot-logo", "disabled", "enabled", "explicit diagnostic opt-in")

    if not getattr(policy, "boot_logo", False):
        for entry in drivers:
            if isinstance(entry, dict) and entry.get("Path") == "NullMothLogo.efi" and entry.get("Enabled"):
                entry["Enabled"] = False
                change("boot-logo", "enabled", "disabled", "cosmetic EFI driver implicated in firmware boot hangs; normal boot drivers preserved")

    # 7. Tahoe + the IOSkywalkFamily downgrade (Broadcom or Intel Wi-Fi) + a Realtek 2.5G/5G port on Lucy: macOS 26 adds
    #    its own Realtek driver (AppleEthernetRL, RTL8124-8127), which loads at boot to probe the port and links against
    #    Tahoe's IOSkywalkFamily. With that family blocked for the downgrade, the machine stops at the Apple logo with no
    #    panic. Lucy drives the port, so Apple's driver is blocked too; macOS 15 has no such driver and is left alone.
    lucy = {"RTL812xLucy.kext", "LucyRTL8125Ethernet.kext"} & enabled
    blocks = cfg["Kernel"].setdefault("Block", [])
    skywalk_downgrade = any(b.get("Identifier") == "com.apple.iokit.IOSkywalkFamily" and b.get("Enabled") for b in blocks)
    if tahoe and skywalk_downgrade and lucy and not any(b.get("Identifier") == "com.apple.driver.AppleEthernetRL" for b in blocks):
        blocks.append({"Arch": "x86_64", "Comment": "Apple Realtek Ethernet on 26 (Lucy drives the port)", "Enabled": True,
                       "Identifier": "com.apple.driver.AppleEthernetRL", "MaxKernel": "", "MinKernel": "25.0.0",
                       "Strategy": "Exclude"})
        change("tahoe-realtek-ethernet", "AppleEthernetRL", "blocked (" + ", ".join(sorted(lucy)) + " drives the port)",
               "with the IOSkywalkFamily downgrade, Apple's Realtek driver stops macOS 26 at the Apple logo")

    # 8. NVMe drives macOS struggles with: the install target is only found missing at install time, after the long
    # download and build. The scan now records the drive models (Storage Drives on the raw report); warn up front, and
    # enable NVMeFix for the OEM families whose drop-outs a power-state fix is known to clear.
    from . import storage_drives  # noqa: PLC0415
    raw = getattr(result, "raw_hardware", None) or (result.hardware or {})
    if storage_drives.wants_nvmefix(raw):
        for k in kexts:
            if k.get("BundlePath", "").split("/")[-1] == "NVMeFix.kext" and not k.get("Enabled"):
                k["Enabled"] = True
                change("storage-nvmefix", "NVMeFix off", "NVMeFix on",
                       "this PC has an OEM NVMe drive that can drop out under macOS power management")
    sd_warning = storage_drives.warning(raw)
    if sd_warning:
        change("storage-drive-warning", "", sd_warning,
               "the scan recorded an NVMe drive macOS is known to have trouble with")

    tmp = config_path + ".tmp"
    with open(tmp, "wb") as fh:
        plistlib.dump(cfg, fh)
    os.replace(tmp, config_path)
    return changes


def _legal_comment(text):
    # ocvalidate accepts a Comment only when every character is printable ASCII below "~" (OcAsciiLib IsAsciiPrint:
    # ' ' <= c < '~'). A "~" in one community driver's text failed every build that added it (1401 #101).
    out = "".join(c if " " <= c < "~" else "-" if c in "\u2013\u2014" else "" for c in text)
    return out.replace("~", "")


def legal_comments(config_path):
    """Rewrite every Comment in config.plist to the characters ocvalidate accepts. Runs last, after every pass that
    adds entries, so text from any source (engine, policy, community drivers) cannot fail validation."""
    with open(config_path, "rb") as fh:
        cfg = plistlib.load(fh)
    fixed = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "Comment" and isinstance(v, str):
                    clean = _legal_comment(v)
                    if clean != v:
                        node[k] = clean
                        fixed.append((v, clean))
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(cfg)
    if not fixed:
        return []
    tmp = config_path + ".tmp"
    with open(tmp, "wb") as fh:
        plistlib.dump(cfg, fh)
    os.replace(tmp, config_path)
    return [{"rule": "legal-comments", "before": b, "after": a,
             "why": "ocvalidate refuses a Comment with characters outside printable ASCII below '~'"} for b, a in fixed]
