"""Checks an OpenCore config against efi_rules.json and fixes what it finds.

python -m p1401.efi_rules <config.plist> --report Report.json --macos 24.6.0 [--scope installed] [--fix]

facts_from_report() turns a Hardware Sniffer report into the facts the rules match on; the Mac app computes the same
facts from its own scan. check() returns one issue per rule whose expectations the config does not meet, with the
plain-language text the app shows. fix() applies exactly those expectations to a copy, so "Fix it for me" and the
Windows builder write the same thing.
"""
import copy
import json
import os
import plistlib
import sys

from . import policy

RULES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "efi_rules.json")
BOOT = policy.BOOT
_MISSING = object()


def load(path=RULES):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("schema") != "nullmoth-efi-rules/1":
        raise ValueError(f"{path}: unknown schema {data.get('schema')!r}")
    return data


def facts_from_report(hardware, macos_version, disabled_devices=None):
    """Facts from a Hardware Sniffer report, with the same tests policy.py uses, so the two cannot disagree."""
    from . import nullmoth, storage_drives  # noqa: PLC0415
    hw = hardware or {}
    cpu = hw.get("CPU") or {}
    board = hw.get("Motherboard") or {}
    gpus = {n: g for n, g in (hw.get("GPU") or {}).items() if not nullmoth.gpu_disabled(n, g, disabled_devices or {})}
    classes = set()
    name, code = str(cpu.get("Processor Name") or ""), str(cpu.get("Codename") or "")
    if cpu.get("Manufacturer") == "AMD" and policy.is_zen4_or_later(cpu):
        classes.add("zen45")
    if policy.is_intel_hybrid(cpu):
        classes.add("intel_hybrid")
    if cpu.get("Manufacturer") == "Intel" and ("Core(TM) Ultra" in name or any(c in code for c in ("Meteor Lake", "Arrow Lake", "Lunar Lake"))):
        classes.add("core_ultra")
    if "Arrow Lake" in code:
        classes.add("arrow_lake")
    facts = set()
    if storage_drives.wants_nvmefix(hw):
        facts.add("nvme_oem_dropout")
    return {
        "macos": macos_version or "",
        "cpu_vendor": cpu.get("Manufacturer") or "",
        "cpu_class": sorted(classes),
        "chipset": board.get("Chipset") or "",
        "laptop": board.get("Platform") == "Laptop",
        "amd_dgpu": any(g.get("Manufacturer") == "AMD" and g.get("Device Type") != "Integrated GPU" for g in gpus.values()),
        "intel_igpu": any(g.get("Manufacturer") == "Intel" and g.get("Device Type") == "Integrated GPU" for g in gpus.values()),
        "fact": sorted(facts),
    }


def matches(match, facts):
    for key, want in match.items():
        if key == "macos_min":
            if not facts.get("macos") or policy._darwin(facts["macos"]) < policy._darwin(want):
                return False
        elif key == "cpu_class":
            if not set(want) & set(facts.get("cpu_class", [])):
                return False
        elif key == "cpu_class_not":
            if set(want) & set(facts.get("cpu_class", [])):
                return False
        elif key == "chipset_not_in":
            if facts.get("chipset", "") in want:
                return False
        elif key == "fact":
            if not set(want) <= set(facts.get("fact", [])):
                return False
        elif key in ("cpu_vendor", "laptop", "amd_dgpu", "intel_igpu"):
            if facts.get(key) != want:
                return False
        else:
            raise ValueError(f"unknown match key {key!r}")   # a rule the evaluator cannot read must not pass silently
    return True


def _get(cfg, path, default=_MISSING):
    node = cfg
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def _set(cfg, path, value):
    parts = path.split(".")
    node = cfg
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _kexts(cfg):
    return [k for k in _get(cfg, "Kernel.Add", []) if isinstance(k, dict)]


def _kname(k):
    return str(k.get("BundlePath", "")).split("/")[-1]


def _args(cfg):
    return str(_get(cfg, f"NVRAM.Add.{BOOT}.boot-args", "") or "").split()


def _set_args(cfg, args):
    _set(cfg, f"NVRAM.Add.{BOOT}.boot-args", " ".join(args))


def holds(cfg, p):
    """True when the config meets one expectation."""
    if "any" in p:
        return any(holds(cfg, q) for q in p["any"])
    if "path" in p:
        v = _get(cfg, p["path"], p.get("default", _MISSING))
        if "eq" in p:
            return v is not _MISSING and v == p["eq"] and type(v) is type(p["eq"])
        if "ne" in p:
            return v != p["ne"]
        if "bits" in p:
            return isinstance(v, int) and not isinstance(v, bool) and v & p["bits"] == p["bits"]
    if "kext" in p:
        return any(_kname(k) == p["kext"] and bool(k.get("Enabled")) == p["enabled"] for k in _kexts(cfg)) or \
            (not p["enabled"] and not any(_kname(k) == p["kext"] for k in _kexts(cfg)))
    if "kext_listed" in p:
        return any(_kname(k) == p["kext_listed"] for k in _kexts(cfg))
    if "boot_arg" in p:
        return (p["boot_arg"] in _args(cfg)) == p["present"]
    if "boot_arg_prefix" in p:
        return any(a.startswith(p["boot_arg_prefix"]) for a in _args(cfg)) == p["present"]
    if "boot_arg_item" in p:
        key, item = p["boot_arg_item"]
        return any(a.startswith(key + "=") and item in a.split("=", 1)[1].split(",") for a in _args(cfg))
    if "list_lacks" in p:
        path, item = p["list_lacks"]
        return item not in (_get(cfg, path, []) or [])
    if "acpi_delete" in p:
        return any(isinstance(d, dict) and d.get("TableSignature") == p["acpi_delete"].encode() and d.get("Enabled")
                   for d in _get(cfg, "ACPI.Delete", []))
    if "kernel_block" in p:
        return any(isinstance(b, dict) and b.get("Identifier") == p["kernel_block"] and bool(b.get("Enabled")) == p["enabled"]
                   for b in _get(cfg, "Kernel.Block", []))
    if "driver" in p:
        on = any(isinstance(d, dict) and d.get("Path") == p["driver"] and d.get("Enabled", True) for d in _get(cfg, "UEFI.Drivers", []))
        return on == p["loaded"]
    if "check" in p:
        return not CHECKS[p["check"]](cfg, fix=False)
    raise ValueError(f"unknown expectation {p!r}")


def apply(cfg, p):
    """Makes one expectation true. Only the forms a rule's expect uses need a fix."""
    if "path" in p:
        if "eq" in p:
            _set(cfg, p["path"], p["eq"])
        elif "ne" in p:
            _set(cfg, p["path"], p["fix"])
        elif "bits" in p:
            v = _get(cfg, p["path"], p.get("default", 0))
            _set(cfg, p["path"], (v if isinstance(v, int) else 0) | p["bits"])
    elif "kext" in p:
        for k in _kexts(cfg):
            if _kname(k) == p["kext"]:
                k["Enabled"] = p["enabled"]
    elif "boot_arg" in p:
        args = [a for a in _args(cfg) if a != p["boot_arg"]]
        _set_args(cfg, args + [p["boot_arg"]] if p["present"] else args)
    elif "boot_arg_prefix" in p:
        _set_args(cfg, [a for a in _args(cfg) if not a.startswith(p["boot_arg_prefix"])])
    elif "boot_arg_item" in p:
        key, item = p["boot_arg_item"]
        args = _args(cfg)
        old = next((a for a in args if a.startswith(key + "=")), None)
        vals = [v for v in (old.split("=", 1)[1].split(",") if old else []) if v] + [item]
        _set_args(cfg, [a for a in args if a != old] + [key + "=" + ",".join(vals)])
    elif "list_lacks" in p:
        path, item = p["list_lacks"]
        lst = _get(cfg, path, [])
        while item in lst:
            lst.remove(item)
    elif "acpi_delete" in p:
        cfg.setdefault("ACPI", {}).setdefault("Delete", []).append(
            {"All": True, "Comment": f"Drop {p['acpi_delete']}", "Enabled": True, "OemTableId": bytes(8), "TableLength": 0,
             "TableSignature": p["acpi_delete"].encode()})
    elif "kernel_block" in p:
        cfg.setdefault("Kernel", {}).setdefault("Block", []).append(
            {"Arch": "x86_64", "Comment": f"Block {p['kernel_block']}", "Enabled": True, "Identifier": p["kernel_block"],
             "MaxKernel": "", "MinKernel": p.get("min_kernel", ""), "Strategy": "Exclude"})
    elif "check" in p:
        CHECKS[p["check"]](cfg, fix=True)
    else:
        raise ValueError(f"no fix for {p!r}")


def _dupes(cfg, fix):
    found = []
    for section, key in (("ACPI", "Path"), ("Kernel", "BundlePath")):
        entries = _get(cfg, f"{section}.Add", [])
        seen, kept = set(), []
        for e in entries:
            k = e.get(key) if isinstance(e, dict) else None
            if k and k in seen:
                found.append(k)
                continue
            seen.add(k)
            kept.append(e)
        if fix and len(kept) != len(entries):
            entries[:] = kept
    return found


def _whitelist(cfg, fix):
    on = [w for w in _get(cfg, "Booter.MmioWhitelist", []) if isinstance(w, dict) and w.get("Enabled")]
    if fix:
        for w in on:
            w["Enabled"] = False
    return on


def _mask(cfg, fix):
    bad = []
    for pt in _get(cfg, "Kernel.Patch", []):
        rep, msk = pt.get("Replace"), pt.get("ReplaceMask")
        if isinstance(rep, bytes) and isinstance(msk, bytes) and msk and len(rep) == len(msk):
            clean = bytes(r & m for r, m in zip(rep, msk))
            if clean != rep:
                bad.append(pt)
                if fix:
                    pt["Replace"] = clean
    return bad


CHECKS = {"no-duplicate-add": _dupes, "mmio-whitelist-off": _whitelist, "replace-within-mask": _mask}


def check(cfg, facts, scope="installed", rules=None):
    """One issue per rule that applies to this machine and that the config does not meet.

    Rules run in file order (policy.py's order) on a working copy that takes each earlier fix, because a later rule's
    `when` can depend on it: with SetupVirtualMap turned off for a Zen 3 board, the NVRAM write guard no longer applies,
    and reporting it would send the user to fix something the first fix already made moot."""
    work = copy.deepcopy(cfg)
    issues = []
    for r in (rules or load())["rules"]:
        if scope not in r["scope"] or not matches(r["match"], facts):
            continue
        if not all(holds(work, w) for w in r.get("when", [])):
            continue
        failed = [e for e in r["expect"] if not holds(work, e)]
        if failed:
            issues.append({"id": r["id"], "title": r["title"], "what": r["what"], "steps": r["steps"],
                           "restart": r["restart"], "failed": failed})
            for e in failed:
                apply(work, e)
    return issues


def fix(cfg, issues):
    """A fixed copy of cfg; the input is never changed."""
    out = copy.deepcopy(cfg)
    for issue in issues:
        for e in issue["failed"]:
            apply(out, e)
    return out


def main(argv=None):
    import argparse  # noqa: PLC0415
    ap = argparse.ArgumentParser(prog="1401 efi_rules")
    ap.add_argument("config")
    ap.add_argument("--report", required=True)
    ap.add_argument("--macos", required=True, help="Darwin version of the macOS this EFI starts, e.g. 24.6.0")
    ap.add_argument("--scope", choices=("installed", "stick"), default="installed")
    ap.add_argument("--fix", action="store_true")
    a = ap.parse_args(argv)
    with open(a.config, "rb") as fh:
        cfg = plistlib.load(fh)
    with open(a.report, encoding="utf-8") as fh:
        facts = facts_from_report(json.load(fh), a.macos)
    issues = check(cfg, facts, a.scope)
    for i in issues:
        print(f"  {i['id']}: {i['title']}")
    if a.fix and issues:
        import shutil, time  # noqa: E401, PLC0415
        backup = a.config + ".1401-backup-" + time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(a.config, backup)
        tmp = a.config + ".tmp"
        with open(tmp, "wb") as fh:
            plistlib.dump(fix(cfg, issues), fh)
        os.replace(tmp, a.config)
        print(f"  fixed {len(issues)}; the old config is at {backup}")
    print(json.dumps({"facts": facts, "issues": [{k: v for k, v in i.items() if k != 'failed'} for i in issues]}, default=str))
    return 1 if issues and not a.fix else 0


if __name__ == "__main__":
    sys.exit(main())
