"""python3 -m p1401.selftest

Every check runs both ways: the good EFI has to pass and a deliberately broken copy has to fail. Works on copies
in a temp dir; out/ and the engine cache are only read.

Needs one EFI built by `tests/run_corpus.py build` first (x570-5800x-6600xt: Tahoe + AMD dGPU + Intel BT, which
hits every policy rule). If it's missing the suite exits non-zero rather than passing.
"""
import os
import plistlib
import shutil
import sys
import tempfile

from . import engine, policy, validate

REPO = engine.REPO
FIXTURE = os.path.join(REPO, "out", "corpus", "x570-5800x-6600xt")
FIXTURE_OLD = os.path.join(REPO, "out", "corpus", "optiplex-5050-micro")  # Ventura: nothing needs SIP lowered
results = []


def arm(name, cond, shown):
    results.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + name + f"  [{shown}]")


def _copy(src):
    d = tempfile.mkdtemp(prefix="1401-selftest-")
    shutil.copytree(os.path.join(src, "EFI"), os.path.join(d, "EFI"))
    return d


def _cfg(d):
    return os.path.join(d, "EFI", "OC", "config.plist")


def _edit(d, fn):
    p = _cfg(d)
    with open(p, "rb") as fh:
        c = plistlib.load(fh)
    fn(c)
    with open(p, "wb") as fh:
        plistlib.dump(c, fh)


def main():
    if not (os.path.isdir(FIXTURE) and os.path.isdir(FIXTURE_OLD)):
        print(f"can't run: fixtures missing ({FIXTURE}, {FIXTURE_OLD}). Run python3 tests/run_corpus.py build first")
        return 2

    # --- validator, good EFI
    d = _copy(FIXTURE)
    v = validate.validate(d)
    arm("the built Tahoe EFI passes ocvalidate and every invariant", v["ok"], f"issues={(v['ocvalidate'] or {}).get('issues')} inv={v['invariants']} err={v['error']}")

    # --- validator, broken copies (fresh copy each time)
    d = _copy(FIXTURE)
    _edit(d, lambda c: c["Misc"]["Security"].__setitem__("Vault", "NotAVaultMode"))
    ok, n, _ = validate.run_ocvalidate(_cfg(d))
    arm("ocvalidate catches an illegal Misc.Security.Vault value", not ok and n > 0, f"issues={n}")

    d = _copy(FIXTURE)
    shutil.rmtree(os.path.join(d, "EFI", "OC", "Kexts", "Lilu.kext"))
    inv = validate.invariants(d)
    arm("invariants catch a missing kext folder", any("Lilu.kext" in f for f in inv), inv[:2])

    d = _copy(FIXTURE)
    def lilu_last(c):
        add = c["Kernel"]["Add"]
        li = next(i for i, k in enumerate(add) if k["BundlePath"] == "Lilu.kext")
        add.append(add.pop(li))
    _edit(d, lilu_last)
    inv = validate.invariants(d)
    arm("invariants catch a Lilu plugin loading before Lilu", any("before Lilu" in f for f in inv), inv[:2])

    d = _copy(FIXTURE)
    os.remove(os.path.join(d, "EFI", "BOOT", "BOOTx64.efi"))
    inv = validate.invariants(d)
    arm("invariants catch a missing BOOTx64.efi", any("BOOTx64" in f for f in inv), inv[:1])

    d = _copy(FIXTURE)
    _edit(d, lambda c: c["PlatformInfo"]["Generic"].__setitem__("SystemSerialNumber", ""))
    inv = validate.invariants(d)
    arm("invariants catch an empty serial", any("SystemSerialNumber" in f for f in inv), inv[:1])

    # --- policy (re-applied to a copy whose WhateverGreen + pikera we restore to the engine's original output)
    d = _copy(FIXTURE)
    def engine_original(c):
        for k in c["Kernel"]["Add"]:
            if k["BundlePath"] == "WhateverGreen.kext":
                k["Enabled"] = True
        c["Kernel"]["Patch"] = [p for p in c["Kernel"]["Patch"] if "1401" not in (p.get("Comment") or "")]
        nv = c["NVRAM"]["Add"][policy.BOOT]
        nv["boot-args"] = "-v debug=0x100 keepsyms=1 agdpmod=pikera -radcodec"
        nv["csr-active-config"] = bytes.fromhex("030A0000")
    _edit(d, engine_original)
    fake = engine.BuildResult(ok=True, out_dir=d, macos_version="25.99.99",
                              hardware={"GPU": {"AMD Radeon RX 6600 XT": {"Manufacturer": "AMD", "Device Type": "Discrete GPU"}}},
                              decisions=[engine.Decision("Select audio kext for your system:", "2", "")])
    ch = policy.apply(_cfg(d), fake, engine.Policy())
    with open(_cfg(d), "rb") as fh:
        c = plistlib.load(fh)
    nv = c["NVRAM"]["Add"][policy.BOOT]
    weg = [k["Enabled"] for k in c["Kernel"]["Add"] if k["BundlePath"] == "WhateverGreen.kext"]
    arm("Tahoe + AMD dGPU, no iGPU: WhateverGreen off, pikera moved to a kernel patch",
        weg == [False] and "agdpmod=pikera" not in nv["boot-args"] and any("1401" in (p.get("Comment") or "") for p in c["Kernel"]["Patch"]),
        f"weg={weg} args={nv['boot-args']}")
    arm("WhateverGreen's boot args are removed with it (-radcodec)", "-radcodec" not in nv["boot-args"], nv["boot-args"])
    arm("VoodooHDA on Tahoe lowers SIP to 0x03 and no further", nv["csr-active-config"] == bytes.fromhex("03000000"), nv["csr-active-config"].hex())
    arm("the policy pass keeps the EFI valid (ocvalidate accepts the added kernel patch)", validate.validate(d)["ok"], [x["rule"] for x in ch])

    d = _copy(FIXTURE)
    _edit(d, engine_original)
    fake.hardware["GPU"]["Intel UHD 630"] = {"Manufacturer": "Intel", "Device Type": "Integrated GPU"}
    policy.apply(_cfg(d), fake, engine.Policy())
    with open(_cfg(d), "rb") as fh:
        c = plistlib.load(fh)
    weg = [k["Enabled"] for k in c["Kernel"]["Add"] if k["BundlePath"] == "WhateverGreen.kext"]
    arm("same machine with an Intel iGPU keeps WhateverGreen (the iGPU needs it)", weg == [True], f"weg={weg}")

    d = _copy(FIXTURE_OLD)
    _edit(d, lambda c: c["NVRAM"]["Add"][policy.BOOT].__setitem__("csr-active-config", bytes.fromhex("030A0000")))
    old = engine.BuildResult(ok=True, out_dir=d, macos_version="22.99.99", hardware={"GPU": {}}, decisions=[])
    policy.apply(_cfg(d), old, engine.Policy())
    with open(_cfg(d), "rb") as fh:
        csr = plistlib.load(fh)["NVRAM"]["Add"][policy.BOOT]["csr-active-config"]
    arm("machine that needs nothing gets SIP fully on (engine's 0x0A03 undone)", csr == bytes(4), csr.hex())

    d = _copy(FIXTURE)
    _edit(d, lambda c: c["ACPI"]["Add"].insert(1, dict(c["ACPI"]["Add"][0])))
    ch = policy.apply(_cfg(d), old, engine.Policy())
    with open(_cfg(d), "rb") as fh:
        paths = [a["Path"] for a in plistlib.load(fh)["ACPI"]["Add"]]
    for chip, want in (("AMD", False), ("B650", False), ("A320", True)):
        d = _copy(FIXTURE)
        _edit(d, lambda c: c["Booter"]["Quirks"].__setitem__("SetupVirtualMap", True))
        amd = engine.BuildResult(ok=True, out_dir=d, macos_version="24.99.99", decisions=[],
                                 hardware={"GPU": {}, "CPU": {"Manufacturer": "AMD"}, "Motherboard": {"Chipset": chip}})
        policy.apply(_cfg(d), amd, engine.Policy())
        with open(_cfg(d), "rb") as fh:
            svm = plistlib.load(fh)["Booter"]["Quirks"]["SetupVirtualMap"]
        arm(f"Ryzen board reported as {chip!r}: SetupVirtualMap {want} (STOP 0x16 sticks, NM-5WSVHVK1)", svm is want, svm)
    for chip, want in (("B550", False), ("AMD", False), ("TRX40", True)):
        d = _copy(FIXTURE)
        _edit(d, lambda c: c["Booter"]["Quirks"].__setitem__("DevirtualiseMmio", True))
        amd = engine.BuildResult(ok=True, out_dir=d, macos_version="24.99.99", decisions=[],
                                 hardware={"GPU": {}, "CPU": {"Manufacturer": "AMD"}, "Motherboard": {"Chipset": chip}})
        policy.apply(_cfg(d), amd, engine.Policy())
        with open(_cfg(d), "rb") as fh:
            dm = plistlib.load(fh)["Booter"]["Quirks"]["DevirtualiseMmio"]
        arm(f"Ryzen board reported as {chip!r}: DevirtualiseMmio {want} (NM-Z1VR8TR9)", dm is want, dm)
    d = _copy(FIXTURE)
    _edit(d, lambda c: (c["Booter"]["Quirks"].__setitem__("DevirtualiseMmio", True),
                        c["Booter"].__setitem__("MmioWhitelist", [{"Address": 4275159040, "Comment": "1401 selftest MMIO",
                                                                  "Enabled": True}])))
    amd = engine.BuildResult(ok=True, out_dir=d, macos_version="24.99.99", decisions=[],
                             hardware={"GPU": {}, "CPU": {"Manufacturer": "AMD"}, "Motherboard": {"Chipset": "B650"}})
    policy.apply(_cfg(d), amd, engine.Policy())
    with open(_cfg(d), "rb") as fh:
        bt = plistlib.load(fh)["Booter"]
    v = validate.validate(d)
    arm("B650 with a MmioWhitelist entry: DevirtualiseMmio and the entry go off together, EFI validates (NM-KYT0Q2KS)",
        bt["Quirks"]["DevirtualiseMmio"] is False and not any(w.get("Enabled") for w in bt["MmioWhitelist"]) and v["ok"],
        (bt["Quirks"]["DevirtualiseMmio"], [w.get("Enabled") for w in bt["MmioWhitelist"]], v.get("issues")))

    arm("a table listed twice in ACPI > Add is kept once and the EFI validates (NM-MH8TV0NW)",
        len(paths) == len(set(paths)) and "dedupe-add" in [x["rule"] for x in ch] and validate.validate(d)["ok"], paths[:3])

    d = _copy(FIXTURE)
    _edit(d, lambda c: c["Kernel"]["Patch"].append({"Arch": "x86_64", "Base": "", "Comment": "1401 selftest mask", "Count": 1,
          "Enabled": True, "Find": bytes.fromhex("b800000000"), "Identifier": "kernel", "Limit": 0, "Mask": b"",
          "MaxKernel": "", "MinKernel": "", "Replace": bytes.fromhex("b8ffffffff"), "ReplaceMask": bytes.fromhex("ff0f000000"),
          "Skip": 0}))
    ch = policy.apply(_cfg(d), old, engine.Policy())
    with open(_cfg(d), "rb") as fh:
        rp = [p["Replace"] for p in plistlib.load(fh)["Kernel"]["Patch"] if p.get("Comment") == "1401 selftest mask"]
    arm("Replace bits outside ReplaceMask are cleared and the EFI validates (NM-MMXGZ2XV)",
        rp == [bytes.fromhex("b80f000000")] and validate.validate(d)["ok"], (rp[0].hex() if rp else None, [x["rule"] for x in ch]))

    engine._load_engine()
    from Scripts import resource_fetcher as rf  # noqa: PLC0415
    tries = []

    class Stall(rf.ResourceFetcher):
        def _make_request(self, url, timeout=30):
            return object()

        def _download_with_progress(self, response, fh):
            tries.append(1)
            if len(tries) < 3:
                raise TimeoutError("The read operation timed out")
            fh.write(b"ok")
    real_sleep, engine.time.sleep = engine.time.sleep, lambda s: None
    try:
        dest = os.path.join(tempfile.mkdtemp(prefix="1401-selftest-"), "f")
        got = Stall().download_and_save_file("https://example.invalid/f", dest)
    except TimeoutError as e:
        got = e
    finally:
        engine.time.sleep = real_sleep
    arm("a download that stalls mid-read twice is retried and lands (NM-DTC05X6Y)", got is True and len(tries) == 3, (got, len(tries)))

    class Blocked(rf.ResourceFetcher):
        def _make_request(self, url, timeout=30):
            return None
    try:
        Blocked().fetch_and_parse_content("https://raw.githubusercontent.com/dortania/build-repo/builds/latest.json", "json")
        blocked = "returned"
    except RuntimeError as e:
        blocked = str(e)
    arm("a fetch GitHub never answers says VPN/proxy, not 'NoneType is not iterable' (NM-CG2NRMES)",
        "raw.githubusercontent.com" in blocked and "VPN" in blocked, blocked[:70])

    from . import validate as validate_mod  # noqa: PLC0415
    real_cache, validate_mod.CACHE = validate_mod.CACHE, tempfile.mkdtemp(prefix="1401-selftest-")
    try:
        tries.clear(); tries.extend([1, 1])
        dest = os.path.join(tempfile.mkdtemp(prefix="1401-selftest-"), "OpenCorePkg.zip")
        Stall().download_and_save_file("https://example.invalid/x/OpenCore-1.0.9-RELEASE.zip", dest, None)
        unkept = os.path.exists(os.path.join(validate_mod.CACHE, "OpenCore-1.0.9-RELEASE.zip"))
        tries.clear(); tries.extend([1, 1])
        import hashlib  # noqa: PLC0415
        Stall().download_and_save_file("https://example.invalid/x/OpenCore-1.0.9-RELEASE.zip", dest, hashlib.sha256(b"ok").hexdigest())
        kept = os.path.exists(os.path.join(validate_mod.CACHE, "OpenCore-1.0.9-RELEASE.zip"))
    finally:
        validate_mod.CACHE = real_cache
    arm("an unverified OpenCore zip is NOT handed to the validator", not unkept, unkept)
    arm("the engine's checked OpenCore zip is kept for the validator (no second download, NM-KHVZNES3)", kept, kept)

    vmd = engine.stop_message(["5. Storage Controllers:", "Intel VMD controllers are not supported in macOS.\nPlease disable Intel VMD"])
    arm("a VMD stop leads with 'Turn off Intel VMD' (NM-CHW0YW6F)", vmd.startswith("Turn off Intel VMD"), vmd[:40])
    plain = engine.stop_message(["something else"])
    arm("a stop with no known fix keeps the engine's words first", plain.startswith("OpenCore-Simplify stopped"), plain[:30])

    o = type("O", (), {})(); o.o = type("G", (), {})(); o.k = type("K", (), {})()
    engine._use_ock_cache(o)
    arm("the engine's download cache is OCK_CACHE for both gatherer and kext picker",
        o.o.ock_files_dir == o.k.ock_files_dir == engine.OCK_CACHE and o.o.download_history_file.startswith(engine.OCK_CACHE), engine.OCK_CACHE)

    # --- engine guards
    class FakeUtils:
        def request_input(self, prompt=""):
            return ""
    fu = type("M", (), {"Utils": FakeUtils})
    h = engine.Headless(fu, engine.Policy())
    with h:
        try:
            FakeUtils().request_input("Format drive C:? (yes/no): ")
            fired = False
        except engine.UnknownPrompt:
            fired = True
    arm("unknown prompt stops the build instead of guessing", fired, "UnknownPrompt" if fired else "answered!")

    h = engine.Headless(fu, engine.Policy())
    with h:
        try:
            for _ in range(3):
                FakeUtils().request_input("Select audio kext for your system: ")
            looped = False
        except engine.EngineLoop:
            looped = True
    arm("same prompt 3x in a row stops the build", looped, "EngineLoop" if looped else "spun")

    menu_oclp = ("Available macOS versions:\n   23. macOS Sonoma 14 (Requires OpenCore Legacy Patcher)\n"
                 "   24. macOS Sequoia 15 (Requires OpenCore Legacy Patcher)\n   25. macOS Tahoe 26 (Requires OpenCore Legacy Patcher)\nQ. Quit")
    menu_ok = "Available macOS versions:\n   22. macOS Ventura 13\n   23. macOS Sonoma 14\nQ. Quit"
    q = "Please enter the macOS version you want to use (default: macOS Ventura 13):"
    a1 = engine._macos_answer(q, menu_oclp, engine.Policy())
    a2 = engine._macos_answer(q, menu_ok, engine.Policy())
    a3 = engine._macos_answer(q, menu_oclp.replace("   24. macOS Sequoia 15 (Requires OpenCore Legacy Patcher)\n", ""), engine.Policy())
    from . import report as report_mod
    rb, nb = report_mod.normalize({"Input": {}, "GPU": {"Microsoft Basic Display Adapter": {"Manufacturer": "Unknown", "Device ID": "10DE-1F08"}}})
    arm("a driverless card (Basic Display Adapter) gets its maker from the PCI ID (NM-S9BPDPZQ)",
        rb["GPU"]["Microsoft Basic Display Adapter"]["Manufacturer"] == "NVIDIA" and nb, nb)
    try:
        report_mod.normalize({"Input": {}, "GPU": {"Microsoft Basic Display Adapter": {"Manufacturer": "Unknown"}}})
        lone = "accepted"
    except RuntimeError as e:
        lone = str(e)
    arm("a lone driverless card with no PCI ID stops with 'install your graphics driver'", "driver" in lone and lone != "accepted", lone[:60])
    arm("a default missing from the menu answers Sequoia 24 (Turing + Broadcom, NM-036E35M9)", a1 == "24", a1)
    arm("a default that IS on the menu keeps the engine's default", a2 == "", repr(a2))
    arm("no Sequoia on the menu takes the newest listed", a3 == "25", a3)
    a4 = engine._macos_answer("Please enter the macOS version you want to use (default: macOS Sonoma 14):",
                              "Available macOS versions:\n\n   24. macOS Sequoia 15\n\nNote:\nQ. Quit", engine.Policy())
    arm("a Sonoma default with only Sequoia listed answers 24 (NM-3183CSDD)", a4 == "24", a4)
    nores = engine.build(os.path.join(tempfile.mkdtemp(prefix="1401-selftest-"), "Report.json"), tempfile.mkdtemp(prefix="1401-selftest-"),
                         tempfile.mkdtemp(prefix="1401-selftest-"), download=False)
    rf_ = report_mod.normalize({"Input": {}, "GPU": {}, "BIOS": {"Firmware Type": "Linux Rice loaded!\nUEFI"}})
    arm("a PowerShell banner in the firmware type is dropped, UEFI kept (NM-WJBMSV8B)",
        rf_[0]["BIOS"]["Firmware Type"] == "UEFI" and rf_[1], rf_[0]["BIOS"]["Firmware Type"])
    rl_ = report_mod.normalize({"Input": {}, "GPU": {}, "BIOS": {"Firmware Type": "Legacy"}})
    arm("a Legacy firmware type reads as BIOS", rl_[0]["BIOS"]["Firmware Type"] == "BIOS", rl_[0]["BIOS"]["Firmware Type"])
    arm("Build with no Report.json says 'Run Check this PC first' (NM-EMCW2SYV)", "Check this PC first" in (nores.error or ""), (nores.error or "")[:60])

    busy = tempfile.mkdtemp(prefix="1401-selftest-")
    open(os.path.join(busy, "precious.txt"), "w").write("do not wipe")
    try:
        engine._prepare_out(busy)
        refused = False
    except RuntimeError:
        refused = True
    arm("refuses to build into a non-empty folder it did not make (the engine wipes its output dir)",
        refused and os.path.exists(os.path.join(busy, "precious.txt")), "refused" if refused else "ACCEPTED")

    # NM-3YJDQC1P: a file of our previous build vanishes while the wipe runs (antivirus). The first unlink removes it
    # and still reports failure, as Windows does; the wipe must finish instead of raising FileNotFoundError.
    prev = tempfile.mkdtemp(prefix="1401-selftest-")
    open(os.path.join(prev, engine.MARKER), "w").write("1401")
    os.makedirs(os.path.join(prev, "EFI", "OC", "Drivers"))
    gone = os.path.join(prev, "EFI", "OC", "Drivers", "UefiPxeBcDxe.efi")
    open(gone, "wb").write(b"x")
    real_unlink = os.unlink
    def flaky_unlink(path, *a, **k):
        if os.fspath(path).endswith("UefiPxeBcDxe.efi") and os.path.exists(path):
            real_unlink(path, *a, **k)
            raise PermissionError(13, "in use", os.fspath(path))
        return real_unlink(path, *a, **k)
    os.unlink = flaky_unlink
    fd_rmtree = getattr(shutil, "_rmtree_impl", None)
    if fd_rmtree is not None and hasattr(shutil, "_rmtree_unsafe"):
        shutil._rmtree_impl = shutil._rmtree_unsafe   # Windows' rmtree: unlink by full path, as on the user's PC
    try:
        engine._prepare_out(prev)
        wiped = (os.path.isdir(prev) and not os.listdir(prev), "")
    except Exception as e:
        wiped = (False, f"{type(e).__name__}: {e}")
    finally:
        os.unlink = real_unlink
        if fd_rmtree is not None:
            shutil._rmtree_impl = fd_rmtree
    arm("a previous build whose file vanishes mid-wipe is still wiped (NM-3YJDQC1P)", wiped[0], wiped[1] or "empty")

    # --- device choice + report normalizer
    ctx = "1. Network Controller\n   Device ID: 14E4-43A0\n2. Intel(R) Wi-Fi 6 AX200 160MHz\n   Device ID: 8086-2723"
    pol = engine.Policy(prefer={"WiFi": "Intel(R) Wi-Fi 6 AX200 160MHz"})
    got = engine._choose_device("Select a WiFi device (1-2): ", ctx, pol)
    arm("Wi-Fi pick is matched by name in the engine's list, not position", got == "2", got)
    try:
        engine._choose_device("Select a WiFi device (1-2): ", ctx.replace("AX200", "AX210"), pol)
        fired = False
    except engine.UnknownPrompt:
        fired = True
    arm("a pick the engine didn't list stops the build", fired, "UnknownPrompt" if fired else "answered!")
    hh = engine.Headless(fu, engine.Policy())
    still = engine._oclp_still_needed({"Network": {"Intel AX200": {"Device ID": "8086-2723"}}, "BIOS": {"Firmware Type": "UEFI"}}, True, hh)
    arm("OCLP flag clears when every OCLP device is disabled (no AMFIPass for a dead card)", still is False, still)
    still = engine._oclp_still_needed({"GPU": {"GTX 970": {"OCLP Compatibility": ("25.99.99", "23.0.0")}}}, True, hh)
    arm("OCLP flag stays when an enabled device still needs it", still is True, still)
    from . import report  # noqa: PLC0415
    r, notes = report.normalize({"Input": {}, "Sound": {"Focusrite USB Audio": {"Bus Type": "FOCUSRITEUSB"},
                                           "Realtek(R) Audio": {"Bus Type": "HDAUDIO"}}})
    arm("a USB audio interface without a Device ID is dropped (class-compliant; never in the EFI)",
        "Focusrite USB Audio" not in r["Sound"] and len(notes) == 1, notes[:1])
    r2, n2 = report.normalize({"Sound": {}})
    arm("a report with no Input section gets an empty one (NM-NX36531A was rejected for it), and says so",
        r2.get("Input") == {} and any(n.startswith("Input:") for n in n2), n2)
    arm("HDA codec without a Device ID is kept, so the engine's validator still rejects it",
        "Realtek(R) Audio" in r["Sound"], list(r["Sound"]))

    print(f"\n{sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
