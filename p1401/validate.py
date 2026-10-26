"""Checks a built EFI two ways: OpenCore's own ocvalidate (from the same release the EFI was built with), plus
file-level checks that ocvalidate doesn't do.

If the validator can't run, that's a failure, never a pass. A missing ocvalidate, a hash mismatch, or an
unreadable config all fail with the reason attached.

ocvalidate is tied to its OpenCore version (1.0.8's ocvalidate checks a 1.0.8 config), so we download the same
release zip the engine used (URL + sha256 from the engine's download history) and take ocvalidate from it.
"""
import hashlib
import io
import http.client
import json
import os
import platform
import plistlib
import subprocess
import time
import urllib.request
import zipfile
from . import tls
tls.install()   # downloads verify against the OS certificate store + certifi

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def _engine_cache():
    from .engine import OCK_CACHE  # noqa: PLC0415 - the engine decides where its downloads live
    return OCK_CACHE
CACHE = os.path.join(os.path.expanduser("~"), ".cache", "1401")
TIMEOUT = 120  # seconds

# Kexts that are Lilu plugins: Lilu must load before every one of them.
LILU_PLUGINS = {"WhateverGreen.kext", "AppleALC.kext", "VirtualSMC.kext", "NVMeFix.kext", "RestrictEvents.kext",
                "CpuTopologyRebuild.kext", "NootRX.kext", "NootedRed.kext", "BlueToolFixup.kext", "CPUFriend.kext",
                "IntelBTPatcher.kext", "ECEnabler.kext", "BrightnessKeys.kext", "FeatureUnlock.kext", "HibernationFixup.kext",
                "DebugEnhancer.kext", "RadeonSensor.kext", "SMCRadeonGPU.kext", "AMDRyzenCPUPowerManagement.kext"}


class ValidatorUnavailable(RuntimeError):
    pass


DORTANIA_BUILDS = "https://raw.githubusercontent.com/dortania/build-repo/builds/latest.json"


def _opencore_from_builds(fetch=None):
    """(url, sha256) of an OpenCore zip already in the cache whose SHA-256 Dortania's build list publishes - the list the
    engine itself downloads OpenCore from. 1.9 build 10-10: the engine reused a cached OpenCorePkg ("already
    downloaded") whose download was never written to its history, and the build stopped with "engine download history
    names no OpenCorePkg" though the zip was right there."""
    if fetch is None:
        def fetch(url):
            from . import tls  # noqa: PLC0415
            tls.install()
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "1401"}), timeout=60) as r:
                return json.loads(r.read())
    listing = fetch(DORTANIA_BUILDS)
    for v in (listing.get("OpenCorePkg") or {}).get("versions", []):
        for kind in ("debug", "release"):
            url = (v.get("links") or {}).get(kind)
            sha = ((v.get("hashes") or {}).get(kind) or {}).get("sha256")
            if not (isinstance(url, str) and url.startswith("https://") and isinstance(sha, str) and len(sha) == 64):
                continue
            cached = os.path.join(CACHE, os.path.basename(url))
            if os.path.isfile(cached) and not os.path.islink(cached) and _sha256(cached) == sha:
                return url, sha
    raise ValidatorUnavailable("engine download history names no OpenCorePkg, and no cached OpenCore matches Dortania's list")


def _opencore_release():
    try:
        with open(os.path.join(_engine_cache(), "history.json")) as fh:
            for x in json.load(fh):
                if x["product_name"] == "OpenCorePkg":
                    return x["url"], x["sha256"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return _opencore_from_builds()


def ocvalidate_path():
    url, sha = _opencore_release()
    if not sha:
        raise ValidatorUnavailable(f"OpenCorePkg {url} has no sha256 - refusing an unverifiable validator")
    zpath = os.path.join(CACHE, os.path.basename(url))
    os.makedirs(CACHE, exist_ok=True)
    if not os.path.exists(zpath) or _sha256(zpath) != sha:
        tmp = zpath + ".tmp"
        req = urllib.request.Request(url, headers={"User-Agent": "1401"})
        # 10-07: IncompleteRead mid-file failed the build. Normally the engine's own checked copy is
        # already here (engine.download_and_save_file keeps it); this is the fallback, retried like the engine's.
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT) as r, open(tmp, "wb") as fh:
                    fh.write(r.read())
                break
            except (OSError, http.client.HTTPException) as e:
                if attempt == 3:
                    from . import mirror  # noqa: PLC0415
                    try:
                        with open(tmp, "wb") as fh:
                            fh.write(mirror.fetch(url, timeout=TIMEOUT).read())
                        break
                    except (mirror.MirrorError, OSError):
                        pass
                    from .engine import network_help  # noqa: PLC0415
                    raise ValidatorUnavailable(f"{type(e).__name__}: {e}. " + network_help(url)) from e
                time.sleep(2 ** (attempt + 1))
        got = _sha256(tmp)
        if got != sha:
            os.remove(tmp)
            raise ValidatorUnavailable(f"{url} sha256 {got[:12]} != recorded {sha[:12]}")
        os.replace(tmp, zpath)
    name = {"Windows": "ocvalidate.exe", "Linux": "ocvalidate.linux"}.get(platform.system(), "ocvalidate")
    out = os.path.join(CACHE, sha[:12] + "-" + name)
    # A verified archive does not authenticate a validator left in a writable cache.
    # Compare executable bytes before every launch; never run a stale or replaced copy.
    with open(zpath, "rb") as stream:
        archive_bytes = stream.read(64 * 1024 * 1024 + 1)
    if len(archive_bytes) > 64 * 1024 * 1024 or hashlib.sha256(archive_bytes).hexdigest() != sha:
        raise ValidatorUnavailable("The OpenCore archive changed before validator extraction; validation stopped.")
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as z:
        member = next((m for m in z.namelist() if m.endswith("Utilities/ocvalidate/" + name)), None)
        if not member:
            raise ValidatorUnavailable(f"{os.path.basename(url)} has no Utilities/ocvalidate/{name}")
        expected = z.read(member)
    digest = hashlib.sha256(expected).hexdigest()
    if os.path.islink(out):
        raise ValidatorUnavailable("The cached OpenCore validator is a link; validation stopped.")
    if not os.path.exists(out) or _sha256(out) != digest:
        import tempfile
        fd, temporary = tempfile.mkstemp(prefix="1401-validator-", dir=CACHE)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(expected)
            os.chmod(temporary, 0o755)
            # Antivirus holds a just-written .exe while it scans it: the rename failed with "[WinError 5] Access is
            # denied" and the write stopped (1.14.2 write logs). Retry for a few seconds; a lock that never clears
            # still stops before anything is launched.
            for attempt in range(12):
                try:
                    os.replace(temporary, out)
                    break
                except PermissionError:
                    if attempt == 11: raise
                    time.sleep(0.5)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
    if os.path.islink(out) or _sha256(out) != digest:
        raise ValidatorUnavailable("OpenCore validator bytes differ from the verified release; validation stopped.")
    return out


def _sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_ocvalidate(config_path):
    """Returns (ok, issues:int, text)."""
    exe = ocvalidate_path()
    # ocvalidate is a plain C program that opens the path it is given through the ANSI file API, so a config under a
    # Windows account whose name is outside the system code page ("Failed to read %USERPROFILE%\\?M?N\\...") could not
    # be read, and the build stopped with "ocvalidate issues=0" (115 build logs on 10-24 to 10-26). It runs from the
    # config's own folder and is given the bare file name, which is ASCII; Windows resolves the folder for it.
    folder, name = os.path.split(os.path.abspath(config_path))
    try:
        p = subprocess.run([exe, name], cwd=folder, capture_output=True, text=True, errors="replace", timeout=TIMEOUT)
    except OSError as error:
        if getattr(error, "winerror", None) == 4551:
            raise ValidatorUnavailable("Windows application control blocked the verified OpenCore validator (4551). "
                                       "No validated EFI was produced. Review Applications and Services Logs > Microsoft > "
                                       "Windows > CodeIntegrity > Operational in Event Viewer, and follow the device "
                                       "administrator's approval process for this exact OpenCore release. "
                                       "Do not disable application control or substitute an unverified validator.") from None
        raise
    text = (p.stdout + p.stderr).strip()
    # ocvalidate exits 0 only when it found nothing; its last line says how many issues otherwise.
    issues = 0
    for line in text.splitlines():
        if "Found" in line and "issue" in line:
            issues = int("".join(c for c in line.split("Found")[1].split("issue")[0] if c.isdigit()) or 0)
    return p.returncode == 0 and issues == 0, issues, text


def invariants(efi_dir):
    """Checks the files ocvalidate never looks at. Returns a list of failures (empty means fine)."""
    oc = os.path.join(efi_dir, "EFI", "OC")
    fails = []
    with open(os.path.join(oc, "config.plist"), "rb") as fh:
        cfg = plistlib.load(fh)
    order = []
    for k in cfg["Kernel"]["Add"]:
        if not k.get("Enabled"):
            continue
        bp = os.path.join(oc, "Kexts", k["BundlePath"])
        order.append(k["BundlePath"].split("/")[-1])
        if not os.path.isdir(bp):
            fails.append(f"kext missing on disk: {k['BundlePath']}")
            continue
        if k.get("ExecutablePath") and not os.path.isfile(os.path.join(bp, k["ExecutablePath"])):
            fails.append(f"kext executable missing: {k['BundlePath']}/{k['ExecutablePath']}")
        if not os.path.isfile(os.path.join(bp, k.get("PlistPath") or "Contents/Info.plist")):
            fails.append(f"kext Info.plist missing: {k['BundlePath']}")
    if "Lilu.kext" in order:
        li = order.index("Lilu.kext")
        fails += [f"{p} loads before Lilu" for p in order[:li] if p in LILU_PLUGINS]
    elif any(p in LILU_PLUGINS for p in order):
        fails.append(f"Lilu plugins enabled without Lilu: {[p for p in order if p in LILU_PLUGINS]}")
    for a in cfg["ACPI"]["Add"]:
        if a.get("Enabled") and not os.path.isfile(os.path.join(oc, "ACPI", a["Path"])):
            fails.append(f"SSDT missing on disk: {a['Path']}")
    for d in cfg["UEFI"]["Drivers"]:
        if d.get("Enabled") and not os.path.isfile(os.path.join(oc, "Drivers", d["Path"])):
            fails.append(f"UEFI driver missing on disk: {d['Path']}")
    for t in cfg["Misc"].get("Tools", []):
        if t.get("Enabled") and not os.path.isfile(os.path.join(oc, "Tools", t["Path"])):
            fails.append(f"tool missing on disk: {t['Path']}")
    gen = cfg["PlatformInfo"].get("Generic", {})
    for key in ("SystemSerialNumber", "MLB", "SystemUUID", "SystemProductName"):
        if not gen.get(key):
            fails.append(f"PlatformInfo.Generic.{key} is empty")
    if not os.path.isfile(os.path.join(efi_dir, "EFI", "BOOT", "BOOTx64.efi")):
        fails.append("EFI/BOOT/BOOTx64.efi missing - the firmware has nothing to boot")
    return fails


def release_archive():
    """The verified OpenCore release zip's bytes, re-checked against the sha256 the engine recorded for this build.
    This is the same zip ocvalidate and release_components read. Raises ValidatorUnavailable when it is not cached or
    does not match, so a caller that extracts a driver from it (policy.py's emulated NVRAM) can keep the firmware guard
    instead of shipping an unverified file."""
    url, expected = _opencore_release()
    if not expected:
        raise ValidatorUnavailable(f"OpenCorePkg {url} has no recorded sha256")
    path = os.path.join(CACHE, os.path.basename(url))
    if not os.path.isfile(path) or os.path.islink(path):
        raise ValidatorUnavailable(f"the verified OpenCore release is not cached at {path}")
    with open(path, "rb") as stream:
        data = stream.read(256 * 1024 * 1024 + 1)
    if len(data) > 256 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != expected:
        raise ValidatorUnavailable("the cached OpenCore release does not match its recorded sha256")
    return data


def _release_files(efi_dir):
    """(verified release zip bytes, relative paths of the files in the built EFI that must come from it)."""
    url, expected = _opencore_release()
    archive_path = os.path.join(CACHE, os.path.basename(url))
    with open(archive_path, 'rb') as stream:
        data = stream.read()
    if not expected or hashlib.sha256(data).hexdigest() != expected:
        raise ValidatorUnavailable('The OpenCore archive changed before its boot files could be checked.')
    with open(os.path.join(efi_dir, 'EFI', 'OC', 'config.plist'), 'rb') as stream:
        config = plistlib.load(stream)
    relative_paths = ['EFI/BOOT/BOOTx64.efi', 'EFI/OC/OpenCore.efi']
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = set(archive.namelist())
    for driver in config.get('UEFI', {}).get('Drivers', []):
        relative = 'EFI/OC/Drivers/' + driver.get('Path', '')
        if driver.get('Enabled') and 'X64/' + relative in members:
            relative_paths.append(relative)
    return data, relative_paths


def describe_file(path):
    """What a boot file that is not the release's looks like: its hash and size, and whether security software seems
    to have replaced it. A quarantined or scrubbed file is empty, tiny, or no longer a PE image (no 'MZ' header)."""
    try:
        size = os.path.getsize(path)
        with open(path, 'rb') as stream:
            head = stream.read(2)
    except OSError as error:
        return f'unreadable ({type(error).__name__})'
    digest = _sha256(path)
    note = ''
    if size == 0:
        note = '; empty - security software may have quarantined it'
    elif head != b'MZ' or size < 4096:
        note = '; not a PE image - security software may have replaced or quarantined it'
    return f'sha256 {digest}, {size} bytes{note}'


def restore_release_components(efi_dir):
    """Puts the verified release's own bytes back under every boot file that is missing or differs (BOOTx64.efi,
    OpenCore.efi, its drivers). Returns one record per file replaced, with what was there. A fresh build produced
    "EFI/OC/OpenCore.efi differs from the verified OpenCore release" (NM-YZZJY5WJ): whatever wrote that file - the
    engine's own download cache or security software - the EFI must leave here with the release's bytes or not at all,
    so the file is replaced from the verified zip before the check, and the check still runs after."""
    data, relative_paths = _release_files(efi_dir)
    records = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for relative in relative_paths:
            path = os.path.join(efi_dir, *relative.split('/'))
            good = archive.read('X64/' + relative)
            if os.path.isfile(path) and _sha256(path) == hashlib.sha256(good).hexdigest():
                continue
            found = describe_file(path) if os.path.isfile(path) else 'missing'
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + '.1401-restore'
            with open(tmp, 'wb') as stream:
                stream.write(good)
            if os.path.exists(path):
                os.chmod(path, 0o644)
            os.replace(tmp, path)
            records.append({'tool': 'release-components', 'file': relative, 'found': found,
                            'restored_sha256': hashlib.sha256(good).hexdigest()})
    return records


def release_components(efi_dir):
    """The boot files must be from the release whose validator checked the config."""
    data, relative_paths = _release_files(efi_dir)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        failures = []
        for relative in relative_paths:
            path = os.path.join(efi_dir, *relative.split('/'))
            if not os.path.isfile(path):
                failures.append(relative + ' is missing from the built EFI')
            elif _sha256(path) != hashlib.sha256(archive.read('X64/' + relative)).hexdigest():
                failures.append(relative + ' differs from the verified OpenCore release (' + describe_file(path)
                                + '); rebuild the complete EFI')
    return failures


# Sections whose keys are names the user chooses (device paths, NVRAM GUIDs and variables): any key, values checked
# against the sample's first entry only when the sample has one of the same type.
FREE_KEY_SECTIONS = {("DeviceProperties", "Add"), ("DeviceProperties", "Delete"), ("NVRAM", "Add"), ("NVRAM", "Delete"),
                     ("NVRAM", "LegacySchema")}


def schema_problems(cfg, samples):
    """The config's shape against OpenCore's own Sample.plist (and SampleCustom.plist) from the same verified release:
    every key known to OpenCore and every value of the type OpenCore reads (a missing key takes its default). This is what
    ocvalidate checks first; it is the check 1401 runs itself when Windows will not run ocvalidate."""
    out = []

    def kind(v):
        return "bool" if isinstance(v, bool) else "int" if isinstance(v, int) else type(v).__name__

    def walk(c, refs, path):
        refs = [r for r in refs if isinstance(r, dict)]
        if path in FREE_KEY_SECTIONS:
            return
        for k, v in c.items():
            if k.startswith("#"):
                continue
            known = [r[k] for r in refs if k in r]
            if not known:
                out.append(f"{'.'.join(path + (k,))}: not a key OpenCore knows")
                continue
            if kind(v) not in {kind(x) for x in known}:
                out.append(f"{'.'.join(path + (k,))}: is {kind(v)}, OpenCore reads {kind(known[0])}")
                continue
            if isinstance(v, dict):
                walk(v, known, path + (k,))
            elif isinstance(v, list):
                tmpl = [x[0] for x in known if isinstance(x, list) and x and isinstance(x[0], dict)]
                for i, e in enumerate(v):
                    if isinstance(e, dict) and tmpl:
                        walk(e, tmpl, path + (k, str(i)))
        # A missing key is not checked: OpenCore reads its default and ocvalidate accepts it (measured on 1,064 uploaded
        # configs: 301 lacked HideVerbose, written by older OpenCore releases, and boot fine).
    walk(cfg, samples, ())
    return out


def release_samples():
    """Sample.plist and SampleCustom.plist from the verified OpenCore release in the cache."""
    url, expected = _opencore_release()
    archive_path = os.path.join(CACHE, os.path.basename(url))
    with open(archive_path, "rb") as stream:
        data = stream.read()
    if not expected or hashlib.sha256(data).hexdigest() != expected:
        raise ValidatorUnavailable("The OpenCore archive changed before its sample config could be read.")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return [plistlib.loads(archive.read(n)) for n in ("Docs/Sample.plist", "Docs/SampleCustom.plist") if n in archive.namelist()]


def validate(efi_dir):
    """Returns a dict: ok, ocvalidate {ok, issues, text}, invariants [..], error.
    When Windows application control (Smart App Control / WDAC, error 4551) refuses to run ocvalidate, the config is
    checked against OpenCore's own sample of the same verified release instead (schema_problems), with the same file
    and boot-file checks; the result says so. WAS: the build stopped there and 8 PCs could not make a stick at all."""
    out = {"ok": False, "ocvalidate": None, "invariants": [], "error": ""}
    cfg_path = os.path.join(efi_dir, "EFI", "OC", "config.plist")
    try:
        ok, n, text = run_ocvalidate(cfg_path)
        out["ocvalidate"] = {"ok": ok, "issues": n, "text": text[-2000:]}
        out["invariants"] = invariants(efi_dir) + release_components(efi_dir)
        out["ok"] = ok and not out["invariants"]
    except ValidatorUnavailable as e:
        if "application control blocked" not in str(e):
            out["error"] = f"{type(e).__name__}: {e}"
            return out
        try:
            with open(cfg_path, "rb") as fh:
                cfg = plistlib.load(fh)
            schema = schema_problems(cfg, release_samples())
            out["ocvalidate"] = {"ok": None, "issues": len(schema), "text": "\n".join(schema)[-2000:],
                                 "fallback": "Windows application control blocked ocvalidate (4551): checked against "
                                             "OpenCore's Sample.plist from the same verified release"}
            out["invariants"] = schema + invariants(efi_dir) + release_components(efi_dir)
            out["ok"] = not out["invariants"]
        except Exception as e2:  # noqa: BLE001 - the reason is the result: Windows' refusal first, then why the
            out["ocvalidate"] = None  # fallback could not stand in for it
            out["error"] = f"{type(e).__name__}: {e} The check against OpenCore's sample could not run either: {type(e2).__name__}"
    except Exception as e:  # couldn't validate, so not ok; keep the reason
        out["error"] = f"{type(e).__name__}: {e}"
    return out
