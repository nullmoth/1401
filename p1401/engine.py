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


def _macos_answer(prompt, ctx, pol):
    """The version menu. "" takes the engine's default, but the default is not always on the menu.
    10-07 (NM-036E35M9, NM-0ZH4CA2A): a Broadcom card that tops out at Ventura plus a GeForce marked Sequoia-only
    left no native version; the menu offered only 23-25 (OCLP) while the default stayed "macOS Ventura 13", so the
    blank answer was refused three times. Then: Sequoia (24, the NullMoth driver's target) if listed, else the newest."""
    if pol.macos:
        return pol.macos
    offered = re.findall(r"^\s*(\d+)\.\s+macOS (.+?)(?:\s+\(|$)", ctx, re.M)
    m = re.search(r"\(default: macOS (.+?)\)", prompt)
    if not offered or (m and any(name.strip() == m.group(1).strip() for _, name in offered)):
        return ""
    nums = [n for n, _ in offered]
    return "24" if "24" in nums else max(nums, key=int)


# 10-07 (NM-CHW0YW6F): the reason ("Intel VMD controllers are not supported ... disable Intel VMD in the BIOS") sat at
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
    # Filled by 1401's pre-pass, never by the user: device kind ("WiFi") -> the device name 1401 picked.
    prefer: dict = field(default_factory=dict)
    # The stick's opencore-*.txt from a failed boot: bootfix.py changes the next build from what it shows.
    boot_logs: list = field(default_factory=list)
    # The line the screen stopped on, as the user typed or pasted it when sending logs (bootfix.after_handoff).
    stopped_at: str = ""


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
    from . import tls  # noqa: PLC0415
    tls.install()   # verify against the Windows store + certifi, not certifi alone
    return mod, utils_mod


class _Sig(bytes):
    """Bytes that also equal the same text: b"DSDT" == "DSDT" is True for this type."""
    def __eq__(self, other):
        return bytes.__eq__(self, other.encode("latin-1")) if isinstance(other, str) else bytes.__eq__(self, other)

    def __ne__(self, other):
        return not self.__eq__(other)

    __hash__ = bytes.__hash__


def _dsdt_signature_fix():
    """10-07 (uploaded log NM-DY0PA8ZT: "Failed to load tables ... - dsdt.aml"): the engine reads a table's signature
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


# 10-07 (NM-EWTXNCET PermissionError in ...\Downloads\Compressed\1401\...\OCK_Files, NM-QT5R4QQQ missing
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
    # 10-07 (NM-DTC05X6Y, NM-GP91G90X): "TimeoutError: The read operation timed out" while gathering OpenCore and
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
        # 10-07 (NM-KHVZNES3, NM-0CEPWXM0, NM-TS458ASW): the validator downloaded OpenCorePkg a SECOND time after the
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
        # 10-07 (NM-CG2NRMES, NM-Y0CFTWRR): raw.githubusercontent.com reset every connection (WinError 10054/10060,
        # mainland China); the engine got None back and died on "argument of type 'NoneType' is not iterable".
        if got is None:
            raise RuntimeError(network_help(resource_url))
        return got
    cls.fetch_and_parse_content = fetch_and_parse_content
    cls._1401_patient = True


def _prepare_out(out_dir):
    """The engine wipes its result dir. Only ever hand it a folder that is empty or one we made."""
    out_dir = os.path.abspath(out_dir)
    if os.path.exists(out_dir) and os.listdir(out_dir) and not os.path.exists(os.path.join(out_dir, MARKER)):
        raise RuntimeError(f"refusing to build into {out_dir}: not empty and not a 1401 build folder")
    if os.path.exists(os.path.join(out_dir, MARKER)):
        # a second Build failed "Access is denied: ...EFI\\OC\\ACPI" because Windows leaves the old build's
        # folders ReadOnly and the upstream cleanup can't delete them. Our own previous build: clear the flag, wipe it.
        # 10-07 (NM-3YJDQC1P): the wipe stopped with FileNotFoundError on ...\EFI\OC\Drivers\UefiPxeBcDxe.efi - the
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
        if not hit:
            if exited:
                raise exited
            return
        mux = nullmoth.mux_help(checker.hardware_report)
        if mux:
            h.notices.append(mux)
        gpus = checker.hardware_report.get("GPU", {})
        checker._restrict_native_compatibility(checker._widest_compatibility(g.get("Compatibility") for g in gpus.values()))
        h.notices.append("NullMoth driver: " + ", ".join(hit) + " selected for macOS 15 Sequoia."
                         + ("" if nullmoth.tested(checker.hardware_report) else
                            " This card is in NVIDIA's supported list but has not been tested with the driver yet."))
    checker.check_gpu_compatibility = wrapped


def build(report_path, acpi_dir, out_dir, policy=None, echo=False, download=True):
    """Report.json + ACPI dump -> OpenCore EFI in out_dir. download=False stops after planning (no network)."""
    policy = policy or Policy()
    policy = dataclasses.replace(policy, prefer=dict(policy.prefer))  # the Wi-Fi pre-pass writes to prefer
    out_dir = os.path.abspath(out_dir)
    if os.path.exists(out_dir) and os.listdir(out_dir) and not os.path.exists(os.path.join(out_dir, MARKER)):
        raise RuntimeError("refusing to build into an unowned nonempty folder")
    scratch = tempfile.mkdtemp(prefix="1401-report-")
    res = BuildResult(ok=False, out_dir=out_dir)
    h = None
    try:
        mod, utils_mod = _load_engine()
        h = Headless(utils_mod, policy, echo)
        with h:
            # 10-07 (NM-EMCW2SYV): Build ran with no Report.json and failed with a bare FileNotFoundError.
            if not os.path.isfile(report_path):
                raise RuntimeError("This PC has not been checked yet (no hardware report). Run Check this PC first and wait for it "
                                   "to finish; if it stops with an error, send that log instead.")
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
            from . import acpi_diagnostics
            with acpi_diagnostics.capture(o.ac.acpi, res.acpi_diagnostics):
                o.ac.read_acpi_tables(os.path.abspath(acpi_dir))
            if not o.ac.ensure_dsdt():
                raise RuntimeError(f"no usable DSDT in {acpi_dir} - the ACPI dump is required")
            _nullmoth_gpu_pass(o.c, h)
            hw, native, oclp_versions = o.c.check_compatibility(report)
            res.hardware = hw
            mv = o.select_macos_version(_wifi_prepass(hw, policy, h, o), native, oclp_versions)
            cust, disabled, needs_oclp = o.h.hardware_customization(hw, mv)
            from . import panel_guard, scan_evidence
            panel = panel_guard.active_panel_notice(disabled, scan_evidence.load_for_report(
                report_path, res.raw_hardware, expected_report_sha256=res.report_sha256))
            if panel:
                h.notices.append(panel)
            _prepare_out(out_dir)  # Preserve prior EFI on an output-safety refusal.
            needs_oclp = _oclp_still_needed(cust, needs_oclp, h)
            smbios = o.s.select_smbios_model(cust, mv)
            o.ac.select_acpi_patches(cust, disabled)
            needs_oclp = o.k.select_required_kexts(cust, mv, needs_oclp, o.ac.patches)
            o.s.smbios_specific_options(cust, smbios, mv, o.ac.patches, o.k)
            res.macos_version, res.smbios, res.needs_oclp = mv, smbios, bool(needs_oclp)
            res.disabled_devices = {k: (v.get("Device ID") if isinstance(v, dict) else v) for k, v in (disabled or {}).items()}
            res.kexts = [k.name for k in o.k.kexts if k.checked]
            # itlwm (not AirportItlwm) does not join Wi-Fi through macOS's own menu: users on the support chat had working
            # Bluetooth and no Wi-Fi until someone told them to install HeliPort, itlwm's companion app (10-08).
            if "itlwm" in res.kexts and "AirportItlwm" not in res.kexts:
                h.notices.append("Wi-Fi: this Intel card uses itlwm. In macOS, Wi-Fi is joined with the HeliPort app "
                                 "(github.com/OpenIntelWireless/HeliPort/releases), not the menu bar; install it after setup.")
            res.bios_requirements = o.check_bios_requirements(report, cust)
            if download:
                if not o.o.gather_bootloader_kexts(o.k.kexts, mv):
                    raise RuntimeError('Dependency gathering stopped before the EFI was ready. '
                                       'Check the preceding download error and rebuild; no installable EFI was produced.')
                o.build_opencore_efi(cust, disabled, smbios, mv, needs_oclp)
                open(os.path.join(out_dir, MARKER), "w").write("built by 1401\n")
                res.decisions = h.decisions  # the policy pass reads what was decided
                res.policy_changes = policy_mod.apply(os.path.join(out_dir, "EFI", "OC", "config.plist"), res, policy)
                res.validation = validate_mod.validate(out_dir)
                if not res.validation.get("ok"):
                    raise RuntimeError("EFI failed validation: " + (res.validation.get("error") or
                                       f"ocvalidate issues={(res.validation.get('ocvalidate') or {}).get('issues')} "
                                       f"invariants={res.validation.get('invariants')}"))
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
        # 10-07 (NM-Z3WKQAFQ): after every retry the engine said only "Could not download RTL812xLucy at this time".
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
