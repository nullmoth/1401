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
    out = {"startimage_aborted": False, "stop16": False, "secureboot_dmg": False, "mmio": [], "devirt_ran": False}
    seen = set()
    for t in texts:
        out["startimage_aborted"] |= "StartImage failed - Aborted" in t
        out["stop16"] |= bool(re.search(r"EB\.MM\.AKM|Couldn't allocate runtime area|STOP 0x16", t))
        out["secureboot_dmg"] |= "Cannot use Secure Boot with Any DmgLoading" in t
        out["devirt_ran"] |= "OCABC: MMIO devirt" in t
        for m in _MMIO.finditer(t):
            addr, pages, skip = int(m.group(1), 16), int(m.group(2), 16), m.group(3) == "1"
            if addr not in seen:
                seen.add(addr)
                out["mmio"].append((addr, pages, skip))
    return out


def apply(cfg, result, texts, change):
    """Mutates cfg (the loaded config.plist) from the boot logs. Returns the findings used."""
    f = findings(texts)
    cpu = ((result.hardware or {}).get("CPU") or {}).get("Manufacturer")
    booter = cfg.setdefault("Booter", {})
    quirks = booter.setdefault("Quirks", {})
    # AM5/AM4 boards that stop in boot.efi (STOP 0x16 "Couldn't allocate runtime area", or "StartImage failed -
    # Aborted", which 48 of 52 such logs show together) need different memory-map quirks per board: of 7 AMD sticks
    # with the policy default (DevirtualiseMmio and SetupVirtualMap off) 3 reached the kernel and 4 stopped there, and
    # support-chat users fixed theirs with both on plus a whitelist of the firmware's runtime MMIO region (Dortania KASLR
    # guide, "Using DevirtualiseMmio"). The log says which settings it ran with - OCABC "MMIO devirt" lines appear only
    # with DevirtualiseMmio on, "skip 1" marks a whitelisted region - so each failed boot moves one step:
    #   off, failed                          -> both on (the next log lists the board's MMIO regions)
    #   on, regions below 4 GiB not skipped  -> whitelist those (the large 64-bit regions stay devirtualised)
    #   on, all of them already whitelisted  -> back to the default, and say so: nothing left to try from the log.
    failed = f["stop16"] or f["startimage_aborted"]
    if cpu == "AMD" and failed:
        before = f"DevirtualiseMmio={quirks.get('DevirtualiseMmio')}, SetupVirtualMap={quirks.get('SetupVirtualMap')}"
        low = [(a, p, k) for a, p, k in f["mmio"] if a < 0x100000000]
        wl = [w for w in booter.get("MmioWhitelist", []) if isinstance(w, dict)]
        if not f["devirt_ran"]:
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
        else:
            quirks["DevirtualiseMmio"] = False; quirks["SetupVirtualMap"] = False
            for w in wl:
                w["Enabled"] = False
            booter["MmioWhitelist"] = wl
            change("bootlog-amd-memory-map-exhausted", before, "DevirtualiseMmio=False, SetupVirtualMap=False",
                   "every memory-map step the log allows has failed on this board; send the logs so it can be looked at")
    if f["secureboot_dmg"]:
        sec = cfg.setdefault("Misc", {}).setdefault("Security", {})
        if sec.get("SecureBootModel") != "Disabled":
            change("bootlog-secureboot-dmg", str(sec.get("SecureBootModel")), "Disabled",
                   "the stick's last boot stopped at 'Cannot use Secure Boot with Any DmgLoading'")
            sec["SecureBootModel"] = "Disabled"
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
        # Both panics saved so far (NM-EP57AX1N, NM-B8EZPY0E, 10-07, laptops): page fault in VoodooPS2Controller. Its
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
    # Dortania troubleshooting, "Stuck on [PCI configuration begin]": npci=0x2000, then npci=0x3000 (support chat 10-08:
    # the second one is what some boards need). The user's stopped line names it.
    if re.search(r"(?i)IOPCIConfigurator|PCI configuration (begin|PCI)", joined):
        out["args"].append("npci")
    if re.search(r"AppleIntelCPUPowerManagement", joined) and "panic" in joined.lower():
        out["cfglock"] = True   # Dortania: CFG-locked firmware panics in AppleIntelCPUPowerManagement -> AppleCpuPmCfgLock
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
    arm("step 3: failed with the low region already whitelisted -> back to the default, said out loud",
        not c["Booter"]["Quirks"]["DevirtualiseMmio"] and log == ["bootlog-amd-memory-map-exhausted"], log)
    c, log = run(intel, off_fail)
    arm("control: an Intel PC is not given the AMD steps", not c["Booter"]["Quirks"]["DevirtualiseMmio"] and not log)
    c, log = run(amd, "OCB: Saved mode 0/0/0 - Success\nAAPL: #[EB|LOG:EXITBS:START]\n")
    arm("negative control: a log with no failure changes nothing", not log and not c["Booter"]["Quirks"]["DevirtualiseMmio"])
    c, log = run(amd, "OC: Cannot use Secure Boot with Any DmgLoading!\n", {"Misc": {"Security": {"SecureBootModel": "Default"}}})
    arm("Secure Boot with DmgLoading Any: SecureBootModel Disabled", c["Misc"]["Security"]["SecureBootModel"] == "Disabled")
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
    f = after_handoff([], "the last line on the screen when it stopped")
    arm("negative control: a stopped line that names nothing changes nothing", f == {"disable": [], "args": [], "cfglock": False, "report": []}, f)
    print(f"bootfix: {sum(res)}/{len(res)}")
    return all(res)


if __name__ == "__main__":
    import sys  # noqa: PLC0415
    sys.exit(0 if selftest() else 1)
