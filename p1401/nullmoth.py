"""NullMoth NVIDIA driver support: lets 1401 build for a PC whose graphics card is a supported Turing-or-later NVIDIA card.

The engine underneath marks every NVIDIA card after Kepler unsupported, disables it, and refuses a machine that has no
other GPU ("You cannot install macOS without a supported GPU"). The NullMoth driver runs these cards on macOS 15, so:

1. `mark()` runs right after the engine's GPU check. A card in NVIDIA's own supported-GPU table for the firmware the
   driver ships (nvidia_gsp_ids.json, from open-gpu-kernel-modules 610.57.04) gets Compatibility = macOS 15 only.
   The engine's version picker then suggests Sequoia by itself, and the card is kept instead of disabled.
2. `apply()` runs in the policy pass: the boot-args and SIP/AMFI settings the driver was tested with.
3. The driver itself is installed after macOS by the 1401 Mac companion, from the package `stage()` puts on the stick.

Every number here is the tested configuration, not a guessed minimum. A smaller SIP value is untested.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SEQUOIA = ("24.99.99", "24.0.0")  # (max, min) Darwin: the only macOS the driver is built for
# The working machine's OpenCore config before it was changed for dtrace (2026-): kexts, FS, NVRAM, recovery, root.
SIP_DRIVER = bytes.fromhex("430A0000")
# nvfb/nvaccel switch the framebuffer and accelerator on; nvfbheads=4 = the card's display heads; the smooth boot
# takeover is off on the tested machine. The two AMFI args let WindowServer load a GPU bundle Apple did not sign.
BOOT_ARGS = ("nvfb=1", "nvaccel=1", "nvfbheads=4", "-nvkmsnosmooth", "amfi_get_out_of_my_way=0x1", "amfi=0x80")
# Package published with the driver; the stick carries it so the Mac companion can install it offline.
PACKAGE = {"name": "nullmoth-nvidia-1.0.4.tar.gz",
           "url": "https://github.com/nullmoth/nvidia-macos-driver/releases/download/v1.0.7/nullmoth-nvidia-1.0.4.tar.gz",
           "sha256": "c070ca9180122b35588064be443d7b2bd74a4b8c50fcf5eafd177867b19e37e3"}

with open(os.path.join(HERE, "nvidia_gsp_ids.json")) as _fh:
    TABLE = json.load(_fh)


def _pid(gpu):
    did = (gpu.get("Device ID") or "").upper()
    return did[5:] if did.startswith("10DE-") else ""


def supported(gpu):
    """A discrete NVIDIA card NVIDIA's firmware table lists. Laptops' switchable graphics are not handled."""
    return gpu.get("Manufacturer") == "NVIDIA" and gpu.get("Device Type") == "Discrete GPU" and _pid(gpu) in TABLE["ids"]


def cards(report):
    return {n: g for n, g in (report.get("GPU") or {}).items() if supported(g)}


def mark(report):
    """Gives each supported card macOS 15 compatibility. Returns the names marked. A card that drives a laptop's
    internal panel through another GPU is left alone (the engine rule for that case stands)."""
    monitors = list((report.get("Monitor") or {}).values())
    internal = [m for m in monitors if m.get("Connector Type") == "Internal"]
    hit = []
    for n, g in cards(report).items():
        # A laptop whose built-in panel runs on the integrated GPU can still use the NVIDIA card for a monitor plugged into
        # a port wired to it (10-07, NM-K8HCTWCW: RTX 5060 Laptop + Radeon 610M panel + a DP monitor). Without such a
        # monitor the card has nothing to show a picture on, and the engine rule stands.
        external_on_card = any(m.get("Connector Type") != "Internal" and m.get("Connected GPU") == n for m in monitors)
        if any(m.get("Connected GPU", n) != n for m in internal) and not external_on_card:
            continue
        g["Compatibility"] = SEQUOIA
        g.pop("OCLP Compatibility", None)
        g["Codename"] = g.get("Codename") if g.get("Codename") not in (None, "", "Unknown") else "NullMoth driver"
        hit.append(n)
    return hit


MUX_HELP = (
    "This laptop's built-in screen is connected to its integrated graphics ({igpu}), which macOS cannot drive, so the "
    "{card} has no screen to show macOS on.\n\n"
    "Most gaming laptops can connect the built-in screen straight to the NVIDIA card (a MUX switch):\n"
    "  - ASUS: Armoury Crate > GPU Mode > Ultimate (or dGPU / Discrete)\n"
    "  - Lenovo Legion: Lenovo Vantage > Hybrid Mode off, or BIOS > Graphic Device > Discrete Graphics\n"
    "  - MSI: MSI Center > MUX switch / Discrete Graphics Mode\n"
    "  - Others: look for 'MUX', 'Discrete GPU' or 'dGPU only' in the vendor app or the BIOS\n"
    "Switch it, restart Windows, then run Check this PC and Build again.\n"
    "An external monitor plugged into a port wired to the NVIDIA card (often HDMI or the dGPU-side USB-C/DP) also works.")


def mux_help(report):
    """When a supported card was skipped only because the built-in panel runs on another GPU: the advice to give.
    (10-07: five uploaded logs in one night were RTX 4060/5060/5070 Ti laptops in Optimus mode.)"""
    mons = list((report.get("Monitor") or {}).values())
    for n, g in cards(report).items():
        panel = [m for m in mons if m.get("Connector Type") == "Internal" and m.get("Connected GPU", n) != n]
        if panel:
            return MUX_HELP.format(igpu=panel[0].get("Connected GPU") or "integrated GPU", card=n)
    return None


def tested(report):
    return [n for n, g in cards(report).items() if _pid(g) in TABLE["tested"]]


def apply(cfg, result, change):
    """Policy-pass rule. cfg = the loaded config.plist dict; change(rule, before, after, why) records it.
    Returns True when the driver settings were applied (the SIP rule then must not lower them again)."""
    gpus = (result.hardware or {}).get("GPU", {})
    live = [n for n, g in gpus.items() if supported(g) and g.get("Compatibility") == SEQUOIA and n not in result.disabled_devices]
    if not live:
        return False
    nv = cfg["NVRAM"]["Add"].setdefault("7C436110-AB2A-4BBB-A880-FE41995C9F82", {})
    args = (nv.get("boot-args") or "").split()
    add = [a for a in BOOT_ARGS if a not in args]
    if add:
        nv["boot-args"] = " ".join(args + add)
        change("nullmoth-boot-args", "", " ".join(add), f"NullMoth driver for {', '.join(live)}: framebuffer, accelerator, AMFI")
    if nv.get("csr-active-config") != SIP_DRIVER:
        change("nullmoth-sip", (nv.get("csr-active-config") or b"").hex(), SIP_DRIVER.hex(),
               "the SIP value the NullMoth driver was tested with (its kexts are not Apple-signed)")
        nv["csr-active-config"] = SIP_DRIVER
    delete = cfg["NVRAM"].setdefault("Delete", {}).setdefault("7C436110-AB2A-4BBB-A880-FE41995C9F82", [])
    # not boot-args (): deleting it replaced the flags of a machine already running macOS. SIP is safe to reassert.
    for k in ("csr-active-config",):
        if k not in delete:
            delete.append(k)
    return True


def stage(usb_root, cache_dir, fetch=None):
    """Puts the driver package on the stick under NullMoth/. Verifies SHA-256 before and after copying; a mismatch
    raises and leaves nothing behind. fetch(url, path) downloads; None = the package must already be in cache_dir."""
    import hashlib  # noqa: PLC0415
    import shutil  # noqa: PLC0415

    def sha(p):
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for b in iter(lambda: fh.read(1 << 20), b""):
                h.update(b)
        return h.hexdigest()

    src = os.path.join(cache_dir, PACKAGE["name"])
    if not os.path.exists(src) or sha(src) != PACKAGE["sha256"]:
        if fetch is None:
            raise RuntimeError(f"driver package missing or wrong in {cache_dir}")
        fetch(PACKAGE["url"], src + ".part")
        if sha(src + ".part") != PACKAGE["sha256"]:
            os.remove(src + ".part")
            raise RuntimeError("driver package download does not match its SHA-256 - not written to the stick")
        os.replace(src + ".part", src)
    d = os.path.join(usb_root, "NullMoth")
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, PACKAGE["name"])
    shutil.copyfile(src, dst + ".part")
    if sha(dst + ".part") != PACKAGE["sha256"]:
        os.remove(dst + ".part")
        raise RuntimeError("driver package changed while copying to the stick")
    os.replace(dst + ".part", dst)
    with open(os.path.join(d, "README.txt"), "w") as fh:
        fh.write("NullMoth NVIDIA driver for macOS 15.\n"
                 "After macOS finishes installing, the 1401 Mac companion installs this package.\n"
                 "By hand: tar -xzf " + PACKAGE["name"] + " && cd pkgroot && sudo ./install.sh\n")
    return dst


def selftest():
    res = []

    def arm(name, cond, shown):
        res.append(bool(cond))
        print(("ok   " if cond else "FAIL ") + name + f"  [{shown}]")

    rtx = {"Manufacturer": "NVIDIA", "Device Type": "Discrete GPU", "Device ID": "10DE-2D05", "Codename": "Unknown"}
    gtx = {"Manufacturer": "NVIDIA", "Device Type": "Discrete GPU", "Device ID": "10DE-1B80", "Codename": "Pascal"}
    rep = {"GPU": {"RTX 5060": dict(rtx), "GTX 1080": dict(gtx)}}
    hit = mark(rep)
    arm("a GeForce RTX 5060 (10de:2d05) is marked macOS 15", hit == ["RTX 5060"] and rep["GPU"]["RTX 5060"]["Compatibility"] == SEQUOIA, hit)
    arm("a GTX 1080 (Pascal, no GSP) is NOT marked", "Compatibility" not in rep["GPU"]["GTX 1080"], rep["GPU"]["GTX 1080"])
    arm("an RTX 3090 (10de:2204) is in NVIDIA's table", supported(dict(rtx, **{"Device ID": "10DE-2204"})), TABLE["ids"].get("2204"))
    coverage = all(supported(dict(rtx, **{"Device ID": "10DE-" + pid})) for pid in TABLE["ids"])
    arm("all 235 display-card IDs are accepted across GTX, RTX, Quadro and workstation families", len(TABLE["ids"]) == 235 and coverage, len(TABLE["ids"]))
    arm("an AMD card with the same product id is NOT marked", not supported(dict(rtx, Manufacturer="AMD")), "AMD")
    lap = {"GPU": {"RTX": dict(rtx), "iGPU": {"Manufacturer": "Intel", "Device Type": "Integrated GPU"}},
           "Monitor": {"panel": {"Connector Type": "Internal", "Connected GPU": "iGPU"}}}
    arm("a laptop whose panel is on the iGPU keeps the engine's rule", mark(lap) == [], lap["GPU"]["RTX"].get("Compatibility"))
    arm("only the 5060 counts as tested", tested(rep) == ["RTX 5060"], tested(rep))

    class R:
        hardware, disabled_devices = rep, {}
    cfg = {"NVRAM": {"Add": {"7C436110-AB2A-4BBB-A880-FE41995C9F82": {"boot-args": "-v", "csr-active-config": bytes(4)}}}}
    ch = []
    on = apply(cfg, R, lambda *a: ch.append(a))
    nv = cfg["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]
    arm("the driver boot-args are added after the existing ones", on and nv["boot-args"].startswith("-v nvfb=1 nvaccel=1"), nv["boot-args"])
    arm("SIP is set to the tested value and recorded", nv["csr-active-config"] == SIP_DRIVER and any(c[0] == "nullmoth-sip" for c in ch), nv["csr-active-config"].hex())
    dl = set(cfg["NVRAM"]["Delete"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"])
    arm("an installed system's boot-args are never deleted; SIP is reasserted", "boot-args" not in dl and "csr-active-config" in dl, sorted(dl))
    ch.clear()
    apply(cfg, R, lambda *a: ch.append(a))
    arm("a second pass changes nothing", ch == [], ch)

    class D:
        hardware, disabled_devices = rep, {"RTX 5060": {}}
    cfg2 = {"NVRAM": {"Add": {}}}
    arm("a disabled card gets no driver settings", apply(cfg2, D, lambda *a: None) is False and not cfg2["NVRAM"]["Add"], cfg2)

    import tempfile  # noqa: PLC0415
    t = tempfile.mkdtemp(prefix="1401-nm-")
    cache, usb = os.path.join(t, "cache"), os.path.join(t, "usb")
    os.makedirs(cache)
    open(os.path.join(cache, PACKAGE["name"]), "wb").write(b"not the package")
    try:
        stage(usb, cache, fetch=lambda u, p: open(p, "wb").write(b"also wrong"))
        bad = "staged"
    except RuntimeError as e:
        bad = str(e)
    arm("a package whose SHA-256 is wrong never reaches the stick", "SHA-256" in bad and not os.path.exists(os.path.join(usb, "NullMoth", PACKAGE["name"])), bad)
    import shutil  # noqa: PLC0415
    shutil.rmtree(t, ignore_errors=True)
    print(f"{sum(res)}/{len(res)} passed")
    return 0 if all(res) else 1


if __name__ == "__main__":
    raise SystemExit(selftest())
