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
    print(f"bootfix: {sum(res)}/{len(res)}")
    return all(res)


if __name__ == "__main__":
    import sys  # noqa: PLC0415
    sys.exit(0 if selftest() else 1)
