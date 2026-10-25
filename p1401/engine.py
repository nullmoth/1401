"""Runs OpCore Simplify's engine headless (upstream/OpCore-Simplify, BSD-3, pinned in upstream/PINNED.json).

The engine is an interactive console app with ~40 prompts. We don't modify it, we answer its prompts:
- Every prompt has to match a rule in PROMPT_RULES or the build stops with UnknownPrompt. An unexpected prompt
  is a question about the user's machine that nobody answered, and just pressing enter there is how people end
  up with an EFI that boots to a black screen.
- If the same prompt comes back 3 times in a row the engine didn't accept our answer, so we stop instead of looping.
- Every answer is saved as a Decision along with what the engine printed before asking, so the summary screen
  can show what was picked and a bug report has the whole transcript.
"""
import contextlib
import dataclasses
import importlib.util
import io
import copy
import hashlib
import json
import os
import stat
import time
import urllib.parse
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field

from . import amd_gpu
from . import amd_rdna4
from . import community
from . import downloads
from . import netsupport
from . import nullmoth
from . import policy as policy_mod
from . import report as report_mod
from . import validate as validate_mod

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPSTREAM = os.path.join(REPO, "upstream", "OpCore-Simplify")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
MARKER = ".1401-build"  # a folder we may wipe carries this file; any other folder is refused


class UnknownPrompt(RuntimeError):
    pass


class EngineLoop(RuntimeError):
    pass


class MacosNotOffered(RuntimeError):
    """The macOS the user picked is not on the engine's version menu for this PC."""


MACOS_NAMES = {"24": "macOS 15 Sequoia", "25": "macOS 26 Tahoe", "23": "macOS 14 Sonoma", "22": "macOS 13 Ventura"}


def macos_not_offered_message(wanted, offered):
    """offered: [(menu number, name)] as the engine printed them. Names the cap and the version to pick instead."""
    numbers = [n for n, _ in offered]
    top = max(numbers, key=int)
    top_name = "macOS " + next(name.strip() for n, name in offered if n == top)  # the menu says "macOS Sequoia 15"
    wanted_name = MACOS_NAMES.get(wanted, f"Darwin {wanted}")
    if int(wanted) > int(top):
        pick = MACOS_NAMES.get(top, top_name)
        return (f"This PC is capped at {top_name}: OpenCore-Simplify's compatibility check offers macOS versions up to "
                f"{top_name} for its hardware, and {wanted_name} is not among them. Pick {pick} in 1401 and build again.")
    low = min(numbers, key=int)
    low_name = "macOS " + next(name.strip() for n, name in offered if n == low)
    return (f"This PC needs at least {low_name}: OpenCore-Simplify's compatibility check offers macOS versions from "
            f"{low_name} up to {top_name} for its hardware, and {wanted_name} is not among them. Pick "
            f"{MACOS_NAMES.get(low, low_name)} or newer in 1401 and build again.")


def _macos_answer(prompt, ctx, pol):
    """The version menu. "" takes the engine's default, but the default is not always on the menu.
    10-07: a Broadcom card that tops out at Ventura plus a GeForce marked Sequoia-only
    left no native version; the menu offered only 23-25 (OCLP) while the default stayed "macOS Ventura 13", so the
    blank answer was refused three times. Then: Sequoia (24, the NullMoth driver's target) if listed, else the newest."""
    offered = re.findall(r"^\s*(\d+)\.\s+macOS (.+?)(?:\s+\(|$)", ctx, re.M)
    if pol.macos:
        # The user's pick (macOS 15 or 26 in the app) is not negotiable here: the app hands that same version to the
        # guide and the stick writer, and a different macOS has a different NVIDIA driver package. A menu that ends
        # below it (Haswell + GTX 1070: the engine offered up to 24 and the answer 25 was refused three times) is a fact
        # about the PC, so the build stops and says which version to pick instead of looping on a rejected answer.
        if offered and re.fullmatch(r"\d+", pol.macos) and not any(n == pol.macos for n, _ in offered):
            raise MacosNotOffered(macos_not_offered_message(pol.macos, offered))
        return pol.macos
    # A card the NullMoth driver runs has only macOS 15, but the engine's default follows its own advice: on AMD Ryzen
    # laptops "we suggest you to use only macOS Ventura 13 or older", which is on the menu and was taken as is.
    # 15 NVIDIA builds (1.x to 1.15, Ryzen 4800H/5800H/5600H, GTX 1650/1660 Ti, RTX 2060/3050 Ti/3060) installed
    # Ventura or Sonoma, where the driver does not load.
    want = pol.prefer.get("macOS")
    if want and any(n == want for n, _ in offered):
        return want
    m = re.search(r"\(default: macOS (.+?)\)", prompt)
    if not offered or (m and any(name.strip() == m.group(1).strip() for _, name in offered)):
        return ""
    nums = [n for n, _ in offered]
    return "24" if "24" in nums else max(nums, key=int)


# 10-07: the reason ("Intel VMD controllers are not supported ... disable Intel VMD in the BIOS") sat at
# the bottom of 40 lines of compatibility output. A stop the user can fix gets its fix as the first line.
STOP_LEADS = (
    ("Intel VMD", "This builder cannot continue with the reported Intel VMD controller. Open Review firmware prerequisites "
                  "on Check this PC or Build; no EFI is required. Before changing storage, back up files, save the Windows "
                  "encryption recovery key and follow the exact system vendor's storage migration procedure. Changing "
                  "mode without preparing Windows can prevent it from booting or make RAID/Optane data inaccessible. "
                  "If no safe migration is documented, stop. After migration and a normal Windows boot, run Check this PC again."),
    ("without a supported GPU", "macOS has no driver for this PC's graphics, so 1401 cannot build for it. Supported: most AMD "
                                "Radeon desktop cards up to RX 6000, Intel UHD/Iris integrated graphics up to 10th gen, and "
                                "NVIDIA GeForce RTX cards through the NullMoth driver."),
)


def stop_message(parts):
    said = ("\n".join(x for x in parts if x).strip() or "(nothing)")[-3000:]
    lead = next((fix for key, fix in STOP_LEADS if key in said), "")
    return (lead + "\n\n" if lead else "") + "OpenCore-Simplify stopped. It said:\n" + said


class EngineExit(RuntimeError):
    pass


def boot_epoch():
    """When Windows last started (seconds since the epoch), or None where that is not known."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes  # noqa: PLC0415 - Windows only
        k32 = ctypes.WinDLL("kernel32")
        k32.GetTickCount64.restype = ctypes.c_uint64
        return time.time() - k32.GetTickCount64() / 1000.0
    except (OSError, AttributeError):
        return None


# A firmware change (VMD or RAID off, Secure Boot off) needs a restart, and the restart is what makes the old report
# wrong: a build on a Report.json written before this boot still described the Intel VMD controller the user had just
# turned off, and stopped on it again. One minute of slack: boot time is derived from the uptime counter.
STALE_SCAN_SLACK = 60


def stale_scan_message(report_path, booted=None):
    """A message when the hardware report predates this Windows session, else None. booted is an injectable epoch."""
    booted = boot_epoch() if booted is None else booted
    if booted is None:
        return None
    try:
        written = os.path.getmtime(report_path)
    except OSError:
        return None
    if written >= booted - STALE_SCAN_SLACK:
        return None
    fmt = lambda t: time.strftime("%Y-%m-%d %H:%M", time.localtime(t))  # noqa: E731
    return (f"This PC was checked before its last restart (report written {fmt(written)}, Windows started "
            f"{fmt(booted)}). Firmware settings may have changed since, so that report cannot be built from. "
            "Run Check this PC again, then Build.")


@dataclass
class Policy:
    """The choices a beginner never has to make. Each default says why."""
    macos: str = ""                 # "" = the engine's suggested (newest stable the hardware supports)
    # Tahoe dropped AppleHDA. AppleALC needs the OCLP AppleHDA rollback, which means SIP and AMFI off.
    # VoodooHDA sounds a bit worse but leaves both on, so it's the default.
    tahoe_audio: str = "voodoohda"  # or "applealc"
    # OpCore Simplify can copy every saved Windows Wi-Fi password into the EFI, in plaintext. Off unless the
    # user turns it on.
    import_wifi_passwords: bool = False
    force_load_unsupported_kexts: bool = False
    boot_logo: bool = False          # the NullMoth boot logo driver in the EFI (policy.py rule 6)
    # Filled by 1401's pre-pass, never by the user: device kind ("WiFi") -> the device name 1401 picked.
    prefer: dict = field(default_factory=dict)
    # The stick's opencore-*.txt from a failed boot: bootfix.py changes the next build from what it shows.
    boot_logs: list = field(default_factory=list)
    # The line the screen stopped on, as the user typed or pasted it when sending logs (bootfix.after_handoff).
    stopped_at: str = ""
    # A rebuild keeps the previous build's serial number (_keep_identity). The user asks for a new one when that serial
    # is the problem: macOS Setup saying "this Mac belongs to an organization" (the generated serial matches a Mac
    # enrolled in a company's device management; chat 10-14), or Apple refusing it for iMessage.
    new_identity: bool = False
    # The experimental community drivers (AMD RDNA 4 display, MediaTek Wi-Fi) are OFF unless the user turns them on.
    # They are unproven on the hardware they claim, so a build that silently carried them could take a machine that
    # installs fine on the firmware framebuffer and leave it with no picture. Off, the build still says they exist.
    experimental_drivers: bool = False
    # Persistent NVRAM on AMD guard boards, through OpenCore's emulated NVRAM (OpenVariableRuntimeDxe + a LogoutHook that
    # saves NVRAM to nvram.plist at shutdown). Off by default: the DisableVariableWrite guard exists because real AM5/AM4
    # boards stopped POSTing after macOS wrote firmware NVRAM, and emulated NVRAM replaces that guard (writes go to an
    # in-memory store and a file on the ESP, never the fragile firmware flash), so it is proven on a real AMD board
    # through testers before it becomes the default. On, the guard boards keep iMessage, Apple ID and the startup-disk
    # choice across reboots instead of losing every NVRAM write.
    persistent_nvram_amd: bool = False


@dataclass
class Decision:
    prompt: str
    answer: str
    context: str  # what the engine printed right before asking


@dataclass
class BuildResult:
    ok: bool
    out_dir: str
    macos_version: str = ""
    smbios: str = ""
    needs_oclp: bool = False
    disabled_devices: dict = field(default_factory=dict)
    bios_requirements: list = field(default_factory=list)
    kexts: list = field(default_factory=list)
    decisions: list = field(default_factory=list)
    notices: list = field(default_factory=list)
    error: str = ""
    failure_frames: list = field(default_factory=list)
    transcript: str = ""
    hardware: dict = field(default_factory=dict)
    # The scan exactly as Check this PC wrote it, kept apart from `hardware`, which the compatibility pass replaces
    # with its own view (unsupported devices removed). A failure after that pass must still log the raw device IDs.
    raw_hardware: dict = field(default_factory=dict)
    report_sha256: str = ""
    # measured CPU topology + NVIDIA compute facts (p1401/hwcapture.py); collected on success and failure alike
    capture: dict = field(default_factory=dict)
    acpi_diagnostics: list = field(default_factory=list)
    acpi_fingerprints: list = field(default_factory=list)
    policy_changes: list = field(default_factory=list)
    validation: dict = field(default_factory=dict)


def _choose_last(prompt, ctx, policy):
    # "Select a GPU combination (1-N)": the engine sorts combos by (device count, newest macOS) ascending,
    # so the last one keeps the most working hardware.
    m = re.search(r"\((\d+)-(\d+)\)", prompt)
    return m.group(2)


def _choose_device(prompt, ctx, policy):
    # "Select a WiFi device (1-N)": answer with the device 1401's pre-pass chose, looked up by name in the list the
    # engine just printed. No preference means the engine's first listed device.
    kind = re.match(r"^Select a (.+?) device", prompt).group(1)
    want = policy.prefer.get(kind)
    if not want:
        return "1"
    for line in ctx.splitlines():
        m = re.match(r"^\s*(\d+)\. (.+?)\s*$", line)
        if m and m.group(2) == want:
            return m.group(1)
    raise UnknownPrompt(f"1401 chose {want!r} as the {kind} device but the engine did not list it:\n{ctx}")


# (pattern on the prompt, answer or fn(prompt, context, policy)) - first match wins.
PROMPT_RULES = [
    (r"^Press Enter", ""),
    (r"^Build EFI for UEFI\?", "yes"),
    (r"^Please enter the macOS version", lambda p, c, pol: _macos_answer(p, c, pol)),
    (r"^Select audio kext for your system", lambda p, c, pol: "1" if pol.tahoe_audio == "applealc" else "2"),
    (r"^Select kext for your AMD .* GPU \(default", ""),
    (r"^Select kext for your Intel WiFi device \(default", ""),
    (r"^Do you want to force load", lambda p, c, pol: "yes" if pol.force_load_unsupported_kexts else "no"),
    (r"^Would you like to scan for WiFi profiles", lambda p, c, pol: "yes" if pol.import_wifi_passwords else "no"),
    (r"^Enter the ID of the codec layout", ""),
    (r"^Select a .* combination \(\d+-\d+\)", _choose_last),
    (r"^Select a .* device \(\d+-\d+\)", _choose_device),
]


class _Tee(io.TextIOBase):
    def __init__(self, echo):
        self.buf, self.echo = io.StringIO(), echo

    def write(self, s):
        self.buf.write(s)
        if self.echo:
            sys.__stdout__.write(s)
        return len(s)

    def text(self):
        return ANSI.sub("", self.buf.getvalue())


class Headless:
    """Patches the engine's Utils so it can run without a console, and records the conversation."""

    def __init__(self, utils_mod, policy, echo=False):
        self.U, self.policy, self.echo = utils_mod.Utils, policy, echo
        self.decisions, self.notices = [], []
        self._saved, self._last, self._repeat, self._mark = {}, None, 0, 0

    def _context(self):
        text = self.tee.text()
        ctx = text[self._mark:]
        self._mark = len(text)
        return "\n".join(l for l in ctx.strip().splitlines()[-60:] if l.strip())

    def request_input(self, _self, prompt="Press Enter to continue..."):
        p = ANSI.sub("", prompt).strip()
        ctx = self._context()
        self._repeat = self._repeat + 1 if p == self._last else 1
        self._last = p
        if re.search(r"drag and drop ACPI Tables", p):
            # OpenCore-Simplify reached this only because it could not read the dump we passed (no table passed its check,
            # two tables carry a DSDT signature, or iasl could not disassemble the DSDT). It printed the reason before a
            # bare "press Enter" we already answered, so that text is in the notices, not in ctx. (10-07: users saw only
            # "The engine had just printed: ...".)
            why = "\n".join(n for n in self.notices[-3:] + [ctx] if n).strip() or "(it printed nothing)"
            raise RuntimeError("OpenCore-Simplify could not read this PC's ACPI tables. It said:\n" + why[-3000:])
        if self._repeat >= 3:
            raise EngineLoop(f"engine re-asked {p!r} {self._repeat}x - our answer was rejected.\n{ctx}")
        for pat, ans in PROMPT_RULES:
            if re.search(pat, p):
                a = ans(p, ctx, self.policy) if callable(ans) else ans
                if pat == r"^Press Enter":
                    if ctx:
                        self.notices.append(ctx)
                else:
                    self.decisions.append(Decision(p, a, ctx))
                self.tee.write(f"{prompt}{a}\n")
                return a
        raise UnknownPrompt(f"no rule answers {p!r}. The engine had just printed:\n{ctx}")

    def __enter__(self):
        h = self
        patches = {
            "request_input": lambda s, prompt="Press Enter to continue...": h.request_input(s, prompt),
            "head": lambda s, text=None, width=68, resize=True: print(f"\n== {text or ''}"),
            "adjust_window_size": lambda s, *a, **k: None,
            "open_folder": lambda s, *a, **k: None,
            # OpenCore-Simplify prints why before it quits (no supported GPU, missing SSE4, no storage ...); keep that text.
            # (10-07: a laptop user saw only "engine asked to exit".)
            "exit_program": lambda s, *a, **k: (_ for _ in ()).throw(EngineExit(stop_message(h.notices[-3:] + [h._context()]))),
            "progress_bar": lambda s, title, steps, i, done=False: print(
                f"[{title}] {'done' if done else steps[i] if i < len(steps) else ''}"),
        }
        for k, fn in patches.items():
            self._saved[k] = getattr(self.U, k, None)
            setattr(self.U, k, fn)
        self.tee = _Tee(self.echo)
        self._redirect = contextlib.redirect_stdout(self.tee)
        self._redirect.__enter__()
        return self

    def __exit__(self, *exc):
        self._redirect.__exit__(*exc)
        for k, fn in self._saved.items():
            setattr(self.U, k, fn)
        return False


def _load_engine():
    if UPSTREAM not in sys.path:
        sys.path.insert(0, UPSTREAM)
    from Scripts import utils as utils_mod  # noqa: PLC0415 - only importable once UPSTREAM is on the path
    spec = importlib.util.spec_from_file_location("ocs_main", os.path.join(UPSTREAM, "OpCore-Simplify.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _patient_downloads()
    _dsdt_signature_fix()
    _unsupported_igpu_fix()
    from . import tls  # noqa: PLC0415
    tls.install()   # verify against the Windows store + certifi, not certifi alone
    return mod, utils_mod


def _unsupported_igpu_fix():
    """1.10.0 build log (10-10, Intel Iris Xe laptop): "KeyError: 'PciRoot(0x0)/Pci(0x2,0x0)'". For an Intel iGPU macOS has
    no driver for, the engine's igpu_properties returns no properties, its add_device_property then adds nothing (as
    intended), and the very next line indexes that missing entry. The iGPU entry is left out of the device-properties
    pass instead: the result is the one the engine meant (no properties for that GPU) and every other device is untouched."""
    from Scripts import config_prodigy  # noqa: PLC0415 - upstream module
    cls = config_prodigy.ConfigProdigy
    if getattr(cls, "_1401_igpu", False):
        return
    orig = cls.deviceproperties

    def deviceproperties(self, hardware_report, disabled_devices, macos_version, kexts):
        gpus = hardware_report.get("GPU", {}) or {}
        board = hardware_report.get("Motherboard", {}) or {}
        platform = "NUC" if "NUC" in (board.get("Name") or "") else board.get("Platform")
        empty = []
        for name, info in gpus.items():
            if info.get("Device Type") != "Integrated GPU" or "Intel" not in (info.get("Manufacturer") or ""):
                continue
            try:
                props = self.igpu_properties(platform, (name, info), hardware_report.get("Monitor", {}), macos_version)
            except Exception:  # noqa: BLE001 - the engine's own call below raises the real error if this one does
                continue
            if not props:
                empty.append(name)
        if empty:
            print(f"(no macOS properties for {', '.join(empty)}: left out of device properties)")
            hardware_report = dict(hardware_report, GPU={k: v for k, v in gpus.items() if k not in empty})
        return orig(self, hardware_report, disabled_devices, macos_version, kexts)
    cls.deviceproperties = deviceproperties
    cls._1401_igpu = True


class _Sig(bytes):
    """Bytes that also equal the same text: b"DSDT" == "DSDT" is True for this type."""
    def __eq__(self, other):
        return bytes.__eq__(self, other.encode("latin-1")) if isinstance(other, str) else bytes.__eq__(self, other)

    def __ne__(self, other):
        return not self.__eq__(other)

    __hash__ = bytes.__hash__


def _dsdt_signature_fix():
    """10-07 (an uploaded log: "Failed to load tables ... - dsdt.aml"): the engine reads a table's signature
    as bytes (b"DSDT") but acpi_guru compares it to the str "DSDT", which is never equal in Python 3. So it never finds
    the DSDT up front and its pre-patch path - the known patches that let iasl disassemble a DSDT it chokes on - never
    runs; the DSDT then fails in the bulk load and the build stops at "drag and drop ACPI Tables". Returning a bytes
    value that also equals the str restores the engine's intended path without changing any other comparison."""
    from Scripts import dsdt  # noqa: PLC0415 - upstream module
    cls = dsdt.DSDT
    if getattr(cls, "_1401_sig", False):
        return
    orig = cls._table_signature

    def table_signature(self, table_path, table_name=None):
        sig = orig(self, table_path, table_name=table_name)
        return _Sig(sig) if isinstance(sig, bytes) else sig
    cls._table_signature = table_signature
    cls._1401_sig = True


def network_help(url):
    host = urllib.parse.urlsplit(url).hostname or url
    return (f"1401 could not reach {host} (tried several times). The build downloads OpenCore and its drivers from GitHub, "
            "and this network blocks or resets those connections - common in mainland China and on some school or work "
            "networks. Turn on a VPN, or a proxy set in Windows (Settings > Network & internet > Proxy - 1401 uses it), "
            "then build again.")


# 10-07 (PermissionError in ...\Downloads\Compressed\1401\...\OCK_Files, missing
# efi\manifest.json): the engine keeps its downloads in OCK_Files beside its own code, so it rewrote files inside the
# folder the user unpacked - which can be read-only or watched by antivirus - and 1.0.0-1.0.6 even shipped a stale copy of
# that cache. On Windows it now lives in the user's writable app-data folder; the zip ships none.
OCK_CACHE = (os.path.join(os.environ["LOCALAPPDATA"], "NullMoth", "1401", "OCK_Files") if os.environ.get("LOCALAPPDATA")
             else os.path.join(REPO, "upstream", "OpCore-Simplify", "OCK_Files"))


def _use_ock_cache(o):
    os.makedirs(OCK_CACHE, exist_ok=True)
    o.o.ock_files_dir = OCK_CACHE
    o.o.download_history_file = os.path.join(OCK_CACHE, "history.json")
    if hasattr(o.o, 'integrity_checker'):
        from . import dependency_cache
        dependency_cache.harden(o.o.integrity_checker)
        dependency_cache.tolerate_cache_locks(o.o.utils, OCK_CACHE)
    o.k.ock_files_dir = OCK_CACHE




def _opencore_debug(gathering_files):
    """The stick boots OpenCore's DEBUG build (same release, Dortania's own DEBUG zip and SHA-256). A failed boot then
    leaves a log that names why: the MMIO regions behind "StartImage failed - Aborted" (26 stick logs in one day, AM5
    boards, fixed by hand with board-specific MmioWhitelist entries), memory-map and quirk decisions the RELEASE build
    does not print. Dortania's troubleshooting guide asks for the DEBUG build for the same reason. RELEASE stays the
    fallback when the index has no DEBUG link or hash."""
    if getattr(gathering_files, "_1401_oc_debug", False):
        return
    cls = gathering_files.gatheringFiles
    original = cls.fetch_latest_products_info

    def fetch_latest_products_info(self, kexts, local_download_history):
        products = original(self, kexts, local_download_history)
        try:
            v = self.fetcher.fetch_and_parse_content(self.dortania_builds_url, "json")["OpenCorePkg"]["versions"][0]
            url, sha = v["links"]["debug"], v["hashes"]["debug"]["sha256"]
        except (TypeError, KeyError, IndexError, ValueError):
            print("OpenCore DEBUG build not listed; using RELEASE.")
            return products
        if isinstance(url, str) and url.startswith("https://") and url.endswith("-DEBUG.zip") and isinstance(sha, str) and len(sha) == 64:
            oc = products.get("OpenCorePkg") or {}
            oc.update({"url": url, "sha256": sha, "id": str(oc.get("id", "")) + "-debug"})
            products["OpenCorePkg"] = oc
        return products
    cls.fetch_latest_products_info = fetch_latest_products_info
    gathering_files._1401_oc_debug = True

def _keep_first_kext(gathering_files):
    """The engine empties a product's folder, then moves every kext it extracted into it. A release that holds two
    kexts with the same name in different folders made the second move fail on Windows (WinError 183, itlwm.kext,
    1401 1.0.24), which stopped the whole build; on macOS the same move silently nests one kext inside the other.
    Keep the first copy and say so; nothing that was already there before this download can be in that folder."""
    if getattr(gathering_files, "_1401_keep_first", False):
        return
    import shutil as real  # noqa: PLC0415

    class _Shutil:
        def __getattr__(self, name):
            return getattr(real, name)

        @staticmethod
        def move(src, dst, *a, **kw):
            if str(dst).lower().endswith(".kext") and os.path.exists(dst):
                print(f"Two copies of {os.path.basename(dst)} in one download; keeping the first.")
                return dst
            return real.move(src, dst, *a, **kw)
    gathering_files.shutil = _Shutil()
    gathering_files._1401_keep_first = True

def _patient_downloads():
    """Retry transient downloads without multiplying upstream retry loops."""
    from Scripts import resource_fetcher as rf
    from Scripts import gathering_files
    from . import kernel_patches
    from .downloads import make_request, verified_context
    kernel_patches.harden(gathering_files.gatheringFiles)
    _keep_first_kext(gathering_files)
    _opencore_debug(gathering_files)
    cls = rf.ResourceFetcher
    if getattr(cls, "_1401_patient", False):
        return
    cls.create_ssl_context = verified_context
    cls._make_request = make_request
    # 10-07: "TimeoutError: The read operation timed out" while gathering OpenCore and
    # kexts. The connection opened; the stall came mid-body in response.read(), which the engine never retries, so one
    # slow chunk killed the build. Each whole download/fetch now gets 4 tries with the same growing pause.
    import http.client, socket, urllib.error  # noqa: E401,PLC0415

    def _retry(fn):
        def run(self, *a, **kw):
            for attempt in range(4):
                try:
                    return fn(self, *a, **kw)
                except (TimeoutError, socket.timeout, ConnectionError, http.client.IncompleteRead, urllib.error.URLError):
                    if attempt == 3:
                        raise
                    print(f"Download stalled ({a[0] if a else ''}); retrying in {2 ** (attempt + 1)} s...")
                    time.sleep(2 ** (attempt + 1))
        return run
    from . import archive_download
    dl = _retry(archive_download.harden(cls.download_and_save_file))

    def download_and_save_file(self, resource_url, destination_path, sha256_hash=None):
        ok = dl(self, resource_url, destination_path, sha256_hash)
        # 10-07: the validator downloaded OpenCorePkg a SECOND time after the
        # engine had just fetched and checked it, and on slow or filtered networks that second download is what failed.
        # Keep the engine's checked zip where the validator looks (it re-checks the SHA-256 before using it).
        if ok and sha256_hash and os.path.basename(resource_url).startswith("OpenCore-") and resource_url.endswith(".zip"):
            from . import validate  # noqa: PLC0415
            try:
                os.makedirs(validate.CACHE, exist_ok=True)
                shutil.copyfile(destination_path, os.path.join(validate.CACHE, os.path.basename(resource_url)))
            except OSError as e:
                print(f"(could not keep {os.path.basename(resource_url)} for the validator: {e})")
        return ok
    cls.download_and_save_file = download_and_save_file
    fetch = _retry(cls.fetch_and_parse_content)

    def fetch_and_parse_content(self, resource_url, content_type=None):
        got = fetch(self, resource_url, content_type)
        # 10-07: raw.githubusercontent.com reset every connection (WinError 10054/10060,
        # mainland China); the engine got None back and died on "argument of type 'NoneType' is not iterable".
        if got is None:
            raise RuntimeError(network_help(resource_url))
        return got
    cls.fetch_and_parse_content = fetch_and_parse_content
    cls._1401_patient = True


# Bug report 10-14: every Build ran macserial again, so rebuilding a PC's EFI (to recover from a failed driver update)
# gave its Mac a new serial number, board serial, UUID and ROM - a different Mac to iCloud, iMessage and the App Store.
# A rebuild for the same PC and the same Mac model keeps the previous build's identity.
IDENTITY_KEYS = ("SystemSerialNumber", "MLB", "SystemUUID", "ROM")
IDENTITY_FOR = ".1401-identity-for"  # which PC the build folder's identity belongs to (board and CPU, hashed)
PLACEHOLDER_SERIALS = ("A" + "0" * 10 + "9", "A" + "0" * 15 + "Z")  # the engine's values when macserial fails


def _machine_key(raw_hardware):
    board = ((raw_hardware or {}).get("Motherboard") or {}).get("Name") or ""
    cpu = ((raw_hardware or {}).get("CPU") or {}).get("Processor Name") or ""
    if not board.strip() or not cpu.strip():
        return ""
    return hashlib.sha256(f"{board.strip()}\n{cpu.strip()}".encode()).hexdigest()


def _prior_identity(out_dir, machine_key):
    """The SMBIOS identity of this PC's previous 1401 build, read before the folder is wiped. None when there is no
    previous build, it was made for another PC, or its values are unusable."""
    import plistlib  # noqa: PLC0415
    if not os.path.exists(os.path.join(out_dir, MARKER)):
        return None
    try:
        with open(os.path.join(out_dir, IDENTITY_FOR)) as f:
            if f.read().strip() != machine_key:
                return None
    except FileNotFoundError:
        pass  # builds before this file existed were made by this PC's own scan, like every build
    except OSError:
        return None
    try:
        with open(os.path.join(out_dir, "EFI", "OC", "config.plist"), "rb") as f:
            generic = plistlib.load(f)["PlatformInfo"]["Generic"]
    except (OSError, ValueError, KeyError, TypeError, plistlib.InvalidFileException):
        return None
    ident = {k: generic.get(k) for k in IDENTITY_KEYS + ("SystemProductName",)}
    if not all(ident.values()) or ident["SystemSerialNumber"] in PLACEHOLDER_SERIALS or ident["MLB"] in PLACEHOLDER_SERIALS:
        return None
    return ident


def _identity_to_keep(out_dir, machine_key, policy, h):
    """The previous build's identity to carry over, or None when there is none or the user asked for a new serial."""
    if policy.new_identity:
        h.notices.append("SMBIOS: a new serial number, board serial, UUID and ROM, as asked; sign in to iCloud again "
                         "after installing this build.")
        return None
    return _prior_identity(out_dir, machine_key)


def _keep_identity(out_dir, prior, machine_key, h):
    """Puts the previous build's identity into the new config when the Mac model is unchanged, and records the PC."""
    import plistlib  # noqa: PLC0415
    if machine_key:
        with open(os.path.join(out_dir, IDENTITY_FOR), "w") as f:
            f.write(machine_key + "\n")
    if not prior:
        return
    path = os.path.join(out_dir, "EFI", "OC", "config.plist")
    with open(path, "rb") as f:
        cfg = plistlib.load(f)
    generic = cfg["PlatformInfo"]["Generic"]
    if generic.get("SystemProductName") != prior["SystemProductName"]:
        h.notices.append(f"SMBIOS: the Mac model changed ({prior['SystemProductName']} to {generic.get('SystemProductName')}), "
                         "so this build has a new serial number; sign in to iCloud again after installing it.")
        return
    for k in IDENTITY_KEYS:
        generic[k] = prior[k]
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        plistlib.dump(cfg, f)
    os.replace(tmp, path)
    h.notices.append("SMBIOS: kept the serial number, board serial, UUID and ROM of this PC's previous build, so macOS "
                     "and iCloud still see the same Mac.")


APP_BUILD_DIR = ("nullmoth", "1401", "efi")  # the app's own build folder, under the user's local app data
LEFTOVER_TOP = {"EFI", "manifest.json", MARKER, IDENTITY_FOR}  # all an upstream build leaves at the top


def _adopt_leftover_build(out_dir):
    """A build that stopped inside the upstream step (before this fix) left the app's build folder without its marker.
    Only the app's own folder is adopted, and only when it holds nothing but an upstream build; any other folder is
    still refused, so a folder of the user's own is never wiped."""
    parts = tuple(p.lower() for p in os.path.normpath(out_dir).replace("\\", "/").split("/")[-3:])
    if parts != APP_BUILD_DIR or not os.path.isdir(out_dir) or os.path.exists(os.path.join(out_dir, MARKER)):
        return False
    top = set(os.listdir(out_dir))
    if not top or not top <= LEFTOVER_TOP or not os.path.isdir(os.path.join(out_dir, "EFI", "OC")):
        return False
    open(os.path.join(out_dir, MARKER), "w").write("built by 1401\n")
    return True


def _prepare_out(out_dir):
    """The engine wipes its result dir. Only ever hand it a folder that is empty or one we made."""
    out_dir = os.path.abspath(out_dir)
    if os.path.exists(out_dir) and os.listdir(out_dir) and not os.path.exists(os.path.join(out_dir, MARKER)):
        raise RuntimeError(f"refusing to build into {out_dir}: not empty and not a 1401 build folder")
    if os.path.exists(os.path.join(out_dir, MARKER)):
        # a second Build failed "Access is denied: ...EFI\\OC\\ACPI" because Windows leaves the old build's
        # folders ReadOnly and the upstream cleanup can't delete them. Our own previous build: clear the flag, wipe it.
        # 10-07: the wipe stopped with FileNotFoundError on ...\EFI\OC\Drivers\UefiPxeBcDxe.efi - the
        # file was gone by the time this handler ran (an antivirus scan or the engine's own cleanup), and chmod on a
        # missing path raised. A file that is already gone is what the wipe wanted.
        def _force(fn, path, _exc):
            if not os.path.lexists(path):
                return
            try:
                os.chmod(path, stat.S_IWRITE)
                fn(path)
            except FileNotFoundError:
                pass
        shutil.rmtree(out_dir, onerror=_force)
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def _wifi_prepass(hw, policy, h, o):
    """The engine caps macOS at what the oldest Wi-Fi card supports, then keeps only one card anyway, so with two
    cards the weaker one decides for the whole machine. The trx40 report (Broadcom 14E4-43A0, max Ventura, next to
    an Intel AX200 that runs Tahoe) got offered Ventura, which doesn't even get security updates anymore.
    So pick the card with the newest native support first (ties keep the engine's order), show the engine only
    that card when it suggests a version, and give it the same card when it asks which Wi-Fi to use.
    Returns the hardware dict to suggest from."""
    from Scripts.datasets import pci_data  # noqa: PLC0415 - importable once the engine is loaded
    net = hw.get("Network") or {}
    wifi = [n for n, p in net.items() if p.get("Device ID") in pci_data.WirelessCardIDs
            and (p.get("Compatibility") or (None, None))[0]]
    if len(wifi) < 2:
        return hw
    best = max(wifi, key=lambda n: o.u.parse_darwin_version(net[n]["Compatibility"][0]))
    policy.prefer["WiFi"] = best
    h.notices.append(f"{len(wifi)} Wi-Fi cards found; 1401 uses {best!r} (newest macOS natively) and leaves "
                     + ", ".join(repr(n) for n in wifi if n != best) + " off.")
    return {**hw, "Network": {n: p for n, p in net.items() if n not in wifi or n == best}}


def _oclp_still_needed(cust, flagged, h):
    """hardware_customization sets needs_oclp for any OCLP-capable device, then disables the devices that weren't
    picked without clearing the flag. trx40 (Broadcom disabled, AX200 picked) ended up with AMFIPass, so AMFI was
    bypassed for a card that's turned off. Recompute it from what's still enabled. AppleALC on Tahoe still sets
    it later in select_required_kexts, which is right since the user chose that."""
    left = [n for sect in cust.values() if isinstance(sect, dict)
            for n, p in sect.items() if isinstance(p, dict) and p.get("OCLP Compatibility")]
    if flagged and not left:
        h.notices.append("OpenCore Legacy Patcher is not needed: the only device that needed it is disabled.")
    return bool(left)


def _nullmoth_amfipass(o, hw, mv, h):
    """The NullMoth driver needs AMFIPass (with Lilu) so WindowServer can load it. The engine picks AMFIPass only for OCLP
    Wi-Fi, so EFIs rebuilt for the driver lacked it and the driver's Mac setup 1.10 stopped on them (10-10, 9 uploads)."""
    if not nullmoth.cards(hw):
        return False
    from Scripts.datasets import kext_data  # noqa: PLC0415 - importable once the engine is loaded
    if o.k.check_kext(kext_data.kext_index_by_name.get("AMFIPass"), mv):
        return True
    h.notices.append("AMFIPass could not be selected for this macOS version; the NVIDIA driver's Mac setup adds it.")
    return False


def _nullmoth_gpu_pass(checker, h):
    """Runs the engine's GPU check, then gives cards the NullMoth driver supports macOS 15 (nullmoth.mark). A machine
    whose only GPU is such a card made the engine exit; with the card marked it builds."""
    orig = checker.check_gpu_compatibility

    def wrapped():
        try:
            orig()
            exited = None
        except EngineExit as e:
            exited = e
        hit = nullmoth.mark(checker.hardware_report)
        # Per-AMD-GPU notice (family -> the macOS path it gets), independent of the NVIDIA path above. It names the
        # card so the user sees before building whether this AMD GPU gets full acceleration, basic display with an
        # opt-in/experimental route, or no driver at all.
        gpus = checker.hardware_report.get("GPU", {})
        # Navi 48 cards are described in full by the RDNA 4 display-driver pass (amd_rdna4), so skip them here.
        amd_notes = amd_gpu.notes(checker.hardware_report, skip_ids=amd_rdna4.NAVI48_IDS)
        h.notices.extend(amd_notes)
        if not hit:
            basic = nullmoth.basic_display(checker.hardware_report) if exited else None
            if not basic:
                if exited:
                    raise exited
                return
            checker._restrict_native_compatibility(checker._widest_compatibility(g.get("Compatibility") for g in gpus.values()))
            # The AMD notice for this card is more specific than the generic BASIC_NOTE, so skip the generic one when
            # the card kept on the firmware framebuffer is the AMD GPU already described above.
            if amd_gpu.classify(gpus.get(basic, {})) is None:
                h.notices.append(nullmoth.BASIC_NOTE.format(name=basic))
            return
        h.policy.prefer["macOS"] = h.policy.macos or nullmoth.DEFAULT_DARWIN
        mux = nullmoth.mux_help(checker.hardware_report)
        if mux:
            h.notices.append(mux)
        checker._restrict_native_compatibility(checker._widest_compatibility(g.get("Compatibility") for g in gpus.values()))
        target = "macOS 26 Tahoe" if h.policy.prefer["macOS"] == "25" else "macOS 15 Sequoia"
        h.notices.append("NullMoth driver: " + ", ".join(hit) + f" selected for {target}."
                         + ("" if nullmoth.tested(checker.hardware_report) else
                            " This card is in NVIDIA's supported list but has not been tested with the driver yet."))
    checker.check_gpu_compatibility = wrapped


def build(report_path, acpi_dir, out_dir, policy=None, echo=False, download=True):
    """Report.json + ACPI dump -> OpenCore EFI in out_dir. download=False stops after planning (no network)."""
    policy = policy or Policy()
    policy = dataclasses.replace(policy, prefer=dict(policy.prefer))  # the Wi-Fi pre-pass writes to prefer
    out_dir = os.path.abspath(out_dir)
    _adopt_leftover_build(out_dir)
    if os.path.exists(out_dir) and os.listdir(out_dir) and not os.path.exists(os.path.join(out_dir, MARKER)):
        raise RuntimeError("refusing to build into an unowned nonempty folder")
    scratch = tempfile.mkdtemp(prefix="1401-report-")
    res = BuildResult(ok=False, out_dir=out_dir)
    h = None
    try:
        mod, utils_mod = _load_engine()
        h = Headless(utils_mod, policy, echo)
        try:
            netsupport.register()   # MediaTek Wi-Fi/BT device IDs + kexts upstream does not carry
        except Exception as e:  # noqa: BLE001 - a networking add-on must never stop a build from starting
            h.notices.append(f"MediaTek support not loaded: {type(e).__name__}: {e}")
        try:
            amd_rdna4.register()    # the RDNA 4 (RX 9070) community display driver, built and mirrored by us
        except Exception as e:  # noqa: BLE001 - a GPU add-on must never stop a build from starting
            h.notices.append(f"AMD RDNA 4 support not loaded: {type(e).__name__}: {e}")
        try:
            community.register()    # pinned community drivers for hardware the engine has none for (community.py)
        except Exception as e:  # noqa: BLE001 - an add-on must never stop a build from starting
            h.notices.append(f"Community drivers not loaded: {type(e).__name__}: {e}")
        with h:
            # 10-07: Build ran with no Report.json and failed with a bare FileNotFoundError.
            if not os.path.isfile(report_path):
                raise RuntimeError("This PC has not been checked yet (no hardware report). Run Check this PC first and wait for it "
                                   "to finish; if it stops with an error, send that log instead.")
            stale = stale_scan_message(report_path)
            if stale:
                raise RuntimeError(stale)
            with open(report_path, "rb") as report_file:
                raw = report_file.read(16 * 1024 * 1024 + 1)
            if len(raw) > 16 * 1024 * 1024:
                raise RuntimeError("The hardware report exceeded its bounded size. Run Check this PC again.")
            res.report_sha256 = hashlib.sha256(raw).hexdigest()
            res.hardware = json.loads(raw.decode("utf-8"))
            if not isinstance(res.hardware, dict):
                raise RuntimeError("The hardware report must contain a JSON object. Run Check this PC again.")
            res.raw_hardware = copy.deepcopy(res.hardware)
            if not os.path.isdir(acpi_dir) or not os.listdir(acpi_dir):
                raise RuntimeError("Check this PC did not save the ACPI tables. Run Check this PC again (as administrator).")
            res.acpi_fingerprints = report_mod.acpi_fingerprints(acpi_dir)
            rpath, norm_notes = report_mod.normalized_copy(os.path.abspath(report_path), scratch, raw_hardware=res.raw_hardware)
            h.notices += norm_notes
            o = mod.OCPE()
            o.result_dir = out_dir
            _use_ock_cache(o)
            valid, errors, warnings, report = o.v.validate_report(rpath)
            if not valid or errors:
                raise RuntimeError(f"hardware report rejected: {errors}")
            res.hardware = report
            o.ac.dsdt = o.ac.acpi.acpi_tables = None
            from . import acpi_diagnostics, acpi_dupnames
            with acpi_diagnostics.capture(o.ac.acpi, res.acpi_diagnostics), \
                    acpi_dupnames.tolerate(o.ac.acpi, res.acpi_diagnostics):
                o.ac.read_acpi_tables(os.path.abspath(acpi_dir))
            if not o.ac.ensure_dsdt():
                raise RuntimeError(f"no usable DSDT in {acpi_dir} - the ACPI dump is required")
            _nullmoth_gpu_pass(o.c, h)
            hw, native, oclp_versions = o.c.check_compatibility(report)
            res.hardware = hw
            mv = o.select_macos_version(_wifi_prepass(hw, policy, h, o), native, oclp_versions)
            cust, disabled, needs_oclp = o.h.hardware_customization(hw, mv)
            from . import panel_guard, scan_evidence
            capture = scan_evidence.load_for_report(report_path, res.raw_hardware, expected_report_sha256=res.report_sha256)
            keep = panel_guard.intel_panel_keys(disabled, capture)
            for k in keep:   # the panel's own GPU stays on (no disable-gpu), so the built-in screen has a display in macOS
                h.notices.append(panel_guard.KEEP_NOTE.format(dev=disabled[k].get("Device ID")))
                disabled = {kk: vv for kk, vv in disabled.items() if kk != k}
            panel = None if keep else panel_guard.active_panel_notice(disabled, capture)
            if panel:
                h.notices.append(panel)
            machine_key = _machine_key(res.raw_hardware)
            prior_identity = _identity_to_keep(out_dir, machine_key, policy, h)
            _prepare_out(out_dir)  # Preserve prior EFI on an output-safety refusal.
            needs_oclp = _oclp_still_needed(cust, needs_oclp, h)
            smbios = o.s.select_smbios_model(cust, mv)
            # macOS 26 dropped iMacPro1,1, which the engine picks for a discrete-GPU desktop on macOS 15; that PC then stops
            # at Apple's "not supported on this platform" (Mac-7BA5B2D9E42DDD94, 1.9 stick log 10-10) the day it takes
            # macOS 26. MacPro7,1 runs both and is what the engine picks for 26 itself; its options (RestrictEvents) follow.
            if smbios == "iMacPro1,1":
                smbios = "MacPro7,1"
                h.notices.append("SMBIOS: MacPro7,1 - it runs macOS 15 and macOS 26 (iMacPro1,1 does not run macOS 26).")
            o.ac.select_acpi_patches(cust, disabled)
            needs_oclp = o.k.select_required_kexts(cust, mv, needs_oclp, o.ac.patches)
            netsupport.apply_kexts(o, cust, mv, h.notices, experimental=policy.experimental_drivers)   # MediaTek Wi-Fi/BT, if this machine has one and the user opted in
            amd_rdna4.apply_kexts(o, cust, mv, h.notices, experimental=policy.experimental_drivers)    # RX 9070 display driver, same opt-in
            community.apply_kexts(o, cust, mv, h.notices, experimental=policy.experimental_drivers)    # Realtek/Qualcomm Wi-Fi, BT, input, USB fixes
            net_status = netsupport.support_from_pci(cust, h.notices)  # warn if the installer will have no internet
            # Kexts under the ChefKiss licence are never downloaded or shipped (policy.EXCLUDED_KEXTS; the policy pass
            # also removes them from any config that still names them).
            from .policy import EXCLUDED_KEXTS  # noqa: PLC0415
            for k in o.k.kexts:
                if k.checked and f"{k.name}.kext" in EXCLUDED_KEXTS:
                    k.checked = False
                    h.notices.append(f"{k.name} is not used by 1401 (its licence); "
                                     + ("that GPU runs with basic display until NullMoth's own driver covers it."
                                        if k.name in ("NootedRed", "NootRX") else "macOS runs without it."))
                    # ForgedInvariant was the TSC sync for (ASUS) laptops; on Intel, acidanthera's CpuTscSync (BSD-3)
                    # does that job. AMD CPUs keep the AMD Vanilla patches' own TSC handling.
                    if k.name == "ForgedInvariant" and "AMD" not in str(hw.get("CPU", {}).get("Manufacturer", "")):
                        for t in o.k.kexts:
                            if t.name == "CpuTscSync":
                                t.checked = True
                                h.notices.append("TSC sync: CpuTscSync in place of ForgedInvariant.")
            _nullmoth_amfipass(o, hw, mv, h)
            o.s.smbios_specific_options(cust, smbios, mv, o.ac.patches, o.k)
            res.macos_version, res.smbios, res.needs_oclp = mv, smbios, bool(needs_oclp)
            res.disabled_devices = {k: (v.get("Device ID") if isinstance(v, dict) else v) for k, v in (disabled or {}).items()}
            res.kexts = [k.name for k in o.k.kexts if k.checked]
            # itlwm (not AirportItlwm) does not join Wi-Fi through macOS's own menu: users had working
            # Bluetooth and no Wi-Fi until someone told them to install HeliPort, itlwm's companion app (10-08).
            if "itlwm" in res.kexts and "AirportItlwm" not in res.kexts:
                h.notices.append("Wi-Fi: this Intel card uses itlwm. In macOS, Wi-Fi is joined with the HeliPort app "
                                 "(github.com/OpenIntelWireless/HeliPort/releases), not the menu bar; install it after setup.")
            res.bios_requirements = o.check_bios_requirements(report, cust)
            if download:
                if not o.o.gather_bootloader_kexts(o.k.kexts, mv):
                    raise RuntimeError('Dependency gathering stopped before the EFI was ready. '
                                       'Check the preceding download error and rebuild; no installable EFI was produced.')
                # The upstream build empties out_dir (our marker with it) before copying OpenCore in, so a build that
                # stopped inside it left a folder without the marker, and every later Build on that PC was refused as
                # "unowned" (106 uploads, every version from 1.0 to 1.15). The marker goes back even when it raises.
                try:
                    o.build_opencore_efi(cust, disabled, smbios, mv, needs_oclp)
                finally:
                    if os.path.isdir(out_dir):
                        open(os.path.join(out_dir, MARKER), "w").write("built by 1401\n")
                # Tell the writer, without re-scanning, whether this machine can reach the internet in the installer,
                # so it can default to the offline (local-image) path for a PC that has no supported network adapter.
                netsupport.write_marker(out_dir, net_status)
                _keep_identity(out_dir, prior_identity, machine_key, h)
                res.decisions = h.decisions  # the policy pass reads what was decided
                res.policy_changes = policy_mod.apply(os.path.join(out_dir, "EFI", "OC", "config.plist"), res, policy)
                community.apply_efi_drivers(os.path.join(out_dir, "EFI", "OC", "config.plist"), cust, mv, h.notices,
                                            lambda url: downloads.make_request(o.o.fetcher, url).read(),
                                            experimental=policy.experimental_drivers)
                # 10-10: 43 of 233 users' DSDTs are discarded whole by macOS's ACPICA (forward Scope targets in pass 1);
                # ship the firmware table with those Scopes deferred so macOS gets a DSDT at all
                from . import dsdt_pass1  # noqa: PLC0415
                res.policy_changes += dsdt_pass1.apply(os.path.abspath(acpi_dir), out_dir)
                res.policy_changes += policy_mod.legal_comments(os.path.join(out_dir, "EFI", "OC", "config.plist"))
                # A fresh build left an OpenCore.efi that was not the verified release's (NM-YZZJY5WJ): the boot files
                # are written back from the verified zip before the check, and a file that STILL differs is being
                # rewritten by something on the PC (the check names its hash and whether it looks quarantined).
                restored = []
                try:
                    restored = validate_mod.restore_release_components(out_dir)
                except (validate_mod.ValidatorUnavailable, OSError) as e:
                    h.notices.append(f"Boot files could not be checked against the verified OpenCore zip before validation: {e}")
                for r in restored:
                    h.notices.append(f"{r['file']} was not the verified OpenCore release's ({r['found']}); written back from the verified zip.")
                res.policy_changes += restored
                res.validation = validate_mod.validate(out_dir)
                if not res.validation.get("ok"):
                    why = (res.validation.get("error") or
                           f"ocvalidate issues={(res.validation.get('ocvalidate') or {}).get('issues')} "
                           f"invariants={res.validation.get('invariants')}")
                    if any("differs from the verified OpenCore release" in str(x) for x in res.validation.get("invariants") or []):
                        why += ("\nThat file was written back from the verified OpenCore zip just before this check, so "
                                "something on this PC rewrites it: look in the security software's quarantine or history for "
                                "OpenCore files, exclude the 1401 folder under AppData\\Local\\NullMoth, and build again.")
                    raise RuntimeError("EFI failed validation: " + why)
            if download:
                from . import machine_handoff
                machine_handoff.create(report_path, res)
            res.ok = True
    except Exception as e:  # reported to the caller in res.error
        res.error = f"{type(e).__name__}: {e}"
        trace = e.__traceback__
        while trace is not None and len(res.failure_frames) < 24:
            filename = os.path.abspath(trace.tb_frame.f_code.co_filename)
            try: relative = os.path.relpath(filename, REPO)
            except ValueError: relative = '..'
            source = relative.replace(os.sep, '/') if not relative.startswith('..' + os.sep) and relative != '..' else 'external'
            if not re.fullmatch(r'[A-Za-z0-9_./-]{1,200}', source): source = 'external'
            function = trace.tb_frame.f_code.co_name
            if not re.fullmatch(r'[A-Za-z0-9_<>]{1,64}', function): function = 'unknown'
            res.failure_frames.append({'source': source, 'line': trace.tb_lineno, 'function': function})
            trace = trace.tb_next
        # 10-07: after every retry the engine said only "Could not download RTL812xLucy at this time".
        m = re.match(r"Could not download (\S+)", str(e))
        if m:
            res.error += "\n" + network_help(f"github.com ({m.group(1)})")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    from . import scan_evidence  # noqa: PLC0415
    try:
        res.capture = scan_evidence.load_for_report(
            report_path, res.raw_hardware or res.hardware, expected_report_sha256=res.report_sha256 or None)
    except scan_evidence.ReportChanged as error:
        res.capture = scan_evidence.unbound_report_capture(res.raw_hardware or res.hardware,
                                                         'the planned hardware report changed or became unavailable')
        res.ok = False
        if not res.error:
            res.error = f"{type(error).__name__}: {error}"
    if h is not None:
        res.decisions, res.notices = h.decisions, h.notices
    res.transcript = h.tee.text() if hasattr(h, "tee") else ""
    return res
