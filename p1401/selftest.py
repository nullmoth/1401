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

    busy = tempfile.mkdtemp(prefix="1401-selftest-")
    open(os.path.join(busy, "precious.txt"), "w").write("do not wipe")
    try:
        engine._prepare_out(busy)
        refused = False
    except RuntimeError:
        refused = True
    arm("refuses to build into a non-empty folder it did not make (the engine wipes its output dir)",
        refused and os.path.exists(os.path.join(busy, "precious.txt")), "refused" if refused else "ACCEPTED")

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
