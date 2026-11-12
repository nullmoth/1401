"""Experimental targets: the macOS releases before 15 (10.7 Lion to 14 Sonoma) on a PC with an NVIDIA card the
NullMoth driver covers.

Nothing here is offered unless the user turns "experimental older macOS" on. The driver for these releases is a kit
built for exactly one release each (driver repository, build/legacy); it has been compiled, linked against that
release's own kernel and class tables, and never run on a card. The boot side is equally unproven on real hardware.

How a build for an older release is made:
  14 to 10.13   the engine builds for that release as it does for any other; the card is kept by nullmoth.mark.
  10.12 to 10.7 the engine cannot build below 10.13, so it builds for 10.13 and convert() changes the result for the
                older release. Every change carries its source:
                  DOC       OpenCore's configuration reference
                  MEASURED  read from Apple's recovery image of that release, or from the kext's own binary
                  CHOICE    ours; the reason is in the rule
10.6 is not offered: Apple serves no recovery image for it.

    python3 -m p1401.legacy --selftest
"""
import copy
import hashlib
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))

# Darwin major -> release label (the kit's name and the installer's check use the label)
RELEASE = {11: "10.7", 12: "10.8", 13: "10.9", 14: "10.10", 15: "10.11", 16: "10.12", 17: "10.13", 18: "10.14",
           19: "10.15", 20: "11", 21: "12", 22: "13", 23: "14"}
NAME = {11: "Mac OS X 10.7 Lion", 12: "OS X 10.8 Mountain Lion", 13: "OS X 10.9 Mavericks", 14: "OS X 10.10 Yosemite",
        15: "OS X 10.11 El Capitan", 16: "macOS 10.12 Sierra", 17: "macOS 10.13 High Sierra", 18: "macOS 10.14 Mojave",
        19: "macOS 10.15 Catalina", 20: "macOS 11 Big Sur", 21: "macOS 12 Monterey", 22: "macOS 13 Ventura",
        23: "macOS 14 Sonoma"}
ENGINE_FLOOR = 17          # the lowest release the engine itself builds for
MARKER = ".nullmoth-legacy"  # in the EFI build folder: the Darwin major the build is for (the stick writer reads it)

# The display driver alone; the accelerator stays off until the user adds nvaccel=1 after the desktop is confirmed.
BOOT_ARGS = ("nvfb=1", "nvfbheads=4", "-nvkmsnosmooth")

with open(os.path.join(HERE, "legacy_kits.json")) as _fh:
    KITS = json.load(_fh)

# Kernel quirks with a first release (DOC: the "Requirement" line of each). Switched off below it.
QUIRK_FIRST = {"XhciPortLimit": 15, "PanicNoKextDump": 17, "PowerTimeoutKernelPanic": 19, "DisableIoMapper": 12,
               "DisableIoMapperMapping": 22, "AppleXcpmCfgLock": 12, "AppleXcpmExtraMsrs": 12, "AppleXcpmForceBoost": 12,
               "SetApfsTrimTimeout": 18, "IncreasePciBarSize": 14, "ForceSecureBootScheme": 20,
               "ExtendBTFeatureFlags": 12, "ForceAquantiaEthernet": 19, "CustomPciSerialDevice": 11}
# DisableLinkeditJettison is not in the table: its entry says 11, but OpenCore's validator refuses a config that loads
# Lilu without it on any release.

# Kext floors as Darwin majors. MEASURED from each kext's kernel-interface versions (current public releases); NVMeFix
# and USBToolBox also from what the release itself ships (no NVMe family before 10.10, no IOUSBHostFamily before 10.11).
KEXT_FLOOR = {"Lilu": 8, "VirtualSMC": 8, "AppleALC": 8, "AppleALCU": 8, "SMCBatteryManager": 8, "WhateverGreen": 10,
              "SMCSuperIO": 10, "SMCLightSensor": 10, "SMCProcessor": 11, "SMCDellSensors": 11, "RestrictEvents": 12,
              "CpuTscSync": 12, "NVMeFix": 18, "USBToolBox": 15, "UTBMap": 15, "UTBDefault": 15}

# What the release itself can drive. MEASURED: presence of Apple's own kext in that release's recovery image.
NATIVE = {11: {"nvme": False, "xhci": True, "usbhost": False, "apfs": False},
          12: {"nvme": False, "xhci": True, "usbhost": False, "apfs": False},
          13: {"nvme": False, "xhci": True, "usbhost": False, "apfs": False},
          14: {"nvme": True, "xhci": True, "usbhost": False, "apfs": False},
          15: {"nvme": True, "xhci": True, "usbhost": True, "apfs": False},
          16: {"nvme": True, "xhci": True, "usbhost": True, "apfs": True}}

# Intel generations in order, and the newest one each release's last update knows. A processor newer than that is
# presented to the kernel as the newest one the release knows (Kernel.Emulate), with Apple's power management kext
# kept from loading (DOC: DummyPowerManagement, 10.4 to 12). CHOICE, NOT VERIFIED on hardware: the build says so.
INTEL_ORDER = ["Nehalem", "Westmere", "Sandy Bridge", "Ivy Bridge", "Haswell", "Broadwell", "Skylake", "Kaby Lake"]
NEWEST_KNOWN = {11: "Ivy Bridge", 12: "Haswell", 13: "Haswell", 14: "Broadwell", 15: "Skylake", 16: "Kaby Lake"}
CPUID = {"Ivy Bridge": 0x0306A9, "Haswell": 0x0306C3, "Broadwell": 0x0306D4, "Skylake": 0x0506E3, "Kaby Lake": 0x0906E9}
# A Mac model each converted release supports (CHOICE): one desktop and one notebook cover 10.7 to 10.12.
MODEL = {"desktop": "MacPro5,1", "laptop": "MacBookPro9,1"}


class LegacyRefused(RuntimeError):
    """This PC cannot run the release that was asked for; the message says why and what would."""


def target(macos):
    """The Darwin major of an experimental target, or None when `macos` is not one (15 and 26 are not)."""
    try:
        d = int(macos)
    except (TypeError, ValueError):
        return None
    return d if d in RELEASE else None


def converted(darwin):
    return darwin is not None and darwin < ENGINE_FLOOR


def kit(darwin):
    """The kit package for this release: {"name", "url", "sha256"}; sha256 is "" until a release pins it."""
    rel = RELEASE[darwin]
    k = (KITS.get("kits") or {}).get(rel) or {}
    name = k.get("name") or f"nullmoth-nvidia-legacy-{rel}-{KITS['version']}.tar.gz"
    return {"name": name, "url": KITS["base"] + name, "sha256": k.get("sha256", "")}


def _intel_index(codename):
    c = (codename or "").lower()
    for i, n in enumerate(INTEL_ORDER):
        if n.lower() in c:
            return i
    return None


def check_hardware(report, darwin):
    """Raises LegacyRefused when the PC cannot run this release at all. Returns notes (limits the user must know)."""
    cpu = report.get("CPU") or {}
    notes = []
    amd = "amd" in (cpu.get("Manufacturer") or "").lower()
    if amd and darwin < 17:
        raise LegacyRefused(f"{NAME[darwin]} cannot run on an AMD processor: the kernel patches AMD needs start at "
                            f"macOS 10.13. Pick macOS 10.13 High Sierra or newer.")
    if darwin < ENGINE_FLOOR:
        n = NATIVE[darwin]
        # the scan names a controller by its PCI device name; every bus reads "PCI", so NVMe is told by the name or
        # by the drives on it. Controllers with no drive are not counted.
        ctl = [(name + " " + " ".join(c.get("Disk Drives") or [])).lower()
               for name, c in (report.get("Storage Controllers") or {}).items() if c.get("Disk Drives")]
        if ctl and all("nvme" in x or "non-volatile" in x for x in ctl) and not n["nvme"]:
            raise LegacyRefused(f"{NAME[darwin]} has no NVMe driver and this PC has only NVMe disks. Pick OS X 10.10 "
                                f"Yosemite or newer, or add a SATA disk for macOS.")
        if not n["nvme"]:
            notes.append(f"{NAME[darwin]} has no NVMe driver: install it on a SATA or USB disk.")
        if not n["usbhost"]:
            notes.append(f"{NAME[darwin]} is older than the USB port maps 1401 makes; the USB map kext is left out and "
                         f"some ports may not work.")
        if not n["apfs"]:
            notes.append(f"{NAME[darwin]} cannot read APFS: the disk must be formatted Mac OS Extended (Journaled).")
    return notes


def model_for(report):
    return MODEL["laptop" if (report.get("Motherboard") or {}).get("Platform") == "Laptop" else "desktop"]


def convert(cfg, darwin, report=None):
    """A config built for 10.13 -> one for the older release. Returns (new config, [changes], [notes]).
    The input is not modified."""
    if darwin not in NATIVE:
        raise ValueError(f"Darwin {darwin} is not a converted release")
    rel = RELEASE[darwin]
    c = copy.deepcopy(cfg)
    ch, notes = [], []

    def put(section, sub, key, value, why):
        node = c.setdefault(section, {}).setdefault(sub, {})
        old = node.get(key, "<absent>")
        if old != value:
            node[key] = value
            ch.append(("legacy-" + key, str(old), str(value), why))

    put("Misc", "Security", "SecureBootModel", "Disabled",
        "DOC: a system shipped before the secure-boot model was released will not boot; the lowest model minimum is 10.13.2")
    if darwin <= 11:
        put("Kernel", "Scheme", "KernelArch", "x86_64",
            "DOC: 10.7 can start a 32-bit kernel; CHOICE: the driver is 64-bit only")
    put("Kernel", "Scheme", "KernelCache", "Auto", "DOC: Auto picks the cache form the release supports")

    q = c.setdefault("Kernel", {}).setdefault("Quirks", {})
    for name, first in sorted(QUIRK_FIRST.items()):
        if q.get(name) is True and darwin < first:
            q[name] = False
            ch.append(("legacy-quirk", name + "=on", name + "=off", f"DOC: this quirk's requirement starts at Darwin {first}"))

    kept = []
    for e in c.get("Kernel", {}).get("Add", []) or []:
        name = os.path.basename(str(e.get("BundlePath", ""))).replace(".kext", "")
        floor = KEXT_FLOOR.get(name)
        if floor is not None and darwin < floor:
            ch.append(("legacy-kext", name, "removed", f"MEASURED: {name} needs Darwin {floor} or later"))
            continue
        if floor is None and e.get("Enabled"):
            notes.append(f"{name}.kext: not checked on {NAME[darwin]}; it is left in and may not load.")
        # an entry bounded for the release the engine built for must reach down to the release it is converted to
        mk = str(e.get("MinKernel") or "")
        try:
            if mk and int(mk.split(".")[0]) > darwin and floor is not None:
                e["MinKernel"] = ""
                ch.append(("legacy-kext", f"{name} MinKernel {mk}", "no minimum", f"MEASURED: {name} loads from Darwin {floor}"))
        except ValueError:
            pass
        kept.append(e)
    if "Kernel" in c and "Add" in c["Kernel"]:
        c["Kernel"]["Add"] = kept

    drivers = c.setdefault("UEFI", {}).setdefault("Drivers", [])
    names = [str(x.get("Path", "") if isinstance(x, dict) else x) for x in drivers]
    if not any(n in ("OpenHfsPlus.efi", "HfsPlus.efi", "HfsPlusLegacy.efi") for n in names):
        drivers.append({"Arguments": "", "Comment": "HFS+ for releases before APFS", "Enabled": True,
                        "LoadEarly": False, "Path": "OpenHfsPlus.efi"})
        ch.append(("legacy-hfs", "", "OpenHfsPlus.efi", "MEASURED: this release's installer and disk are HFS+"))

    nv = c.setdefault("NVRAM", {}).setdefault("Add", {}).setdefault("7C436110-AB2A-4BBB-A880-FE41995C9F82", {})
    args = (nv.get("boot-args") or "").split()
    if darwin == 14 and "kext-dev-mode=1" not in args:
        args.append("kext-dev-mode=1")
        ch.append(("legacy-boot-args", "", "kext-dev-mode=1", "MEASURED: 10.10 loads an unsigned kext only with this argument"))
    if darwin <= 11 and "arch=x86_64" not in args:
        args.append("arch=x86_64")
        ch.append(("legacy-boot-args", "", "arch=x86_64", "CHOICE: the driver is 64-bit only"))
    nv["boot-args"] = " ".join(args)

    cpu = (report or {}).get("CPU") or {}
    idx, newest = _intel_index(cpu.get("Codename")), NEWEST_KNOWN[darwin]
    if idx is None or idx > INTEL_ORDER.index(newest):
        val = CPUID[newest]
        emu = c.setdefault("Kernel", {}).setdefault("Emulate", {})
        emu["Cpuid1Data"] = val.to_bytes(4, "little") + bytes(12)
        emu["Cpuid1Mask"] = bytes.fromhex("FFFFFFFF") + bytes(12)
        emu["DummyPowerManagement"] = True
        ch.append(("legacy-cpu", cpu.get("Codename") or "unknown processor", f"presented as {newest} (0x{val:06X})",
                   f"CHOICE, NOT VERIFIED: {NAME[darwin]} does not know processors after {newest}"))
        notes.append(f"This processor is newer than {NAME[darwin]} knows. The build presents it as {newest} and keeps "
                     f"Apple's power management off. This has not been tried on real hardware.")
    notes.append(f"{NAME[darwin]} is an experimental target: the boot configuration and the NVIDIA driver kit for it "
                 f"have been checked against Apple's own files for this release, and have not been run on a PC.")
    return c, ch, notes


def apply(config_path, darwin, report, change):
    """Policy-pass step for a converted release: rewrites config.plist in place. change(rule, before, after, why)."""
    import plistlib  # noqa: PLC0415
    with open(config_path, "rb") as fh:
        cfg = plistlib.load(fh)
    new, changes, notes = convert(cfg, darwin, report)
    tmp = config_path + ".tmp"
    with open(tmp, "wb") as fh:
        plistlib.dump(new, fh)
    os.replace(tmp, config_path)
    for rule, before, after, why in changes:
        change(rule, before, after, why)
    return notes


def driver_args(cfg, change):
    """The NullMoth boot arguments for an experimental release: the display driver only."""
    nv = cfg["NVRAM"]["Add"].setdefault("7C436110-AB2A-4BBB-A880-FE41995C9F82", {})
    args = [a for a in (nv.get("boot-args") or "").split() if a != "nvaccel=1"]
    add = [a for a in BOOT_ARGS if a not in args]
    if add or "nvaccel=1" in (nv.get("boot-args") or "").split():
        nv["boot-args"] = " ".join(args + add)
        change("nullmoth-legacy-boot-args", "", " ".join(add),
               "experimental release: the NVIDIA display driver starts; the accelerator stays off until nvaccel=1 is added")


def write_marker(out_dir, darwin):
    tmp = os.path.join(out_dir, MARKER + ".tmp")
    with open(tmp, "w") as fh:
        fh.write(f"{darwin}\n")
    os.replace(tmp, os.path.join(out_dir, MARKER))


def read_marker(efi_build_dir):
    try:
        with open(os.path.join(efi_build_dir, MARKER)) as fh:
            d = int(fh.read().strip())
    except (OSError, ValueError):
        return None
    return d if d in RELEASE else None


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def stage(usb_root, cache_dir, darwin, fetch=None):
    """Puts the kit for this release on the stick under NullMoth/. The SHA-256 is checked before and after the copy;
    a kit with no pinned SHA-256 (not released yet) is refused rather than staged unchecked."""
    k = kit(darwin)
    if not k["sha256"]:
        raise RuntimeError(f"the NVIDIA driver kit for {NAME[darwin]} has not been released yet")
    src = os.path.join(cache_dir, k["name"])
    if not os.path.exists(src) or _sha(src) != k["sha256"]:
        if fetch is None:
            raise RuntimeError(f"driver kit missing or wrong in {cache_dir}")
        try:
            fetch(k["url"], src + ".part")
        except Exception as e:  # noqa: BLE001 - GitHub failing: the same file from the site, checked the same way
            from . import nullmoth  # noqa: PLC0415
            mirror = nullmoth.mirror_of(k["url"])
            if not mirror:
                raise
            print(f"(GitHub download failed: {e}; trying the NullMoth mirror)", flush=True)
            if os.path.exists(src + ".part"):
                os.remove(src + ".part")
            fetch(mirror, src + ".part")
        if _sha(src + ".part") != k["sha256"]:
            os.remove(src + ".part")
            raise RuntimeError("driver kit download does not match its SHA-256 - not written to the stick")
        os.replace(src + ".part", src)
    d = os.path.join(usb_root, "NullMoth")
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, k["name"])
    shutil.copyfile(src, dst + ".part")
    if _sha(dst + ".part") != k["sha256"]:
        os.remove(dst + ".part")
        raise RuntimeError("the driver kit read back different from the stick")
    os.replace(dst + ".part", dst)
    folder = k["name"][:-len(".tar.gz")]
    with open(os.path.join(d, "README.txt"), "w") as fh:
        fh.write(f"NullMoth NVIDIA driver kit for {NAME[darwin]} (experimental).\n"
                 f"After macOS finishes installing, open Terminal and run:\n"
                 f"    cd ~ && tar -xzf /Volumes/1401/NullMoth/{k['name']}\n"
                 f"    sudo sh ~/{folder}/install-legacy.sh\n"
                 f"It checks the kit against this macOS before it changes anything. The 1401 Mac app does not run on "
                 f"this release.\n")
    return dst


def selftest():
    import tempfile  # noqa: PLC0415
    fails = []

    def arm(name, ok, detail=""):
        print(("ok   " if ok else "FAIL ") + name + (f" ({detail})" if detail else ""))
        if not ok:
            fails.append(name)

    base = {"Misc": {"Security": {"SecureBootModel": "Default"}},
            "Kernel": {"Scheme": {"KernelArch": "Auto", "KernelCache": "Auto", "FuzzyMatch": True},
                       "Quirks": {"XhciPortLimit": True, "DisableIoMapper": True, "AppleCpuPmCfgLock": True,
                                  "PanicNoKextDump": True, "DisableLinkeditJettison": True},
                       "Add": [{"BundlePath": "Lilu.kext", "Enabled": True, "MinKernel": "17.0.0"},
                               {"BundlePath": "NVMeFix.kext", "Enabled": True},
                               {"BundlePath": "USBToolBox.kext", "Enabled": True},
                               {"BundlePath": "Mystery.kext", "Enabled": True}],
                       "Emulate": {"DummyPowerManagement": False}},
            "UEFI": {"Drivers": [{"Path": "OpenRuntime.efi", "Enabled": True}]},
            "NVRAM": {"Add": {"7C436110-AB2A-4BBB-A880-FE41995C9F82": {"boot-args": "-v"}}}}
    snap = copy.deepcopy(base)
    coffee = {"CPU": {"Manufacturer": "Intel", "Codename": "Coffee Lake"}, "Motherboard": {"Platform": "Desktop"},
              "Storage Controllers": {"SATA AHCI Controller": {"Bus Type": "PCI", "Disk Drives": ["SSD 870"]}}}
    c, ch, notes = convert(base, 11, coffee)
    names = [e["BundlePath"] for e in c["Kernel"]["Add"]]
    rules = [r for r, *_ in ch]
    arm("the input config is never modified", base == snap)
    arm("10.7: the secure boot model is Disabled", c["Misc"]["Security"]["SecureBootModel"] == "Disabled")
    arm("10.7: the kernel is pinned to 64-bit, in the scheme and in the boot arguments",
        c["Kernel"]["Scheme"]["KernelArch"] == "x86_64" and "arch=x86_64" in c["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"])
    arm("10.7: kexts above their floor are removed", "NVMeFix.kext" not in names and "USBToolBox.kext" not in names)
    arm("10.7: a kext at its floor stays and loses the minimum the engine gave it",
        "Lilu.kext" in names and next(e for e in c["Kernel"]["Add"] if e["BundlePath"] == "Lilu.kext")["MinKernel"] == "")
    arm("10.7: a kext nobody measured is kept and reported, not silently kept",
        "Mystery.kext" in names and any("Mystery" in n for n in notes))
    arm("10.7: a quirk that starts later is switched off, one valid since 10.4 stays on",
        c["Kernel"]["Quirks"]["XhciPortLimit"] is False and c["Kernel"]["Quirks"]["AppleCpuPmCfgLock"] is True)
    arm("10.7: the quirk Lilu needs stays on", c["Kernel"]["Quirks"]["DisableLinkeditJettison"] is True)
    arm("10.7: an HFS+ driver is added", any(d.get("Path") == "OpenHfsPlus.efi" for d in c["UEFI"]["Drivers"]))
    arm("10.7 on Coffee Lake: the processor is presented as Ivy Bridge with power management off",
        c["Kernel"]["Emulate"]["Cpuid1Data"][:4] == bytes.fromhex("A9060300") and c["Kernel"]["Emulate"]["DummyPowerManagement"] is True
        and "legacy-cpu" in rules)
    arm("the unproven processor choice is said out loud", any("not been tried on real hardware" in n for n in notes))
    ivy = dict(coffee, CPU={"Manufacturer": "Intel", "Codename": "Ivy Bridge"})
    c2, ch2, _ = convert(base, 11, ivy)
    arm("10.7 on Ivy Bridge: the processor is left alone", "Cpuid1Data" not in c2["Kernel"]["Emulate"]
        and not any(r == "legacy-cpu" for r, *_ in ch2))
    c3, _, _ = convert(base, 14, coffee)
    a3 = c3["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"]
    arm("10.10: unsigned kexts are allowed by boot argument, and the kernel is not pinned",
        "kext-dev-mode=1" in a3 and "arch=x86_64" not in a3 and c3["Kernel"]["Scheme"]["KernelArch"] == "Auto")
    c4, _, _ = convert(base, 16, coffee)
    n4 = [e["BundlePath"] for e in c4["Kernel"]["Add"]]
    arm("10.12: the USB map kext stays, NVMeFix goes, XhciPortLimit stays on",
        "USBToolBox.kext" in n4 and "NVMeFix.kext" not in n4 and c4["Kernel"]["Quirks"]["XhciPortLimit"] is True)
    try:
        convert(base, 17, coffee); raised = False
    except ValueError:
        raised = True
    arm("10.13 is not converted (the engine builds it itself)", raised)

    def refused(report, d):
        try:
            check_hardware(report, d); return ""
        except LegacyRefused as e:
            return str(e)
    ryzen = {"CPU": {"Manufacturer": "AMD", "Codename": "Vermeer"},
             "Storage Controllers": {"SATA AHCI Controller": {"Bus Type": "PCI", "Disk Drives": ["SSD 870"]}}}
    arm("an AMD processor is refused below 10.13 and told what would work", "10.13" in refused(ryzen, 16))
    arm("an AMD processor is accepted from 10.13", refused(ryzen, 17) == "" and refused(ryzen, 23) == "")
    nvme = {"CPU": {"Manufacturer": "Intel", "Codename": "Coffee Lake"},
            "Storage Controllers": {"E12 NVMe Controller": {"Bus Type": "PCI", "Disk Drives": ["MP400"]},
                                    "SATA AHCI Controller": {"Bus Type": "PCI"}}}
    arm("a PC with only NVMe disks is refused before 10.10", "NVMe" in refused(nvme, 13))
    arm("the same PC is accepted on 10.10", refused(nvme, 14) == "")
    arm("a PC with a SATA disk is accepted on 10.7, with the NVMe limit as a note",
        refused(coffee, 11) == "" and any("NVMe" in n for n in check_hardware(coffee, 11)))
    arm("15 and 26 are not experimental targets; 10.6 is not a target", target("24") is None and target("25") is None and target("10") is None)
    arm("every target has a release label, a name and a kit name",
        all(d in NAME and kit(d)["name"].startswith("nullmoth-nvidia-legacy-" + RELEASE[d] + "-") for d in RELEASE))
    arm("a notebook gets a notebook model, a desktop a desktop model",
        model_for({"Motherboard": {"Platform": "Laptop"}}) == "MacBookPro9,1" and model_for(coffee) == "MacPro5,1")
    with tempfile.TemporaryDirectory() as d:
        write_marker(d, 13)
        arm("the build folder remembers the release for the stick writer", read_marker(d) == 13)
        arm("a build folder without the marker is an ordinary build", read_marker(os.path.join(d, "none")) is None)
        usb, cache = os.path.join(d, "usb"), os.path.join(d, "cache")
        os.makedirs(usb); os.makedirs(cache)
        saved = copy.deepcopy(KITS)
        try:
            KITS.setdefault("kits", {})[RELEASE[13]] = {"sha256": ""}
            try:
                stage(usb, cache, 13); ok = False
            except RuntimeError as e:
                ok = "not been released" in str(e)
            arm("a kit with no pinned SHA-256 is refused, not staged unchecked", ok)
            name = kit(13)["name"]
            with open(os.path.join(cache, name), "wb") as fh:
                fh.write(b"kit")
            KITS["kits"][RELEASE[13]] = {"sha256": hashlib.sha256(b"kit").hexdigest()}
            dst = stage(usb, cache, 13)
            arm("a kit that matches its pin is copied to the stick with how to run it",
                os.path.exists(dst) and "install-legacy.sh" in open(os.path.join(usb, "NullMoth", "README.txt")).read())
            os.remove(os.path.join(cache, name))
            tried = []

            def fetch(url, path):
                tried.append(url)
                if "github.com" in url:
                    raise OSError("504")
                with open(path, "wb") as fh:
                    fh.write(b"kit")
            stage(usb, cache, 13, fetch=fetch)
            arm("when GitHub fails the kit comes from the site's copy and is checked the same way",
                len(tried) == 2 and tried[1].startswith("https://nullmothsystems.com/download/nvidia/v"), str(tried))
            KITS["kits"][RELEASE[13]] = {"sha256": "0" * 64}
            try:
                stage(usb, cache, 13); ok = False
            except RuntimeError:
                ok = True
            arm("a kit that does not match its pin is refused", ok)
        finally:
            KITS.clear(); KITS.update(saved)
    print(f"legacy selftest: {'0 failed' if not fails else str(len(fails)) + ' FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    import sys
    sys.exit(selftest() if "--selftest" in sys.argv else 2)
