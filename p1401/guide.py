"""Builds the install guide for one machine: what to do first, which BIOS settings to change on that machine, how
to boot the stick, and how to install. Input is the scan (Report.json) and the EFI 1401 built (config.plist).

Ask for as few BIOS changes as possible. Each one is a chance to break Windows, so a setting is only listed when
macOS needs it on this machine, and the guide says "leave it" where the EFI already works around it (read from the
built config, not assumed). TPM/PTT and SGX are never touched: turning TPM off breaks Windows 11 and BitLocker, and
macOS doesn't care about either.

Windows problems get fixed before any BIOS change. From the corpus: hp-pavilion-15-dk0 has SATA in RAID mode, and
switching to AHCI without the safe-mode step leaves Windows failing with INACCESSIBLE_BOOT_DEVICE. A Legacy-mode
Windows stops booting when CSM goes off. Turning Secure Boot off with BitLocker on asks for the recovery key.

If the scan couldn't see something (BitLocker state, for example), the guide says so and keeps the step.

BIOS facts are checked against the Dortania OpenCore Install Guide, but the wording is our own (that guide is
CC BY-NC-SA, so none of its text is copied into this GPL-3 project).

    python3 -m p1401.guide <Report.json> <config.plist> [--bitlocker On|Off] [--macos 25]
    python3 -m p1401.guide <Report.json> <config.plist> --html guide.html [--mark other.jpg]   (default: the NullMoth mark beside this file)
"""
import base64
import html
import os
import plistlib
import re
import sys
from dataclasses import dataclass, field

NVRAM_APPLE = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
HERE = os.path.dirname(os.path.abspath(__file__))
# Darwin major -> the name Apple ships it under. The engine answers in Darwin versions ("25.99.99").
MACOS = {19: "macOS Catalina 10.15", 20: "macOS Big Sur 11", 21: "macOS Monterey 12", 22: "macOS Ventura 13",
         23: "macOS Sonoma 14", 24: "macOS Sequoia 15", 25: "macOS Tahoe 26"}


def macos_name(darwin):
    try:
        return MACOS.get(int(str(darwin).split(".")[0]), "")
    except ValueError:
        return ""


class GuideError(RuntimeError):
    pass


@dataclass
class Setting:
    name: str            # what the BIOS usually calls it
    want: str            # the value to set
    required: bool       # False = recommended
    why: str
    now: str = ""        # what the scan saw, when it saw it
    if_missing: str = "If your BIOS doesn't have this setting, skip it."


@dataclass
class Step:
    title: str
    body: list = field(default_factory=list)  # lines; `command`, **app button** and [[key]] are the only markup
    blocker: bool = False  # must be done before the BIOS changes
    settings: list = field(default_factory=list)  # [Setting]: the BIOS step's printout


# (setup key, one-time boot menu key). Only vendors whose keys are consistent across their lines are named;
# anything else gets the generic line instead of a guess that sends someone into the wrong menu.
KEYS = {
    "ASUSTEK": {"Desktop": ("Del or F2", "F8"), "Laptop": ("F2", "Esc")},
    "GIGABYTE": ("Del", "F12"),
    "MICRO-STAR": ("Del", "F11"),
    "MSI": ("Del", "F11"),
    "ASROCK": ("F2 or Del", "F11"),
    "DELL": ("F2", "F12"),
    "HP": ("F10", "F9 (or Esc for the startup menu)"),
    "HEWLETT": ("F10", "F9 (or Esc for the startup menu)"),
    "LENOVO": ("F1 (ThinkPad/ThinkCentre) or F2 (other Lenovo)", "F12"),
    "FUJITSU": ("F2", "F12"),
    "ACER": ("F2", "F12 (turn on 'F12 Boot Menu' in the BIOS first)"),
}


def _vendor(mb_name):
    first = mb_name.split()[0].upper() if mb_name.split() else ""
    return first if first in KEYS else ""


def keys(report):
    mb = report.get("Motherboard") or {}
    v = _vendor(mb.get("Name", ""))
    if not v:
        return None
    k = KEYS[v]
    return k.get(mb.get("Platform"), k["Desktop"]) if isinstance(k, dict) else k


def _storage_trap(report):
    """RAID/RST/VMD storage: macOS can't see the drives, and Windows needs a safe-mode boot to survive the switch."""
    hits = [n for n in (report.get("Storage Controllers") or {})
            if any(t in n.upper() for t in ("RAID", "VOLUME MANAGEMENT", "VMD", "RST "))]
    return hits


def bios_settings(report, config):
    cpu = report.get("CPU") or {}
    intel = "Intel" in (cpu.get("Manufacturer") or "")
    bios = report.get("BIOS") or {}
    gpus = report.get("GPU") or {}
    dgpu = [n for n, g in gpus.items() if g.get("Device Type") == "Discrete GPU"]
    igpu_intel = any(g.get("Device Type") == "Integrated GPU" and g.get("Manufacturer") == "Intel" for g in gpus.values())
    kq = ((config.get("Kernel") or {}).get("Quirks")) or {}
    boot_args = (((config.get("NVRAM") or {}).get("Add") or {}).get(NVRAM_APPLE) or {}).get("boot-args", "")
    s = []

    sb = bios.get("Secure Boot", "")
    asus = _vendor((report.get("Motherboard") or {}).get("Name", "")) == "ASUSTEK"
    s.append(Setting("Secure Boot", "Off", True,
                     "The macOS stick isn't signed by Microsoft, so a PC with Secure Boot on refuses to start it.",
                     now=("already off, nothing to change" if sb == "Disabled" else
                          f"currently {sb}" if sb else "the scan couldn't read it"),
                     if_missing="It's usually on a Boot or Security tab." +
                                (" On ASUS boards, set Boot -> Secure Boot -> OS Type to 'Other OS'." if asus else "")))
    s.append(Setting("CSM (Compatibility Support Module / Legacy boot)", "Off", True,
                     "macOS starts only in pure UEFI mode. With CSM on, graphics often stall during boot."))
    s.append(Setting("Fast Boot (in the BIOS, not Windows)", "Off", False,
                     "Fast Boot can skip USB setup, so the PC never sees the stick."))
    a4g = bios.get("Above 4G Decoding", "")
    if "npci=" in boot_args:
        s.append(Setting("Above 4G Decoding", "On if you have it", False,
                         "Lets the GPU map its full memory. Your EFI already carries the workaround if it's missing.",
                         now=f"currently {a4g}" if a4g else ""))
    else:
        s.append(Setting("Above 4G Decoding", "On", bool(dgpu),
                         "Lets the GPU map its full memory. Without it, macOS panics early on many graphics cards.",
                         now=f"currently {a4g} - turn it On" if a4g == "Disabled" else (f"currently {a4g}" if a4g else ""),
                         if_missing="Most laptops don't show this setting. If yours doesn't, skip it."
                         if (report.get("Motherboard") or {}).get("Platform") == "Laptop" else
                         "If your BIOS doesn't have it, skip it."))
    rebar = sorted({g.get("Resizable BAR") for g in gpus.values() if g.get("Resizable BAR") in ("Enabled", "Disabled")})
    if dgpu and rebar:
        s.append(Setting("Resizable BAR / Re-Size BAR", f"Leave it {rebar[0]}", True,
                         "Your EFI was built for this exact setting. If you change it, rebuild it in the app.",
                         now=f"currently {'/'.join(rebar)}", if_missing=""))
    s.append(Setting("XHCI Hand-off (and EHCI Hand-off if listed)", "On", False,
                     "Lets macOS take over the USB ports from the firmware."))
    if intel:
        cfg = kq.get("AppleXcpmCfgLock") or kq.get("AppleCpuPmCfgLock")
        s.append(Setting("CFG Lock (MSR 0xE2 write protection)", "Off", not cfg,
                         "macOS writes a CPU power-management register that CFG Lock freezes.",
                         if_missing=("Most BIOSes hide it. Skip it: your EFI already works around CFG Lock." if cfg else
                                     "Your EFI does NOT work around this one, so it has to be off.")))
        if not kq.get("DisableIoMapper"):
            s.append(Setting("VT-d", "Off", True, "macOS's own VT-d handling conflicts with most PC firmware."))
        if igpu_intel:
            s.append(Setting("DVMT Pre-Allocated (iGPU memory)", "64M or more", False,
                             "Gives Intel graphics enough memory for macOS's framebuffer.",
                             if_missing="Skip it if your BIOS doesn't show it; most laptops don't."))
    else:
        s.append(Setting("IOMMU", "Off", False, "The AMD IOMMU is a common cause of hangs early in the macOS boot."))
    return s


def build_guide(report, config, bitlocker=None, macos=""):
    """-> [Step]. bitlocker: 'On' | 'Off' | None (unknown - then the step is kept)."""
    mb = report.get("Motherboard") or {}
    if not mb.get("Name") or not report.get("CPU"):
        raise GuideError("the scan has no motherboard or CPU - scan again before building a guide")
    bios = report.get("BIOS") or {}
    steps = []

    before = Step("Before you start", [
        "Back up anything you can't lose. Installing macOS erases the disk you choose for it.",
        "Install macOS on its own disk if you can. The installer erases the whole disk you pick, and that is the one "
        "step you can't undo.",
        "Have Ethernet ready. Many PC Wi-Fi cards don't work inside the macOS installer.",
    ])
    steps.append(before)

    if bitlocker != "Off":
        steps.append(Step("BitLocker (Windows drive encryption)", [
            ("BitLocker is ON on this PC. " if bitlocker == "On" else
             "The app couldn't tell whether BitLocker is on. If it is: ") +
            "save your recovery key first (Settings -> Privacy & security -> Device encryption, or aka.ms/myrecoverykey). "
            "Then the app pauses BitLocker for your next restarts. Changing Secure Boot with BitLocker running makes Windows "
            "ask for that key.",
        ], blocker=True))

    if bios.get("Firmware Type") and bios.get("Firmware Type") != "UEFI":
        steps.append(Step("Windows is installed in Legacy (BIOS) mode", [
            "macOS needs CSM off, and a Legacy-mode Windows stops booting once CSM is off.",
            "Convert Windows to UEFI first, using Microsoft's built-in MBR2GPT tool: in an administrator terminal, run "
            "`mbr2gpt /validate /allowFullOS`, then `mbr2gpt /convert /allowFullOS`. Only after that, turn CSM off.",
            "Back up before converting.",
        ], blocker=True))

    trap = _storage_trap(report)
    if trap:
        steps.append(Step("Your drive controller is in RAID mode", [
            f"The scan found {', '.join(trap)}. macOS can't see drives in RAID/RST/VMD mode, so it has to change to "
            "AHCI, and Windows won't boot after that change unless you prepare it first:",
            "1. In an administrator terminal, run `bcdedit /set {current} safeboot minimal`, then restart into the BIOS.",
            "2. Set SATA Mode to AHCI (or turn Intel VMD off), save, and let Windows start. It starts in Safe Mode.",
            "3. In Safe Mode, run `bcdedit /deletevalue {current} safeboot` and restart. Windows now boots normally on AHCI.",
        ], blocker=True))

    steps.append(Step("Make the macOS stick", [
        "The app does this part. Use a USB stick of 4 GB or larger; everything on it is erased.",
        f"It writes this PC's boot files and downloads {macos or 'macOS'} straight from Apple, checking every piece "
        "against Apple's signature.",
    ]))

    k = keys(report)
    # They can't see this page while they're in the BIOS, so have them photograph it first.
    open_bios = ["Before you restart, take a photo of this page with your phone. You can't see it while you're in "
                 "the BIOS."]
    open_bios.append("Click **Restart into BIOS setup** in the app. Windows restarts straight into your BIOS setup."
                     if bios.get("Firmware Type", "UEFI") == "UEFI" else
                     "Restart and press the setup key as soon as the PC powers on.")
    open_bios.append(f"If that doesn't work: restart and press [[{k[0]}]] repeatedly right after power-on." if k else
                     "If that doesn't work: restart and press the setup key for your PC (usually Del, F2, F10 or F1; "
                     "your manual names it).")
    open_bios.append("Change the settings below, then Save & Exit (on most boards [[F10]]). Let Windows start once "
                     "to check it still boots.")
    steps.append(Step("Change these BIOS settings, then Save & Exit", open_bios,
                      settings=bios_settings(report, config)))

    steps.append(Step("Start from the stick", [
        "Leave the stick plugged in. Click **Restart now and pick the USB stick (Use a device)** in the app. Windows "
        "restarts into its blue startup menu: choose Use a device, then your USB stick.",
        f"Or restart and press [[{k[1]}]] repeatedly as the PC starts, to open its boot menu, then pick the USB stick "
        "marked UEFI." if k else
        "Or restart and press your PC's boot-menu key (often F12, F11, F9 or Esc), then pick the USB stick marked UEFI.",
        "A boot menu appears. Pick the macOS installer (the entry ending in '(dmg)').",
    ]))
    steps.append(Step("Install macOS", [
        "Open Disk Utility -> View -> Show All Devices. Select the whole DISK you chose for macOS (not Windows' disk). "
        "Erase it as 'Macintosh HD', format APFS, scheme GUID Partition Map.",
        "Quit Disk Utility, choose Reinstall macOS, and pick 'Macintosh HD'.",
        "The PC restarts several times. Each time, start from the stick again and pick 'macOS Installer' until it "
        "becomes 'Macintosh HD'.",
        "Keep the stick. For now it's how this PC starts macOS.",
    ]))
    return steps


def setting_line(st):
    line = f"**{st.name} -> {st.want}** ({'must' if st.required else 'recommended'}). {st.why}"
    if st.now:
        line += f" [{st.now}]"
    if st.if_missing:
        line += f" {st.if_missing}"
    return line


def render_text(steps):
    out = []
    for i, st in enumerate(steps, 1):
        out.append(f"{i}. {st.title}" + ("  (do this before changing the BIOS)" if st.blocker else ""))
        out.extend(f"   - {b}" for b in st.body)
        out.extend(f"   - {setting_line(x)}" for x in st.settings)
    return "\n".join(out).replace("[[", "").replace("]]", "")


# HTML page. The app, the copy on the stick, and the preview all use this one renderer so they can't drift apart.
# Styling matches nullmothsystems.com and the 1401 Probe (see guide.css); layout is an old setup wizard, one step
# per page. Everything is inline because the page opens from the stick with no network, and the CSP blocks every
# request.
CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'"


def _keys(k):
    out = []
    for part in k.split(" or "):
        key, _, note = part.partition(" (")
        out.append(f"<kbd>{key}</kbd>" + (f" ({note}" if note else ""))
    return " or ".join(out)


def _inline(s):
    """Escape first (board and controller names come from the scan and can contain anything), then code/bold/keys."""
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"\[\[(.+?)\]\]", lambda m: _keys(m.group(1)), s)


def _pc(report, macos):
    mb = report.get("Motherboard") or {}
    cpu = re.sub(r"\((R|TM|tm)\)", "", (report.get("CPU") or {}).get("Processor Name", ""))
    return [("Board", mb.get("Name", "")), ("Type", mb.get("Platform", "")), ("CPU", " ".join(cpu.split())),
            ("Graphics", ", ".join(report.get("GPU") or {})), ("macOS", macos)]


def _printout(settings):
    rows = []
    for st in settings:
        flag = (("ok", "already done") if st.now.startswith("already") else
                ("must", "MUST") if st.required else ("opt", "optional"))
        rows.append(f'<tr><td class="set"><b>{_inline(st.name)}</b><br><span class="{flag[0]}">{flag[1]}</span></td>'
                    f'<td><b class="want">-> {_inline(st.want)}</b><br>{_inline(st.why)}'
                    + (f'<br><span class="saw">Your scan: {_inline(st.now)}</span>' if st.now else "")
                    + (f'<br><span class="miss">{_inline(st.if_missing)}</span>' if st.if_missing else "") + "</td></tr>")
    return ('<div class="printout"><p class="ph">BIOS SETTINGS FOR THIS PC ... print it, or take a photo of it</p>'
            f'<table class="bios" cellspacing="0" cellpadding="0">{"".join(rows)}</table></div>')


def app_html(report, steps, macos="", mark=None, uid="g"):
    """Every step is rendered visible; guide.js turns it into one step at a time with Back and Next.
    Old-school layout: tables, <center>, <hr>, underlined links (see guide.css). The step list is plain
    #anchors, so it still works with scripts off."""
    n, side, pages = len(steps), [], []
    for i, st in enumerate(steps, 1):
        side.append(f'<li><a class="nav" href="#{uid}-h{i}"><span class="n">{i}</span> <span class="t">{_inline(st.title)}</span></a>'
                    + (' <span class="star">*</span>' if st.blocker else "") + "</li>")
        body, ol = [], []
        for line in st.body:
            m = re.match(r"(\d+)\.\s+(.*)", line)
            if m:
                ol.append(f"<li>{_inline(m.group(2))}</li>")
                continue
            if ol:
                body.append(f"<ol>{''.join(ol)}</ol>")
                ol = []
            body.append(f"<p>{_inline(line)}</p>")
        if ol:
            body.append(f"<ol>{''.join(ol)}</ol>")
        if st.settings:
            body.append(_printout(st.settings))
        caution = ('<p class="caution"><b>STOP!</b> Do this one before you change anything in the BIOS.</p>'
                   if st.blocker else "")
        pages.append(f'<section class="pg" aria-labelledby="{uid}-h{i}"><p class="stepno">Step {i} of {n}</p>'
                     f'<h2 id="{uid}-h{i}" tabindex="-1">{_inline(st.title)}</h2>{caution}{"".join(body)}</section>')
    img = (f'<img class="mark" src="data:image/jpeg;base64,{base64.b64encode(mark).decode()}" width="56" height="56" '
           'alt="">' if mark else "")
    plate = "".join(f"<tr><th>{a}</th><td>{_inline(b)}</td></tr>" for a, b in _pc(report, macos) if b)
    first = (' The ones with a red <span class="star">*</span> come first, before you touch the BIOS.'
             if any(st.blocker for st in steps) else "")
    return f'''<div class="app" id="{uid}">
<center class="top">
<table class="logo" role="presentation" cellspacing="0" cellpadding="0"><tr><td>{img}</td><td class="word"><span class="nm">NullMoth</span> <span class="sy">Systems</span><br><span class="ig">1401 Install Guide</span> for this PC</td></tr></table>
</center>
<div class="ticker" aria-hidden="true"><span>*** WRITTEN FOR THIS PC *** NOTHING ON THIS PAGE WAS SENT ANYWHERE *** TAKE A PHOTO BEFORE YOU OPEN THE BIOS *** 1401 IS FREE FOREVER ***</span></div>
<p class="hello">Hi! The 1401 app wrote this page on this PC, just for this PC &mdash; the keys and BIOS settings below are for <b>your</b> board, not anybody else's. Go through the steps in order and take your time.{first}</p>
<table class="pc" border="1" cellspacing="2" cellpadding="3"><caption>This guide is for:</caption>{plate}</table>
<table class="main" role="presentation" cellspacing="0" cellpadding="0"><tr>
<td class="side"><nav aria-label="Steps"><p class="sh">Steps</p><ol>{"".join(side)}</ol>
<p class="every"><button type="button" class="all" aria-pressed="false">Show all the steps on one page</button></p></nav></td>
<td class="content">{"".join(pages)}
<hr>
<table class="btns" role="presentation" cellspacing="0" cellpadding="0"><tr><td class="where">{n} steps</td><td class="go"><button type="button" class="b back">&lt; Back</button> <button type="button" class="b next">Next &gt;</button></td></tr></table>
</td></tr></table>
<center class="foot">
<hr width="80%">
<p><a href="#{uid}">Back to the top</a></p>
<p class="badges" aria-hidden="true"><span class="bd bd1">NullMoth</span><span class="bd bd2">VIEWABLE WITH<br>ANY BROWSER</span><span class="bd bd3">NO COOKIES<br>NO TRACKING</span><span class="bd bd4">FREE<br>FOREVER</span></p>
<p class="counter">You are visitor number <b>000001</b> (it's only ever you &mdash; this page never left this PC)</p>
<p>© 2026 NullMoth Systems<br>NullMoth and the moth logo are trademarks of NullMoth Systems.</p>
<p class="present">Present day. Present time.</p>
</center>
</div>'''


def assets():
    with open(os.path.join(HERE, "guide.css"), encoding="utf-8") as fh:
        css = fh.read()
    with open(os.path.join(HERE, "guide.js"), encoding="utf-8") as fh:
        js = fh.read()
    return css, js


def render_html(report, steps, macos="", mark=None):
    """mark=None puts in the NullMoth mark that ships beside this file (128 px JPEG, no EXIF); b"" leaves it out.
    The mark and the NullMoth name aren't covered by the GPL (see NOTICE.md); modified builds must remove them."""
    if mark is None:
        with open(os.path.join(HERE, "moth-mark.jpg"), "rb") as fh:
            mark = fh.read()
    css, js = assets()
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<meta http-equiv="Content-Security-Policy" content="{CSP}">\n'
            '<meta name="color-scheme" content="dark">\n<title>1401 Install Guide</title>\n'
            f'<style>\n{css}</style>\n</head>\n<body>\n{app_html(report, steps, macos, mark)}\n'
            f'<script>\n{js}</script>\n</body>\n</html>\n')


def leaks(page):
    """What a page must never carry: an email address, or a user-folder path from the machine that built it."""
    return (re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", page) + re.findall(r"/Users/[^/\s\"'<]+", page)
            + re.findall(r"[A-Za-z]:\\Users\\[^\\\s\"'<]+", page))


def load(report_path, config_path):
    import json  # noqa: PLC0415
    with open(report_path, encoding="utf-8") as fh:
        report = json.load(fh)
    with open(config_path, "rb") as fh:
        config = plistlib.load(fh)
    return report, config


def selftest():
    import copy  # noqa: PLC0415
    import glob  # noqa: PLC0415
    import json  # noqa: PLC0415
    import os  # noqa: PLC0415
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache = os.path.join(repo, "tests", "corpus", "cache")
    built = os.path.join(repo, "out", "corpus")
    if not os.path.isdir(cache) or not os.path.isdir(built):
        print("can't run: corpus or built EFIs missing (run tests/corpus/fetch.py, then tests/run_corpus.py build)")
        return False
    res = []

    def arm(name, cond, shown):
        res.append(bool(cond))
        print(("ok   " if cond else "FAIL ") + name + f"  [{shown}]")

    reports = {os.path.basename(d): json.load(open(os.path.join(d, "Report.json"))) for d in sorted(glob.glob(cache + "/*"))}
    configs = {}
    for m in reports:
        p = os.path.join(built, m, "EFI", "OC", "config.plist")
        if os.path.isfile(p):
            with open(p, "rb") as fh:
                configs[m] = plistlib.load(fh)
    texts = {}
    for m, r in reports.items():
        try:
            texts[m] = render_text(build_guide(r, configs.get(m, {})))
        except Exception as e:  # noqa: BLE001 - reported by the next check
            texts[m] = f"ERROR {type(e).__name__}: {e}"
    arm("a guide renders for every corpus machine", all(not t.startswith("ERROR") for t in texts.values()),
        f"{sum(not t.startswith('ERROR') for t in texts.values())}/{len(texts)}")
    arm("every guide requires Secure Boot off", all("Secure Boot -> Off** (must)" in t for t in texts.values()), "all")

    pav = texts["hp-pavilion-15-dk0"]
    arm("the HP Pavilion (SATA in RAID mode) gets the safe-mode AHCI step, before the BIOS step",
        "RAID mode" in pav and pav.index("RAID mode") < pav.index("Change these BIOS settings"), "RAID step first")
    others = [m for m, t in texts.items() if "safeboot minimal" in t and m != "hp-pavilion-15-dk0"]
    arm("no AHCI machine gets the RAID step (the trap check doesn't fire on everyone)", not others, others or "none")

    amd = [m for m, r in reports.items() if "AMD" in r["CPU"].get("Manufacturer", "")]
    arm("AMD machines get IOMMU and never CFG Lock", all("IOMMU" in texts[m] and "CFG Lock" not in texts[m] for m in amd), amd)
    intel_cfg = [m for m in reports if m in configs and "Intel" in reports[m]["CPU"].get("Manufacturer", "")]
    arm("Intel machines whose EFI has the CFG-Lock quirk are told they may skip it",
        all("already works around CFG Lock" in texts[m] for m in intel_cfg), f"{len(intel_cfg)} Intel with EFIs")
    cfg_off = copy.deepcopy(configs[intel_cfg[0]])
    cfg_off["Kernel"]["Quirks"]["AppleXcpmCfgLock"] = cfg_off["Kernel"]["Quirks"]["AppleCpuPmCfgLock"] = False
    t = render_text(build_guide(reports[intel_cfg[0]], cfg_off))
    arm("...and an EFI without the quirk makes CFG Lock required", "CFG Lock (MSR 0xE2 write protection) -> Off** (must)" in t, intel_cfg[0])

    a4 = [m for m, r in reports.items() if (r.get("BIOS") or {}).get("Above 4G Decoding") == "Disabled"]
    arm("a machine the scan saw with Above 4G disabled is told to turn it on", all("turn it On" in texts[m] for m in a4), a4)

    legacy = copy.deepcopy(reports["optiplex-5050-micro"])
    legacy["BIOS"]["Firmware Type"] = "Legacy"
    t = render_text(build_guide(legacy, configs.get("optiplex-5050-micro", {})))
    arm("Legacy-mode Windows gets MBR2GPT before any BIOS change", "mbr2gpt /convert" in t and
        t.index("mbr2gpt") < t.index("Change these BIOS settings"), "legacy")
    arm("...and a UEFI Windows never does", not any("mbr2gpt" in texts[m] for m in texts), "0 UEFI hits")

    t_on = render_text(build_guide(reports["dell-e7470"], configs.get("dell-e7470", {}), bitlocker="On"))
    t_off = render_text(build_guide(reports["dell-e7470"], configs.get("dell-e7470", {}), bitlocker="Off"))
    arm("BitLocker On -> recovery-key step; Off -> no step; unknown -> step kept",
        "BitLocker is ON" in t_on and "BitLocker" not in t_off and "couldn't tell whether BitLocker" in texts["dell-e7470"], "3 states")

    arm("Dell keys F2/F12, HP F10/F9, Gigabyte Del/F12, ASUS laptop vs desktop",
        keys(reports["dell-e7470"]) == ("F2", "F12") and keys(reports["hp-245-g8"])[0] == "F10"
        and keys(reports["x570-5800x-6600xt"]) == ("Del", "F12") and keys(reports["b660-12900kf"])[1] == "F8", "keys")
    odd = copy.deepcopy(reports["optiplex-5050-micro"])
    odd["Motherboard"]["Name"] = "ZOTAC ZBOX"
    t = render_text(build_guide(odd, {}))
    arm("an unknown vendor gets the generic key line, never another vendor's key", keys(odd) is None and "your manual names it" in t, "ZOTAC")
    try:
        build_guide({"CPU": {}}, {})
        stopped = False
    except GuideError:
        stopped = True
    arm("a scan with no motherboard stops the guide instead of guessing", stopped, "GuideError")
    touched = [m for m, r in reports.items() for st in bios_settings(r, configs.get(m, {}))
               if any(w in st.name.upper() for w in ("TPM", "PTT", "SGX"))]
    arm("no guide ever asks for a TPM/PTT/SGX change (Windows 11 + BitLocker need them)", not touched, touched or "none")
    arm("the ASUS OS-Type hint shows on ASUS boards only", "OS Type" in texts["b660-12900kf"]
        and "OS Type" not in texts["z490-vision-g"], "ASUS yes, Gigabyte no")
    arm("Secure Boot the scan saw Disabled reads 'already off'; Enabled reads 'currently Enabled'",
        all(("already off" in texts[m]) == ((r.get("BIOS") or {}).get("Secure Boot") == "Disabled") for m, r in reports.items())
        and any("currently Enabled" in t for t in texts.values()), "both states")
    pages = {}
    for m, r in reports.items():
        try:
            pages[m] = render_html(r, build_guide(r, configs.get(m, {})), "macOS Tahoe 26")
        except Exception as e:  # noqa: BLE001 - reported by the next check
            pages[m] = f"ERROR {type(e).__name__}: {e}"
    good = [m for m, pg in pages.items() if pg.startswith("<!doctype")]
    arm("the HTML page renders for every corpus machine", len(good) == len(pages), f"{len(good)}/{len(pages)}")
    ext = [m for m in good if any(x in pages[m] for x in ('src="http', 'href="http', "url(http", "@import", "<link"))]
    arm("every page is self-contained: nothing loads from the network (it has to open from the stick)",
        not ext and all(CSP in pages[m] for m in good), ext or "none, CSP on all")
    dirty = [m for m in good if leaks(pages[m])]
    planted = leaks("mail a.person@example.com, built in /Users/someone/x and C:\\Users\\someone\\x")
    arm("no page carries an email address or a user-folder path, and the check fires on planted ones",
        not dirty and len(planted) == 3, f"clean {len(good) - len(dirty)}/{len(good)}, planted {len(planted)}/3")
    hostile = copy.deepcopy(reports["dell-e7470"])
    hostile["Motherboard"]["Name"] = "DELL <script>alert(1)</script>"
    hp = render_html(hostile, build_guide(hostile, {}))
    arm("a hostile board name from the scan is escaped, never run", "<script>alert" not in hp
        and "&lt;script&gt;alert" in hp, "escaped")
    arm("every step is a page and every page shows without script (none starts hidden)",
        all(pages[m].count('<section class="pg"') == len(build_guide(reports[m], configs.get(m, {}))) for m in good)
        and not any(re.search(r'<section class="pg"[^>]*\bhidden', pages[m]) for m in good), "all")
    # The visible text should name the app and NullMoth Systems.
    shown = {m: re.sub(r"<style>.*?</style>|<script>.*?</script>|<[^>]+>", " ", pages[m], flags=re.S) for m in good}
    unnamed = [m for m in good if not ("1401 app" in shown[m] and "NullMoth Systems" in shown[m])]
    arm("the page names the app (1401) and its maker (NullMoth Systems)", not unnamed, unnamed or "all")
    bare = render_html(reports["dell-e7470"], build_guide(reports["dell-e7470"], configs.get("dell-e7470", {})), mark=b"")
    unmarked = [m for m in good if 'class="mark" src="data:image/jpeg;base64,' not in pages[m]]
    arm("every page carries the NullMoth mark from the repo by default, and the check fires on a page without it",
        not unmarked and 'class="mark"' not in bare, unmarked or "all, control fires")
    arm("vendor keys render as keycaps", "<kbd>F2</kbd>" in pages["dell-e7470"]
        and "<kbd>F12</kbd>" in pages["dell-e7470"], "Dell F2/F12")
    print(f"\n{sum(res)}/{len(res)} passed")
    return all(res)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    a = sys.argv[1:]

    def opt(name):
        return a[a.index(name) + 1] if name in a else None
    rep, cfg = load(a[0], a[1])
    mac = macos_name(opt("--macos") or "")
    steps = build_guide(rep, cfg, bitlocker=opt("--bitlocker"), macos=mac)
    if opt("--html"):
        mark = None
        if opt("--mark"):
            with open(opt("--mark"), "rb") as fh:
                mark = fh.read()
        page = render_html(rep, steps, mac, mark)
        with open(opt("--html") + ".tmp", "w", encoding="utf-8") as fh:
            fh.write(page)
        os.replace(opt("--html") + ".tmp", opt("--html"))
        print(f"wrote {opt('--html')} ({len(page):,} bytes)")
    else:
        print(render_text(steps))
