"""Replays the builder's hardware decisions over every PC fingerprint in tests/corpus/machines.json.gz.

The replay runs the same code the app runs (p1401.engine._select): compatibility check, macOS version, SMBIOS model,
kext selection, the 1401 add-ons (MediaTek, RDNA 4, community drivers), disabled devices, BIOS requirements, notices.
What it cannot run is the ACPI-dependent part (the scan receipt keeps ACPI table hashes, not the tables).

Assumption, stated once: the receipts keep no CPU instruction-set list, so SIMD Features is derived from the CPU codename
(AVX2 on every Intel generation from Haswell, every Zen; none on Sandy/Ivy Bridge and older; none on Pentium/Celeron/Atom
of the AVX-less lines). A PC whose real list differs would have been refused or accepted by the engine differently.

    python3 tools/machine_replay.py [--macos 24,25] [--limit N] [--json out.json] [--jobs N]
"""
import collections
import contextlib
import io
import json
import multiprocessing
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

NO_AVX2 = ("Sandy Bridge", "Ivy Bridge", "Westmere", "Nehalem", "Penryn", "Core", "Bloomfield", "Clarkdale", "Lynnfield",
           "Arrandale", "Gulftown", "Bulldozer", "Piledriver", "Jaguar", "Puma", "Steamroller", "Tremont", "Gracemont-N")


def simd_for(cpu):
    name = f"{cpu.get('Processor Name', '')} {cpu.get('Codename', '')}"
    if any(c in str(cpu.get("Codename", "")) for c in NO_AVX2):
        return "MMX, SSE, SSE2, SSE3, SSSE3, SSE4.1, SSE4.2, AVX"
    if "Pentium" in name or "Celeron" in name:
        return "MMX, SSE, SSE2, SSE3, SSSE3, SSE4.1, SSE4.2"
    return "MMX, SSE, SSE2, SSE3, SSSE3, SSE4.1, SSE4.2, AVX, AVX2, FMA"


def reconstruct(c):
    """The Report.json shape the engine reads, from a corpus row's hardware."""
    r = {"CPU": dict(c["CPU"]), "Motherboard": dict(c["Motherboard"]), "BIOS": {"Firmware Type": c["BIOS"].get("Firmware Type", "UEFI"),
                                                                              "Secure Boot": "Disabled"}}
    r["CPU"].setdefault("Core Count", "4")
    r["CPU"].setdefault("CPU Count", "1")
    r["CPU"].setdefault("SIMD Features", simd_for(r["CPU"]))
    for section in ("GPU", "Network", "USB Controllers", "Storage Controllers", "Input", "Sound", "Bluetooth", "SD Controller",
                    "Biometric"):
        rows = c.get(section)
        if not rows:
            continue
        names = {}
        out = {}
        for row in rows:
            base = row.get("name") or f"{section} device"
            names[base] = names.get(base, 0) + 1
            name = base if names[base] == 1 else f"{base} #{names[base]}"
            out[name] = {k: v for k, v in row.items() if k != "name"}
        r[section] = out
    # The summary drops "Disk Drives", and the engine only checks a storage controller (VMD, unsupported SSDs) when it has one.
    # Every PCI controller is assumed to have a drive: the replay then refuses at least what the field refused.
    for ctl in r.get("Storage Controllers", {}).values():
        count = ctl.pop("Disk Drive Count", None)      # newer scans say how many drives the controller has
        if ctl.get("Bus Type") == "PCI" and count != 0:
            ctl["Disk Drives"] = ["Disk"] * (count or 1)
    for key in ("Resizable BAR",):
        for g in r.get("GPU", {}).values():
            g.setdefault(key, "Disabled")
    return r


_ENGINE = {}


def _engine():
    if not _ENGINE:
        import time
        time.sleep = lambda seconds: None   # the engine pauses for the reader; a replay has none
        from p1401 import engine, netsupport, amd_rdna4, community
        mod, utils = engine._load_engine()
        _ENGINE.update(engine=engine, mod=mod, utils=utils, netsupport=netsupport, amd_rdna4=amd_rdna4, community=community)
    return _ENGINE


def replay(c, macos="", experimental=False, tahoe_audio="voodoohda", external_target=False):
    """One corpus row -> what the builder decides for it. Never raises: a refusal or a crash is part of the answer."""
    E = _engine()
    engine = E["engine"]
    from p1401 import scan_evidence
    report = reconstruct(c)
    pol = engine.Policy(macos=macos, experimental_drivers=experimental, tahoe_audio=tahoe_audio, external_target=external_target)
    pol = engine.dataclasses.replace(pol, prefer=dict(pol.prefer))
    res = engine.BuildResult(ok=False, out_dir="")
    out = {"ok": False, "refused": "", "crash": ""}
    tmp = tempfile.mkdtemp(prefix="1401-replay-")
    h = engine.Headless(E["utils"], pol, False)
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink), h:
            for name in ("netsupport", "amd_rdna4", "community"):
                with contextlib.suppress(Exception):
                    E[name].register()
            o = E["mod"].OCPE()
            o.result_dir = os.path.join(tmp, "out")
            path, notes = engine.report_mod.normalized_copy(os.path.join(tmp, "Report.json"), tmp, raw_hardware=report)
            h.notices.extend(notes)
            valid, errors, warnings, rep = o.v.validate_report(path)
            if not valid or errors:
                raise RuntimeError(f"hardware report rejected: {errors}")
            res.raw_hardware = report
            sel = engine._select(o, h, pol, res, rep,
                                 lambda: scan_evidence.unbound_report_capture(report, "replay"), lambda: ("", None))
            kexts = [k.name for k in o.k.kexts if k.checked]
            located = [(engine.unsupported.locate(sel.hw, k, v if isinstance(v, dict) else None), v) for k, v in (sel.disabled or {}).items()]
            out.update(ok=True, macos=sel.mv, smbios=sel.smbios, needs_oclp=bool(sel.needs_oclp), kexts=sorted(kexts),
                       disabled=sorted(str(v.get("Device ID") if isinstance(v, dict) else v) for v in (sel.disabled or {}).values()),
                       disabled_detail=sorted([sec or "?", str(v.get("Device ID") if isinstance(v, dict) else v), name or "?"]
                                              for (sec, name), v in located),
                       bios=o.check_bios_requirements(rep, sel.cust), net_status=str(sel.net_status),
                       decisions=[(d.prompt[:60], d.answer) for d in h.decisions],
                       compat=_compat(sel.hw))
    except (engine.EngineExit, engine.MacosNotOffered, engine.UnknownPrompt, engine.EngineLoop) as e:
        out["refused"] = f"{type(e).__name__}: {e}"
    except Exception as e:  # noqa: BLE001 - the replay reports a crash, it does not stop on one
        out["crash"] = f"{type(e).__name__}: {e}"
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    out["notices"] = list(h.notices)
    out["transcript_tail"] = sink.getvalue()[-600:] if not out["ok"] else ""
    return out


def _compat(hw):
    """Per device: (min, max) macOS the engine gave it, for the classes that carry one."""
    rows = {}
    for section in ("GPU", "Network", "Sound", "Bluetooth", "Storage Controllers", "SD Controller", "Biometric", "Input"):
        for name, p in (hw.get(section) or {}).items():
            if isinstance(p, dict) and "Compatibility" in p:
                rows[f"{section}|{p.get('Device ID', name)}|{name}"] = list(p["Compatibility"] or [None, None])
    return rows


def _task(args):
    c, macos, kw = args
    return c["key"], macos, replay(c["hardware"], macos=macos, **kw)


def run(machines, macos_list=("24", "25"), jobs=None, **kw):
    tasks = [({"key": m["key"], "hardware": m["hardware"]}, mv, kw) for m in machines for mv in macos_list]
    ctx = multiprocessing.get_context("spawn")
    results = {}
    with ctx.Pool(jobs or max(2, (os.cpu_count() or 4) // 2), maxtasksperchild=200) as pool:
        for key, mv, r in pool.imap_unordered(_task, tasks, chunksize=8):
            results.setdefault(key, {})[mv] = r
    return results


def main(argv):
    import machine_corpus
    macos = ("24", "25")
    limit = None
    out = None
    jobs = None
    it = iter(argv)
    for a in it:
        if a == "--macos":
            macos = tuple(next(it).split(","))
        elif a == "--limit":
            limit = int(next(it))
        elif a == "--json":
            out = next(it)
        elif a == "--jobs":
            jobs = int(next(it))
    machines = machine_corpus.load()["machines"][:limit]
    results = run(machines, macos, jobs)
    if out:
        with open(out, "w") as f:
            json.dump(results, f)
    tally = collections.Counter()
    for key, per in results.items():
        for mv, r in per.items():
            tally[(mv, "ok" if r["ok"] else "refused" if r["refused"] else "crash")] += 1
    print(dict(tally))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
