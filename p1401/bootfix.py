"""Rebuild from a failed boot: the stick's own OpenCore log decides the settings the next build changes.

OpenCore writes opencore-*.txt on the stick at every boot (policy.py sets Misc > Debug > Target), and 1401 puts the
DEBUG build of OpenCore on the stick (engine._opencore_debug), which also prints the firmware's MMIO regions. When a
build is given those logs (`1401 build ... --boot-log <file>`), the rules below run after the policy pass. Each rule
names the log line it reads and the stick reports it came from; a log that matches nothing changes nothing.
"""
import re

MAX_LOG = 16 * 1024 * 1024

# OpenCore DEBUG, OcAfterBootCompatLib: one line per MMIO region it devirtualises (or skips, when whitelisted).
# Printed only when DevirtualiseMmio is on: "OCABC: MMIO devirt 0x<addr> (0x<pages> pages, 0x<attr>) skip <0|1>", skip 1 =
# that region is whitelisted. Format measured in 23 stick logs (2026-10-05..08).
_MMIO = re.compile(r"OCABC: MMIO devirt (?:0x)?([0-9A-Fa-f]{6,16}) \((?:0x)?([0-9A-Fa-f]+) pages, (?:0x)?[0-9A-Fa-f]+\) skip (\d)")


# One boot, from its own log: when boot.efi stamped it, which entry OpenCore started (T:4 = Apple recovery, which is the
# 1401 installer), whether it reached ExitBootServices, the two hand-off quirks it ran with (OCABC prints DEVMMIO and
# WRUNPROT, not the others), and whether the picker listed a macOS volume on an internal disk (T:2 on a non-USB path:
# the installer's second stage or an installed system exists).
_ABC = re.compile(r"OCABC: ALRBL \d+ .*?DEVMMIO (\d) .*?WRUNPROT (\d)")
_CHOSEN = re.compile(r"OCB: Should boot from \d+\. [^\n]*?\(T:(\d+)\|")
_MACOS_DISK = re.compile(r"OCB: Registering entry [^\n]*\(T:2\|[^\n]* - (?![^\n]*USB\()")


def _boot(t):
    if "EXITBS:START" not in t:
        return None
    abc = _ABC.search(t)
    chosen = _CHOSEN.findall(t)
    stamp = re.findall(r"#\[EB\|LOG:DT\] (\S+)", t)
    return {"stamp": stamp[-1] if stamp else "", "installer": bool(chosen) and chosen[-1] == "4",
            "devmmio": abc and abc.group(1) == "1", "wrunprot": abc and abc.group(2) == "1",
            "macos_disk": bool(_MACOS_DISK.search(t))}


def handoff_stuck(f, stopped_at=""):
    """The newest boot that froze after the hand-off, or None. Every OpenCore log ends at EXITBS:START, good boots too,
    so a log alone proves nothing: either the user's stopped-at line says EXITBS, or the stick shows the installer
    started at least twice and no macOS volume ever appeared on an internal disk (a working installer creates one
    before its first restart). 10-09: 29 photos in chat froze on EXITBS:START, but only 3 users typed it."""
    boots = sorted(f["boots"], key=lambda b: b["stamp"])
    if not boots:
        return {"devmmio": None, "wrunprot": None} if re.search(r"EXITBS", stopped_at or "") else None
    if re.search(r"EXITBS", stopped_at or ""):
        return boots[-1]
    tries = [b for b in boots if b["installer"]]
    if len(tries) >= 2 and not any(b["macos_disk"] for b in boots):
        return tries[-1]
    return None


def read_logs(paths):
    texts = []
    for p in paths or []:
        try:
            with open(p, "rb") as fh:
                texts.append(fh.read(MAX_LOG).decode("utf-8", "replace"))
        except OSError as error:
            print(f"(could not read boot log {p}: {type(error).__name__})")
    return texts


def findings(texts):
    """What the logs show, newest-boot-last order not assumed: any log showing a failure counts."""
    out = {"startimage_aborted": False, "stop16": False, "secureboot_dmg": False, "mmio": [], "devirt_ran": False, "boots": [],
           "vmap": None}
    seen = set()
    for t in texts:
        out["startimage_aborted"] |= "StartImage failed - Aborted" in t
        out["stop16"] |= bool(re.search(r"EB\.MM\.AKM|Couldn't allocate runtime area|STOP 0x16", t))
        out["secureboot_dmg"] |= "Cannot use Secure Boot with Any DmgLoading" in t
        out["devirt_ran"] |= "OCABC: MMIO devirt" in t
        out["no_slide"] = out.get("no_slide", False) or "No slide values are usable" in t
        vm = re.search(r"OCABC: .*\bVMAP ([01])\b", t)  # the quirk line: SetupVirtualMap as that boot ran it
        if vm:
            out["vmap"] = vm.group(1) == "1"
        boot = _boot(t)
        if boot:
            out["boots"].append(boot)
        for m in _MMIO.finditer(t):
            addr, pages, skip = int(m.group(1), 16), int(m.group(2), 16), m.group(3) == "1"
            if addr not in seen:
                seen.add(addr)
                out["mmio"].append((addr, pages, skip))
    return out


def apply(cfg, result, texts, change, stopped_at=""):
    """Mutates cfg (the loaded config.plist) from the boot logs. Returns the findings used."""
    f = findings(texts)
    cpu = ((result.hardware or {}).get("CPU") or {}).get("Manufacturer")
    booter = cfg.setdefault("Booter", {})
    quirks = booter.setdefault("Quirks", {})
    # AM5/AM4 boards that stop in boot.efi (STOP 0x16 "Couldn't allocate runtime area", or "StartImage failed -
    # Aborted", which 48 of 52 such logs show together) need different memory-map quirks per board: of 7 AMD sticks
    # with the policy default (DevirtualiseMmio and SetupVirtualMap off) 3 reached the kernel and 4 stopped there, and
    # users fixed theirs with both on plus a whitelist of the firmware's runtime MMIO region (Dortania KASLR
    # guide, "Using DevirtualiseMmio"). The log says which settings it ran with - OCABC "MMIO devirt" lines appear only
    # with DevirtualiseMmio on, "skip 1" marks a whitelisted region - so each failed boot moves one step:
    #   off, failed                          -> both on (the next log lists the board's MMIO regions)
    #   on, regions below 4 GiB not skipped  -> whitelist those (the large 64-bit regions stay devirtualised)
    #   on, all of them already whitelisted  -> back to the default, and say so: nothing left to try from the log.
    failed = f["stop16"] or f["startimage_aborted"]
    if cpu == "AMD" and failed:
        before = f"DevirtualiseMmio={quirks.get('DevirtualiseMmio')}, SetupVirtualMap={quirks.get('SetupVirtualMap')}"
        # OpenCore sizes the kernel's area as every runtime page plus 200 MB (OcAfterBootCompatLib/CustomSlide.c,
        # ESTIMATED_KERNEL_SIZE) and a whitelisted MMIO region stays runtime. One whitelisted window boots on most AM5
        # boards (11 stick logs: 0xE0000000 or 0xF7000000 alone), but an X870E board with both (382 MB) had no room left
        # below 512 MB: "No slide values are usable", then EB.MM.AKMr2 (4 stick logs 10-10). That log line sends the
        # next build back to no whitelist.
        low = [(a, p, k) for a, p, k in f["mmio"] if a < 0x100000000]
        wl = [w for w in booter.get("MmioWhitelist", []) if isinstance(w, dict)]
        if f["devirt_ran"] and f.get("no_slide") and any(k for _, _, k in f["mmio"]):
            # The whitelist itself is what left no room: the next build devirtualises every region again.
            quirks["DevirtualiseMmio"] = True; quirks["SetupVirtualMap"] = True
            for w in wl:
                w["Enabled"] = False
            booter["MmioWhitelist"] = wl
            change("bootlog-amd-no-slide-whitelist-off", before, "DevirtualiseMmio=True, SetupVirtualMap=True, no whitelist",
                   "OpenCore found no kernel slide: whitelisted MMIO counts as runtime memory and left no room below 512 MB")
        elif not f["devirt_ran"]:
            quirks["DevirtualiseMmio"] = True; quirks["SetupVirtualMap"] = True
            change("bootlog-amd-memory-map", before, "DevirtualiseMmio=True, SetupVirtualMap=True",
                   "the stick's last boot stopped in boot.efi with both off; the next log will list this board's MMIO regions")
        elif any(not k for _, _, k in low):
            have = {w.get("Address") for w in wl}
            for a, _, k in low:
                if a not in have:
                    wl.append({"Address": a, "Comment": f"Keep 0x{a:X} runtime MMIO (from this PC's boot log)", "Enabled": True})
            for w in wl:
                if w.get("Address") in {a for a, _, _ in low}:
                    w["Enabled"] = True
            booter["MmioWhitelist"] = wl
            quirks["DevirtualiseMmio"] = True; quirks["SetupVirtualMap"] = True
            change("bootlog-amd-mmio-whitelist", before, f"{len(low)} region(s) below 4 GiB whitelisted",
                   "the stick's last boot stopped in boot.efi with DevirtualiseMmio on and those regions devirtualised")
        elif f["vmap"] is not False:
            # 10-10: a Ryzen 9 9900X (X870E) ran every step above and still stopped at EB.MM.AKM ("No slide values are
            # usable"), while a Ryzen 5 7600 reached the desktop with DevirtualiseMmio on, SetupVirtualMap OFF and no
            # whitelist - a set this ladder never tried. It is the step before giving up.
            quirks["DevirtualiseMmio"] = True; quirks["SetupVirtualMap"] = False
            for w in wl:
                w["Enabled"] = False
            booter["MmioWhitelist"] = wl
            change("bootlog-amd-devirt-no-vmap", before, "DevirtualiseMmio=True, SetupVirtualMap=False, no whitelist",
                   "every whitelist step failed with SetupVirtualMap on; this set reached the desktop on another AM5 board")
        else:
            quirks["DevirtualiseMmio"] = False; quirks["SetupVirtualMap"] = False
            for w in wl:
                w["Enabled"] = False
            booter["MmioWhitelist"] = wl
            change("bootlog-amd-memory-map-exhausted", before, "DevirtualiseMmio=False, SetupVirtualMap=False",
                   "every memory-map step the log allows has failed on this board; send the logs so it can be looked at")
    # Stuck right after the hand-off (the screen freezes on EXITBS:START, the kernel never prints). Dortania's list for
    # this stop is the booter's memory-map handling, and the log of the frozen boot says which settings it ran with, so
    # each frozen boot moves one step and the next build never repeats a set that already froze:
    #   1. the no-MAT pairing: EnableWriteUnprotector on, RebuildAppleMemoryMap and SyncRuntimePermissions off, for
    #      firmware whose memory attributes table cannot be trusted. On AMD with DevirtualiseMmio and SetupVirtualMap on
    #      as well: measured on a Ryzen 5 5500 / B550 (10-09), it hung with the default, got past with the MMIO pair,
    #      then panicked (type 14) until the write-unprotector pair was on. All five change together.
    #   2. the frozen boot already ran with the write unprotector: DevirtualiseMmio flips from the policy's choice.
    #   3. both tried: the policy's settings stay, and the BIOS checklist is said out loud.
    stuck = handoff_stuck(f, stopped_at)
    if stuck is not None and cpu in ("AMD", "Intel"):
        nomat = {"RebuildAppleMemoryMap": False, "EnableWriteUnprotector": True, "SyncRuntimePermissions": False}
        if cpu == "AMD":
            nomat = {"DevirtualiseMmio": True, "SetupVirtualMap": True, **nomat}
        keys = list(dict.fromkeys(list(nomat) + ["DevirtualiseMmio"]))
        before = ", ".join(f"{k}={quirks.get(k)}" for k in keys)
        if not stuck["wrunprot"]:
            quirks.update(nomat)
            change("bootlog-handoff-nomat" if cpu == "Intel" else "bootlog-amd-exitbs", before,
                   ", ".join(f"{k}={v}" for k, v in nomat.items()),
                   f"the installer froze at EXITBS:START (the kernel never started) on an {cpu} PC")
        elif stuck["devmmio"] == nomat.get("DevirtualiseMmio", bool(quirks.get("DevirtualiseMmio"))):
            first = nomat.get("DevirtualiseMmio", bool(quirks.get("DevirtualiseMmio")))
            quirks.update(nomat)
            quirks["DevirtualiseMmio"] = not first
            change("bootlog-handoff-devirt", before, f"no-MAT set kept, DevirtualiseMmio={quirks['DevirtualiseMmio']}",
                   "it froze at EXITBS:START again with the write unprotector on")
        else:
            change("bootlog-note", "", "every hand-off setting the log allows has frozen on this PC. In the BIOS: Above 4G "
                   "Decoding on, CSM off, Secure Boot off, VT-d off (or keep it and leave DisableIoMapper on), then send the logs",
                   "it froze at EXITBS:START with each hand-off setting")
    if f["secureboot_dmg"]:
        sec = cfg.setdefault("Misc", {}).setdefault("Security", {})
        if sec.get("SecureBootModel") != "Disabled" and sec.get("DmgLoading") != "Signed":
            change("bootlog-secureboot-dmg", str(sec.get("DmgLoading")), "Signed",
                   "the stick's last boot stopped at 'Cannot use Secure Boot with Any DmgLoading'; "
                   "require an Apple-signed recovery image while preserving the configured Secure Boot model")
            sec["DmgLoading"] = "Signed"
    return f



# After OpenCore hands off (EXITBS:START), OpenCore writes nothing more. Two things still reach the next build:
# a kernel panic, which macOS saves on the stick as panic-*.txt (policy.py turns Misc > Debug > ApplePanic on), and the
# line the screen stopped on, which the user types or pastes when sending logs. These rules read both. A kext is only
# switched off when it is optional for starting macOS; anything else is reported, never guessed at.
OPTIONAL_KEXTS = {  # backtrace bundle id fragment -> kext file. All add features; none is needed to reach the desktop.
    "RestrictEvents": "RestrictEvents.kext", "VoodooI2C": "VoodooI2C.kext", "VoodooI2CHID": "VoodooI2CHID.kext",
    "itlwm": "itlwm.kext", "AirportItlwm": "AirportItlwm.kext", "BlueToolFixup": "BlueToolFixup.kext",
    "IntelBluetoothFirmware": "IntelBluetoothFirmware.kext", "IntelBTPatcher": "IntelBTPatcher.kext",
    "NVMeFix": "NVMeFix.kext", "CpuTopologyRebuild": "CpuTopologyRebuild.kext", "RadeonSensor": "RadeonSensor.kext",
    "SMCRadeonGPU": "SMCRadeonGPU.kext", "AMDRyzenCPUPowerManagement": "AMDRyzenCPUPowerManagement.kext",
    "SMCAMDProcessor": "SMCAMDProcessor.kext", "BrightnessKeys": "BrightnessKeys.kext", "ECEnabler": "ECEnabler.kext",
    "HibernationFixup": "HibernationFixup.kext", "FeatureUnlock": "FeatureUnlock.kext", "RealtekCardReader": "RealtekCardReader.kext",
    "Sinetek-rtsx": "Sinetek-rtsx.kext", "YogaSMC": "YogaSMC.kext", "AsusSMC": "AsusSMC.kext",
}
_BT = re.compile(r"Kernel Extensions in backtrace:(.*?)(?:\n\s*\n|Kernel Extensions in|BSD process name|$)", re.S)


def after_handoff(texts, stopped_at=""):
    """Findings from panic files and the user's stopped-at line: kexts to switch off, boot-args to add, and reports."""
    out = {"disable": [], "args": [], "cfglock": False, "report": []}
    joined = "\n".join(texts) + "\n" + (stopped_at or "")
    for m in _BT.finditer(joined):
        for frag, kext in OPTIONAL_KEXTS.items():
            if re.search(r"[.\s]" + re.escape(frag) + r"\b", m.group(1)) and kext not in out["disable"]:
                out["disable"].append(kext)
        # Both panics saved so far (10-07, laptops): page fault in VoodooPS2Controller. Its
        # own ps2rst=0 skips the controller reset some laptop firmware faults on; the panic file's "Boot args:" line
        # says whether the last start already had it, and then the kext goes off (a USB keyboard and mouse still work).
        if "PS2Controller" in m.group(1):
            ran = re.search(r"Boot args:([^\n]*)", joined)
            if ran and "ps2rst=0" in ran.group(1).split():
                out["disable"] += [k for k in ("VoodooPS2Controller.kext",) if k not in out["disable"]]
                out["report"].append("the laptop keyboard/trackpad driver crashed twice; it is off now - use a USB keyboard and mouse")
            elif "ps2rst" not in out["args"]:
                out["args"].append("ps2rst")
        if re.search(r"com\.nullmoth\.", m.group(1)):
            out["report"].append("the panic happened inside the NullMoth NVIDIA driver - send the logs; it is our bug")
    # Dortania troubleshooting, "Stuck on [PCI configuration begin]": npci=0x2000, then npci=0x3000 (user reports 10-08:
    # the second one is what some boards need). The user's stopped line names it.
    if re.search(r"(?i)IOPCIConfigurator|PCI configuration (begin|PCI)", joined):
        out["args"].append("npci")
    # Dortania: CFG-locked firmware panics in AppleIntelCPUPowerManagement -> AppleCpuPmCfgLock. Only a panic BACKTRACE
    # counts: every OpenCore log on AMD names the kext ("Skipping dummy AppleIntelCPUPowerManagement patch") and its
    # kernel patches have "panic" in their names, which set this on 87 AMD configs (10-10 scan of uploads).
    if any("AppleIntelCPUPowerManagement" in m.group(1) for m in _BT.finditer(joined)):
        out["cfglock"] = True
    if re.search(r"(?i)busy timeout.{0,24}NVRM", joined):
        out["report"].append("the NVIDIA card was still starting (small BAR1: up to 2 minutes). Enable Above 4G Decoding "
                             "and Resizable BAR in the BIOS and it starts in about a second; otherwise wait it out.")
    if re.search(r"(?i)GIOScreenLockState|IOConsoleUsers|Window ?Manager", joined):
        out["report"].append("macOS started; the stop is at the login screen's graphics - send the logs from the Mac "
                             "app (NullMoth) if it stays black")
    if re.search(r"(?i)still waiting for root device", joined):
        out["report"].append("macOS cannot see the disk it started from - map the USB ports (USBToolBox) or use another "
                             "USB port (a USB 2 port often works)")
    return out


def apply_after_handoff(cfg, texts, stopped_at, change):
    f = after_handoff(texts, stopped_at)
    kexts = cfg.get("Kernel", {}).get("Add", [])
    for name in f["disable"]:
        for k in kexts:
            if k.get("BundlePath", "").split("/")[-1] == name and k.get("Enabled"):
                k["Enabled"] = False
                change("bootlog-panic-kext-off", name, "Enabled=False", "the saved kernel panic names it in its backtrace; it is optional for starting macOS")
    nv = cfg.setdefault("NVRAM", {}).setdefault("Add", {}).setdefault("7C436110-AB2A-4BBB-A880-FE41995C9F82", {})
    args = (nv.get("boot-args") or "").split()
    if "ps2rst" in f["args"] and "ps2rst=0" not in args:
        args.append("ps2rst=0")
        nv["boot-args"] = " ".join(args)
        change("bootlog-ps2-panic", "", "ps2rst=0", "the saved panic is in the laptop keyboard driver (VoodooPS2Controller)")
    if "npci" in f["args"]:
        cur = next((a for a in args if a.startswith("npci=")), None)
        nxt = "npci=0x2000" if cur is None else ("npci=0x3000" if cur == "npci=0x2000" else None)
        if nxt:
            args = [a for a in args if not a.startswith("npci=")] + [nxt]
            nv["boot-args"] = " ".join(args)
            change("bootlog-pci-config", cur or "", nxt, "the screen stopped at PCI configuration (Dortania troubleshooting)")
        else:
            f["report"].append("PCI configuration still stops with npci=0x3000: check Above 4G Decoding in the BIOS and send the logs")
    if f["cfglock"]:
        q = cfg.setdefault("Kernel", {}).setdefault("Quirks", {})
        if q.get("AppleCpuPmCfgLock") is not True:
            q["AppleCpuPmCfgLock"] = True
            change("bootlog-cfg-lock", "AppleCpuPmCfgLock=False", "True", "the saved panic is AppleIntelCPUPowerManagement on CFG-locked firmware")
    return f

def selftest():
    from types import SimpleNamespace  # noqa: PLC0415
    res = []

    def arm(name, ok, detail=""):
        res.append(bool(ok)); print(("  ok   " if ok else "  FAIL ") + name + (f"   [{detail}]" if detail else ""))

    amd = SimpleNamespace(hardware={"CPU": {"Manufacturer": "AMD"}})
    intel = SimpleNamespace(hardware={"CPU": {"Manufacturer": "Intel"}})
    off_fail = "AAPL: #[EB.MM.AKM|!] Err(0xE)\nOCB: StartImage failed - Aborted\n"
    on_fail = ("OCABC: MMIO devirt start\n"
               "OCABC: MMIO devirt 0xF7000000 (0x1000 pages, 0x8000000000000001) skip 0\n"
               "OCABC: MMIO devirt 0x1000000000 (0x80000 pages, 0x8000000000000001) skip 0\n" + off_fail)
    wl_fail = on_fail.replace("skip 0\nOCABC: MMIO devirt 0x1000000000", "skip 1\nOCABC: MMIO devirt 0x1000000000")

    def run(result, text, cfg=None):
        cfg = cfg or {"Booter": {"Quirks": {"DevirtualiseMmio": False, "SetupVirtualMap": False}, "MmioWhitelist": []}}
        log = []
        apply(cfg, result, [text], lambda *a: log.append(a[0]))
        return cfg, log

    c, log = run(amd, off_fail)
    q = c["Booter"]["Quirks"]
    arm("step 1: AMD failed in boot.efi with both off -> both on", q["DevirtualiseMmio"] and q["SetupVirtualMap"], log)
    c, log = run(amd, on_fail)
    wl = c["Booter"]["MmioWhitelist"]
    arm("step 2: failed with devirt on -> the region below 4 GiB is whitelisted, the 64-bit one is not",
        [w["Address"] for w in wl] == [0xF7000000] and c["Booter"]["Quirks"]["DevirtualiseMmio"], [hex(w["Address"]) for w in wl])
    c, log = run(amd, wl_fail, {"Booter": {"Quirks": {"DevirtualiseMmio": True, "SetupVirtualMap": True},
                                           "MmioWhitelist": [{"Address": 0xF7000000, "Enabled": True}]}})
    arm("step 3: failed with the low region whitelisted and VirtualMap on -> devirt on, VirtualMap off, no whitelist",
        c["Booter"]["Quirks"]["DevirtualiseMmio"] and not c["Booter"]["Quirks"]["SetupVirtualMap"]
        and not any(w["Enabled"] for w in c["Booter"]["MmioWhitelist"]) and log == ["bootlog-amd-devirt-no-vmap"], log)
    c, log = run(amd, wl_fail + "\nOCABC: FEXITBS 0 PRMRG 0 CSLIDE 1 MSLIDE 0 PRSRV 0 RBMAP 1 VMAP 0 APPLOS 0\n",
                 {"Booter": {"Quirks": {"DevirtualiseMmio": True, "SetupVirtualMap": False},
                             "MmioWhitelist": [{"Address": 0xF7000000, "Enabled": False}]}})
    arm("step 4: that set failed too (log says VMAP 0) -> back to the default, said out loud",
        not c["Booter"]["Quirks"]["DevirtualiseMmio"] and log == ["bootlog-amd-memory-map-exhausted"], log)
    hero = ("OCABC: MMIO devirt 0xE0000000 (0x10000 pages, 0x800000000000100D) skip 1\n"
            "OCABC: MMIO devirt 0xF7000000 (0x7E00 pages, 0x800000000000100D) skip 1\n"
            "OCABC: MMIO devirt 0x890000000 (0x20200 pages, 0x800000000000100D) skip 0\n"
            "OCABC: No slide values are usable! Falling back to 0 with 0x0991F000 bytes!\n"
            "AAPL: #[EB.BST.FBS|RT!] 0 <- EB.MM.AKMr2 0x21286000 0x0\nAAPL: #[EB.MM.AKM|!] Err(0xE) <- EB.MM.MKP\n")
    c, log = run(amd, hero, {"Booter": {"Quirks": {"DevirtualiseMmio": True, "SetupVirtualMap": True},
                                        "MmioWhitelist": [{"Address": 0xE0000000, "Enabled": True}, {"Address": 0xF7000000, "Enabled": True}]}})
    arm("X870E log: no slide with regions whitelisted -> whitelist off, both quirks on",
        log == ["bootlog-amd-no-slide-whitelist-off"] and not any(w["Enabled"] for w in c["Booter"]["MmioWhitelist"])
        and c["Booter"]["Quirks"]["DevirtualiseMmio"] and c["Booter"]["Quirks"]["SetupVirtualMap"], log)
    c, log = run(intel, off_fail)
    arm("control: an Intel PC is not given the AMD steps", not c["Booter"]["Quirks"]["DevirtualiseMmio"] and not log)
    c, log = run(amd, "OCB: Saved mode 0/0/0 - Success\nAAPL: #[EB|LOG:EXITBS:START]\n")
    arm("negative control: a log with no failure changes nothing", not log and not c["Booter"]["Quirks"]["DevirtualiseMmio"])
    c, log = run(amd, "OC: Cannot use Secure Boot with Any DmgLoading!\n", {"Misc": {"Security": {"SecureBootModel": "Default"}}})
    arm("Secure Boot recovery requires Signed without disabling its model", c["Misc"]["Security"]["DmgLoading"] == "Signed" and c["Misc"]["Security"]["SecureBootModel"] == "Default")
    panic = ("panic(cpu 2 caller 0xffffff8001): Kernel trap at 0x..., type 14=page fault\n"
             "      Kernel Extensions in backtrace:\n         com.xxxx.driver.RestrictEvents(1.1.5)[...]@0x1->0x2\n\n"
             "BSD process name corresponding to current thread: kernel_task\n")
    c = {"Kernel": {"Add": [{"BundlePath": "Lilu.kext", "Enabled": True}, {"BundlePath": "RestrictEvents.kext", "Enabled": True}]},
         "NVRAM": {"Add": {}}}
    log = []
    apply_after_handoff(c, [panic], "", lambda *a: log.append(a[0]))
    arm("a panic whose backtrace names an optional kext switches only that kext off",
        [k["Enabled"] for k in c["Kernel"]["Add"]] == [True, False], log)
    c = {"Kernel": {"Add": [{"BundlePath": "Lilu.kext", "Enabled": True}]}, "NVRAM": {"Add": {}}}
    log = []
    apply_after_handoff(c, [panic.replace("RestrictEvents", "Lilu")], "", lambda *a: log.append(a[0]))
    arm("control: Lilu in a backtrace is never switched off (not optional)", c["Kernel"]["Add"][0]["Enabled"] and not log)
    c = {"NVRAM": {"Add": {}}}
    apply_after_handoff(c, [], "[IOPCIConfigurator::configure()] PCI configuration PCI0", lambda *a: None)
    a1 = c["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"]
    apply_after_handoff(c, [], "PCI configuration begin", lambda *a: None)
    a2 = c["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"]
    arm("stopped at PCI configuration: npci=0x2000, then npci=0x3000 on the next failure", (a1, a2) == ("npci=0x2000", "npci=0x3000"), (a1, a2))
    f = after_handoff([], "busy timeout 60s for 'NVRM'".replace("timeout 60s", "timeout[0], (60s):").replace(" for 'NVRM'", " 'NVRM' (1e,1)"))
    arm("the NVRM busy timeout is explained (BIOS fix), not treated as a hang", any("Resizable BAR" in r for r in f["report"]), f["report"])
    ps2 = ("Kernel Extensions in backtrace:\n         as.acidanthera.voodoo.driver.PS2Controller(2.3.8)[X]@0x1->0x2\n\n"
           "Boot args: -v keepsyms=1 nvfb=1\n")
    c = {"Kernel": {"Add": [{"BundlePath": "VoodooPS2Controller.kext", "Enabled": True}]}, "NVRAM": {"Add": {}}}
    apply_after_handoff(c, [ps2], "", lambda *a: None)
    step1 = (c["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"], c["Kernel"]["Add"][0]["Enabled"])
    apply_after_handoff(c, [ps2.replace("nvfb=1", "nvfb=1 ps2rst=0")], "", lambda *a: None)
    arm("VoodooPS2 panic: ps2rst=0 first, the kext off only after it panics again with ps2rst=0",
        step1 == ("ps2rst=0", True) and c["Kernel"]["Add"][0]["Enabled"] is False, (step1, c["Kernel"]["Add"][0]["Enabled"]))
    f = after_handoff([], "busy timeout 60s for 'NVRM'")
    arm("the user's own wording of the NVRM busy timeout is recognised", any("Resizable BAR" in r for r in f["report"]))
    q0 = {"DevirtualiseMmio": False, "SetupVirtualMap": False, "RebuildAppleMemoryMap": True,
          "EnableWriteUnprotector": False, "SyncRuntimePermissions": True}
    ca = {"Booter": {"Quirks": dict(q0)}}; la = []
    apply(ca, amd, [], lambda k, *x: la.append(k), "AAPL: #[EB|LOG:EXITBS:START] 2026-10-09T20:04:12")
    qa = ca["Booter"]["Quirks"]
    arm("AMD stuck at EXITBS:START gets the full no-MAT hand-off set (B550 / Ryzen 5 5500, 10-09)",
        la == ["bootlog-amd-exitbs"] and qa["DevirtualiseMmio"] and qa["SetupVirtualMap"] and qa["EnableWriteUnprotector"]
        and not qa["RebuildAppleMemoryMap"] and not qa["SyncRuntimePermissions"], la)
    def boot(stamp, devmmio, wrunprot, entry_t=4, macos_disk=False):
        return (f"OCABC: ALRBL 1 RTDFRG 1 DEVMMIO {int(devmmio)} NOSU 0 NOVRWR 0 NOSB 0 FBSIG 0 NOHBMAP 0 SMSLIDE 1 WRUNPROT {int(wrunprot)} CLRTS 0\n"
                + ("OCB: Registering entry Macintosh HD [Apple] (T:2|F:0|G:0|E:0|B:0) - PciRoot(0x0)/Pci(0x1D,0x0)/NVMe(0x1,AA)/HD(2,GPT,X)\n" if macos_disk else "")
                + f"OCB: Should boot from 1. 1401 (T:{entry_t}|F:1|G:0|E:1|DEF:0)\n"
                f"AAPL: #[EB|LOG:DT] {stamp}\nAAPL: #[EB|LOG:EXITBS:START] {stamp}\n")

    def ladder(result, logs, stopped=""):
        c = {"Booter": {"Quirks": dict(q0)}}; lg = []
        apply(c, result, logs, lambda k, *x: lg.append(k), stopped)
        return c["Booter"]["Quirks"], lg
    qi, li = ladder(intel, [boot("2026-10-09T10:00", 0, 0), boot("2026-10-09T10:20", 0, 0)])
    arm("Intel installer frozen twice at the hand-off, nothing typed: no-MAT pairing on the next build (step 1)",
        li == ["bootlog-handoff-nomat"] and qi["EnableWriteUnprotector"] and not qi["RebuildAppleMemoryMap"]
        and not qi["SyncRuntimePermissions"] and qi["DevirtualiseMmio"] == q0["DevirtualiseMmio"], li)
    qi, li = ladder(intel, [boot("2026-10-09T10:00", 0, 0), boot("2026-10-09T10:40", 0, 1)])
    arm("Intel frozen again WITH the write unprotector: DevirtualiseMmio flips, no-MAT kept (step 2)",
        li == ["bootlog-handoff-devirt"] and qi["DevirtualiseMmio"] is True and qi["EnableWriteUnprotector"], li)
    qi, li = ladder(intel, [boot("2026-10-09T10:40", 0, 1), boot("2026-10-09T11:00", 1, 1)])
    arm("Intel frozen with both steps tried: policy kept, BIOS checklist said (step 3)", li == ["bootlog-note"] and qi == q0, li)
    qa, la = ladder(amd, [boot("2026-10-09T10:00", 1, 1), boot("2026-10-09T10:30", 1, 1)])
    arm("AMD frozen with the measured five-quirk set: DevirtualiseMmio comes off next, the rest stays",
        la == ["bootlog-handoff-devirt"] and qa["DevirtualiseMmio"] is False and qa["EnableWriteUnprotector"], la)
    qi, li = ladder(intel, [boot("2026-10-09T10:00", 0, 0)])
    arm("control: ONE installer boot that reached the hand-off is not called frozen (good boots log the same)", not li and qi == q0, li)
    qi, li = ladder(intel, [boot("2026-10-09T10:00", 0, 0), boot("2026-10-09T10:20", 0, 0, macos_disk=True)])
    arm("control: once a macOS volume appears on an internal disk the installer worked - nothing changes", not li and qi == q0, li)
    qi, li = ladder(intel, [boot("2026-10-09T10:00", 0, 0, entry_t=2), boot("2026-10-09T10:20", 0, 0, entry_t=2)])
    arm("control: repeated starts of an INSTALLED macOS are not the installer freezing", not li and qi == q0, li)
    qi, li = ladder(intel, [boot("2026-10-09T10:00", 0, 0)], "the screen froze at EXITBS:START")
    arm("one boot plus the user's own 'EXITBS' line is enough", li == ["bootlog-handoff-nomat"], li)
    cn = {"Booter": {"Quirks": dict(q0)}}; ln = []
    apply(cn, amd, ["AAPL: #[EB|LOG:EXITBS:START]"], lambda k, *x: ln.append(k))
    arm("control: an OpenCore log that merely ends at EXITBS (every good start does) changes nothing", not ln, ln)
    f = after_handoff([], "the last line on the screen when it stopped")
    amdlog = ("OCAK: [OK] Skipping dummy AppleIntelCPUPowerManagement patch on 240600\n"
              "OC: Kernel patcher result 16 for kernel (algrey, XLNC | Remove version check and panic | 10.13+) - Success\n")
    intel_panic = ("panic(cpu 0 caller 0xffffff8000a1b2c3): \"Unrecoverable trap\"\n"
                   "      Kernel Extensions in backtrace:\n         com.apple.driver.AppleIntelCPUPowerManagement(222.0)[X]@0xffffff7f8\n\n")
    arm("a panic backtrace through AppleIntelCPUPowerManagement turns AppleCpuPmCfgLock on", after_handoff([intel_panic])["cfglock"])
    arm("control: an AMD OpenCore log naming the kext and a patch called 'panic' is not a CFG-lock panic",
        not after_handoff([amdlog])["cfglock"])
    arm("negative control: a stopped line that names nothing changes nothing", f == {"disable": [], "args": [], "cfglock": False, "report": []}, f)
    print(f"bootfix: {sum(res)}/{len(res)}")
    return all(res)


if __name__ == "__main__":
    import sys  # noqa: PLC0415
    sys.exit(0 if selftest() else 1)
