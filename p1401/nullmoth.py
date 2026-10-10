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
import re
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SEQUOIA = ("24.99.99", "24.0.0")  # (max, min) Darwin: the only macOS the driver is built for
# The working machine's OpenCore config before it was changed for dtrace (2026-): kexts, FS, NVRAM, recovery, root.
SIP_DRIVER = bytes.fromhex("430A0000")
# nvfb/nvaccel switch the framebuffer and accelerator on; nvfbheads=4 = the card's display heads; the smooth boot
# takeover is off on the tested machine. The two AMFI args let WindowServer load a GPU bundle Apple did not sign.
BOOT_ARGS = ("nvfb=1", "nvaccel=1", "nvfbheads=4", "-nvkmsnosmooth", "amfi_get_out_of_my_way=0x1", "amfi=0x80")
# Package published with the driver; the stick carries it so the Mac companion can install it offline.
PACKAGE = {"name": "nullmoth-nvidia-1.7.0.tar.gz",
           "url": "https://github.com/nullmoth/nvidia-macos-driver/releases/download/v1.7.0/nullmoth-nvidia-1.7.0.tar.gz",
           "sha256": "e521ab7c6a5147ef8b2b338ab7bc0bbc262f70bcbe2a6ce6222ca5d69d98e892"}

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
    """Gives each supported card macOS 15 compatibility. Returns the names marked.
    A laptop with an unsupported integrated GPU is marked too. This permits building for its discrete GPU; it does not
    establish that the internal panel or external connectors are wired to that GPU. mux_help() describes that limitation."""
    hit = []
    for n, g in cards(report).items():
        g["Compatibility"] = SEQUOIA
        g.pop("OCLP Compatibility", None)
        g["Codename"] = g.get("Codename") if g.get("Codename") not in (None, "", "Unknown") else "NullMoth driver"
        hit.append(n)
    return hit


MUX_HELP = (
    "Laptop display note: the hardware report places the built-in screen on {igpu}. NVIDIA support does not add a "
    "driver for that integrated GPU or reroute the screen to {card}. Firmware output may appear during boot, but "
    "it does not establish that the installer or accelerated desktop will work on this panel.\n\n"
    "A panel or external display needs a connection wired to the NVIDIA GPU for its display driver to use it. "
    "Check the exact model's connector wiring and whether a hardware MUX provides a Discrete GPU mode. "
    "Some laptops have no MUX; a config change cannot create one. If a supported Discrete GPU mode is available, "
    "enable it, restart Windows, then run Check this PC and Build again (a scan taken before the switch still shows the "
    "old wiring). Without a MUX, a monitor on a port wired to the NVIDIA GPU works; the built-in screen stays dark "
    "in macOS.")


BASIC = "basic display (no acceleration)"
BASIC_NOTE = (
    "Basic display: {name} has no macOS driver (NVIDIA GTX 10 and older, AMD RX 7000, Intel Arc). macOS runs on the "
    "screen the card's firmware sets up: the desktop, the installer and everyday apps work, but there is no graphics "
    "acceleration - games, 3D and apps that require Metal will not run, the resolution is the one the firmware picked, "
    "and only the monitor that shows the BIOS screen lights up. A supported card (AMD RX 6000 or older, or an NVIDIA "
    "RTX through the NullMoth driver) gives the full desktop.")


def basic_display(report):
    """A PC whose every GPU is unsupported: keeps the card that drives a monitor (else the first discrete card) for
    macOS 15 so the build continues on the firmware's framebuffer instead of stopping. Nothing in macOS 15 claims these
    cards, so the screen the firmware lit stays lit (the same path the installer already uses for every NVIDIA card).
    62 builds stopped on 'without a supported GPU' through 1.1 (10-09). Returns the name kept, or None."""
    gpus = report.get("GPU") or {}
    if not gpus or any(g.get("Compatibility") not in (None, (None, None)) for g in gpus.values()):
        return None
    shown = {m.get("Connected GPU") for m in (report.get("Monitor") or {}).values()}
    name = next((n for n in gpus if n in shown), None) or next(
        (n for n, g in gpus.items() if g.get("Device Type") == "Discrete GPU"), None) or next(iter(gpus))
    g = gpus[name]
    g["Compatibility"] = SEQUOIA
    g.pop("OCLP Compatibility", None)
    g["Codename"] = BASIC
    return name


def mux_help(report):
    """The build note for a laptop whose built-in panel runs on another GPU (Optimus mode), or None.
    (10-07: five uploaded logs in one night were RTX 4060/5060/5070 Ti laptops in Optimus mode.)"""
    mons = list((report.get("Monitor") or {}).values())
    for n, g in cards(report).items():
        panel = [m for m in mons if m.get("Connector Type") == "Internal" and m.get("Connected GPU", n) != n]
        if panel:
            integrated = (report.get("GPU") or {}).get(panel[0].get("Connected GPU"), {})
            compatibility = integrated.get("Compatibility")
            if compatibility and any(compatibility):
                continue
            return MUX_HELP.format(igpu=panel[0].get("Connected GPU") or "integrated GPU", card=n)
    return None


def tested(report):
    return [n for n, g in cards(report).items() if _pid(g) in TABLE["tested"]]


def gpu_disabled(name, gpu, disabled_devices):
    """Match upstream's exact disabled-device labels without conflating identical PCI IDs."""
    labels = {name, "GPU: " + name}
    device_type = gpu.get("Device Type")
    if device_type:
        labels.add(str(device_type) + ": " + name)
    return any(label in disabled_devices for label in labels)


def apply(cfg, result, change):
    """Policy-pass rule. cfg = the loaded config.plist dict; change(rule, before, after, why) records it.
    Returns True when the driver settings were applied (the SIP rule then must not lower them again)."""
    gpus = (result.hardware or {}).get("GPU", {})
    live = [n for n, g in gpus.items() if supported(g) and g.get("Compatibility") == SEQUOIA and not gpu_disabled(n, g, result.disabled_devices)]
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
    laptop_gpu_awake(cfg, result, live, change)
    delete = cfg["NVRAM"].setdefault("Delete", {}).setdefault("7C436110-AB2A-4BBB-A880-FE41995C9F82", [])
    # not boot-args (): deleting it replaced the flags of a machine already running macOS. SIP is safe to reassert.
    for k in ("csr-active-config",):
        if k not in delete:
            delete.append(k)
    return True



def laptop_gpu_awake(cfg, result, live, change):
    """Laptops: the GPU's PCI path gets acpi-wake-type = 1 in DeviceProperties. Without it the laptop's ACPI powers the
    discrete GPU down in macOS and the driver's bring-up fails (RmInitAdapter); with it, users with an RTX 4060 Laptop
    (i7-13620H), RTX 3050 and RTX 4050 laptops in Discrete/dGPU mode reached a Metal desktop (user reports, 2026-10-08,
    several independent reports of the same manual step). Desktop cards are left alone."""
    hw = result.hardware or {}
    if (hw.get("Motherboard") or {}).get("Platform") != "Laptop":
        return
    gpus = hw.get("GPU") or {}
    add = cfg.setdefault("DeviceProperties", {}).setdefault("Add", {})
    for name in live:
        path = (gpus.get(name) or {}).get("PCI Path") or ""
        if not re.fullmatch(r"PciRoot\(0x[0-9A-Fa-f]+\)(/Pci\(0x[0-9A-Fa-f]+,0x[0-9A-Fa-f]+\))+", path):
            continue
        props = add.setdefault(path, {})
        if props.get("acpi-wake-type") != 1:
            change("nullmoth-laptop-gpu-awake", str(props.get("acpi-wake-type", "")), "1",
                   f"{name}: keeps the laptop's discrete GPU powered for the NullMoth driver (acpi-wake-type)")
            props["acpi-wake-type"] = 1

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


def system_profile(report):
    """What the Mac side's per-system rules need from Windows (macOS only sees the SMBIOS model 1401 set): the real board,
    chipset and form factor, the CPU, and every GPU with its PCI id and Resizable BAR state. Field names are the
    hardware report's own (Motherboard.Name/Chipset/Platform, CPU.Manufacturer/Processor Name/Codename, GPU.*)."""
    mb, cpu = report.get("Motherboard") or {}, report.get("CPU") or {}
    gpus = [{"name": n, "vendor": g.get("Manufacturer"), "id": g.get("Device ID"), "type": g.get("Device Type"),
             "rebar": g.get("Resizable BAR")} for n, g in (report.get("GPU") or {}).items() if isinstance(g, dict)]
    return {"board": mb.get("Name"), "chipset": mb.get("Chipset"), "platform": mb.get("Platform"),
            "cpu_vendor": (cpu.get("Manufacturer") or "").lower() or None, "cpu": cpu.get("Processor Name"),
            "cpu_codename": cpu.get("Codename"), "gpus": gpus}


RELEASE_API = "https://api.github.com/repos/nullmoth/nvidia-macos-driver/releases/latest"
_PKG_RE = re.compile(r"^nullmoth-nvidia-(\d+\.\d+\.\d+)\.tar\.gz$")
_MAC_RE = re.compile(r"^1401-Mac-(\d+\.\d+\.\d+)\.zip$")


def _vkey(v):
    return tuple(int(x) for x in v.split("."))


def latest_release(get_json, get_text):
    """The newest driver release: {"driver": (name, url, sha256), "mac": (name, url, sha256) or None}. Hashes come from
    the SHA256SUMS.txt published in the same release; a package it does not list is refused."""
    rel = get_json(RELEASE_API)
    assets = {a.get("name"): a.get("browser_download_url") for a in rel.get("assets", []) if isinstance(a, dict)}
    sums_url = assets.get("SHA256SUMS.txt")
    if not sums_url:
        raise RuntimeError("the latest driver release has no SHA256SUMS.txt")
    sums = {}
    for line in get_text(sums_url).splitlines():
        f = line.split()
        if len(f) >= 2 and re.fullmatch(r"[0-9a-fA-F]{64}", f[0]):
            sums[f[-1]] = f[0].lower()
    out = {"driver": None, "mac": None}
    for name, url in assets.items():
        for key, rx in (("driver", _PKG_RE), ("mac", _MAC_RE)):
            m = rx.match(name or "")
            if m and url and url.startswith("https://") and name in sums:
                if out[key] is None or _vkey(m.group(1)) > _vkey(rx.match(out[key][0]).group(1)):
                    out[key] = (name, url, sums[name])
    if out["driver"] is None:
        raise RuntimeError("the latest release has no driver package listed in SHA256SUMS.txt")
    return out


def update(dirs, rel, fetch):
    """Puts the newest driver package (and 1401 Mac app) from `rel` into every folder in `dirs` (the app's NullMoth
    folder, then any 1401 stick's NullMoth folder), verified by SHA-256, and removes older copies there - the stick
    writer takes the first package it finds. Downloads once, into dirs[0]. Returns the lines to show."""
    import hashlib  # noqa: PLC0415
    import shutil  # noqa: PLC0415

    def sha(p):
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for b in iter(lambda: fh.read(1 << 20), b""):
                h.update(b)
        return h.hexdigest()

    lines = []
    for key, rx in (("driver", _PKG_RE), ("mac", _MAC_RE)):
        item = rel.get(key)
        if not item:
            continue
        name, url, want = item
        os.makedirs(dirs[0], exist_ok=True)
        src = os.path.join(dirs[0], name)
        if not (os.path.exists(src) and sha(src) == want):
            fetch(url, src + ".part")
            if sha(src + ".part") != want:
                os.remove(src + ".part")
                raise RuntimeError(f"{name} does not match the SHA-256 published with it - nothing was replaced")
            os.replace(src + ".part", src)
            lines.append(f"downloaded {name}")
        for d in dirs:
            os.makedirs(d, exist_ok=True)
            dst = os.path.join(d, name)
            if d != dirs[0] and not (os.path.exists(dst) and sha(dst) == want):
                shutil.copyfile(src, dst + ".part")
                if sha(dst + ".part") != want:
                    os.remove(dst + ".part")
                    raise RuntimeError(f"{name} changed while copying to {d}")
                os.replace(dst + ".part", dst)
                lines.append(f"{name} -> {d}")
            for old in os.listdir(d):
                if old != name and rx.match(old):
                    os.remove(os.path.join(d, old))
                    lines.append(f"removed older {old} from {d}")
    return lines


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
    arm("a laptop whose panel is on the iGPU is still marked (no more refusal at Build)", mark(lap) == ["RTX"], lap["GPU"]["RTX"].get("Compatibility"))
    note = mux_help(lap) or ""
    arm("that laptop gets the built-in-screen note naming its iGPU and the MUX switch", "iGPU" in note and "MUX" in note, note[:60])
    arm("a desktop gets no laptop note", mux_help(rep) is None, mux_help(rep))
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
    t490 = os.path.join(HERE, "..", "tests", "corpus", "cache", "thinkpad-t490s", "Report.json")
    if os.path.exists(t490):
        with open(t490) as fh:
            sp = system_profile(json.load(fh))
        arm("the stick's system profile carries the real board, chipset, form factor, CPU and GPUs",
            sp["board"] == "LENOVO 20NXS1U203" and sp["chipset"] == "Cannon Point-LP" and sp["platform"] == "Laptop"
            and sp["cpu_vendor"] == "intel" and sp["gpus"] and sp["gpus"][0]["id"], (sp["board"], sp["chipset"], sp["cpu_vendor"]))
    # --- Update driver (newest release, verified by its own SHA256SUMS.txt) - no network: fake release + fetch
    import hashlib  # noqa: PLC0415
    import tempfile  # noqa: PLC0415
    blob = {"https://x/nullmoth-nvidia-1.0.7.tar.gz": b"driver 1.0.7", "https://x/1401-Mac-1.0.10.zip": b"mac 1.0.10"}
    hx = {k.rsplit("/", 1)[1]: hashlib.sha256(v).hexdigest() for k, v in blob.items()}
    sums = "".join(f"{h}  {n}\n" for n, h in hx.items())
    api = {"assets": [{"name": n, "browser_download_url": "https://x/" + n} for n in hx] +
           [{"name": "nullmoth-nvidia-9.9.9.tar.gz", "browser_download_url": "https://x/unlisted"},
            {"name": "SHA256SUMS.txt", "browser_download_url": "https://x/sums"}]}
    rel = latest_release(lambda u: api, lambda u: sums)
    arm("the newest release's driver and Mac app are picked, each with its published SHA-256",
        rel["driver"][0] == "nullmoth-nvidia-1.0.7.tar.gz" and rel["mac"][0] == "1401-Mac-1.0.10.zip"
        and rel["driver"][2] == hx["nullmoth-nvidia-1.0.7.tar.gz"], (rel["driver"][0], rel["mac"] and rel["mac"][0]))
    arm("a package missing from SHA256SUMS.txt is never picked", "9.9.9" not in rel["driver"][0], rel["driver"][0])
    app, stick = tempfile.mkdtemp(prefix="1401-selftest-"), tempfile.mkdtemp(prefix="1401-selftest-")
    for d in (app, stick):
        open(os.path.join(d, "nullmoth-nvidia-1.0.6.tar.gz"), "wb").write(b"old")
        open(os.path.join(d, "1401-Mac-1.0.9.zip"), "wb").write(b"old")
    got = []
    lines = update([app, stick], rel, lambda u, p: (got.append(u), open(p, "wb").write(blob[u])))
    arm("Update driver downloads each file once, puts both in the app folder and on the stick, removes the old copies",
        len(got) == 2 and sorted(os.listdir(app)) == sorted(os.listdir(stick)) == ["1401-Mac-1.0.10.zip", "nullmoth-nvidia-1.0.7.tar.gz"],
        (len(got), sorted(os.listdir(stick))))
    bad = tempfile.mkdtemp(prefix="1401-selftest-")
    open(os.path.join(bad, "nullmoth-nvidia-1.0.6.tar.gz"), "wb").write(b"old")
    try:
        update([bad], {"driver": rel["driver"], "mac": None}, lambda u, p: open(p, "wb").write(b"tampered"))
        refused = False
    except RuntimeError:
        refused = True
    arm("a download that does not match its published SHA-256 is refused and the old package stays",
        refused and os.listdir(bad) == ["nullmoth-nvidia-1.0.6.tar.gz"], os.listdir(bad))
    print(f"{sum(res)}/{len(res)} passed")
    return 0 if all(res) else 1


def _cli_update(dirs):
    """python -m p1401.nullmoth update <app NullMoth dir> [<stick root>/NullMoth ...]: newest driver + Mac app."""
    import shutil  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415
    from p1401 import tls  # noqa: PLC0415
    tls.install()

    def get(url):
        rq = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "1401"})
        with urllib.request.urlopen(rq, timeout=60) as r:
            return r.read()

    def fetch(url, path):
        rq = urllib.request.Request(url, headers={"User-Agent": "1401"})
        with urllib.request.urlopen(rq, timeout=120) as r, open(path, "wb") as fh:
            shutil.copyfileobj(r, fh, 1 << 20)

    try:
        rel = latest_release(lambda u: json.loads(get(u)), lambda u: get(u).decode("utf-8", "replace"))
        print(f"newest driver: {rel['driver'][0]}" + (f", Mac app: {rel['mac'][0]}" if rel["mac"] else ""))
        for line in update(dirs, rel, fetch):
            print(line)
        print("RESULT ok")
        return 0
    except Exception as e:  # noqa: BLE001 - the reason is what the user sees
        print(f"RESULT stop: {e}")
        return 1


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "update":
        raise SystemExit(_cli_update(sys.argv[2:]))
    raise SystemExit(selftest())
