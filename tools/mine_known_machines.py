"""Builds p1401/known_machines.json entries from the stick logs, by CPU.

The stick's opencore-*.txt log names the CPU ("OCCPU: Found ...") and the memory-map quirks the boot ran with (the
"OCABC:" line, and whether "MMIO devirt" ran). A log in which OpenCore registers a macOS volume on an internal disk
(bootfix._MACOS_DISK: the install put macOS on the PC's disk) is a boot that passed boot.efi; a log that stops at
EB.MM.AKM / STOP 0x16 without one is a boot that did not. The board is not in the log (the batch ids of the build log and of
the stick logs never coincide), so the table is by CPU and applies to every board with that CPU.

For one CPU, with every quirk set seen counted by distinct upload batches:
  - a quirk set is chosen only when it failed in at most 10% of its batches and passed in at least 5;
  - and every other quirk set seen in at least 5 batches failed in at least 20% of them, and at least twice as often.
Where both sets work (most CPUs) nothing is written: the builder's own rules stay in charge.

    python3 tools/mine_known_machines.py <incoming folder>... [--write]

Without --write it prints what it would add. Entries that exist are never changed.
"""
import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from p1401 import bootfix  # noqa: E402

KNOWN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "p1401", "known_machines.json")
# OpenCore's own abbreviations on the "OCABC:" line, only the ones whose Booter > Quirks name is certain
ABBR = {"VMAP": "SetupVirtualMap", "RBMAP": "RebuildAppleMemoryMap", "CSLIDE": "ProvideCustomSlide",
        "RTPERMS": "SyncRuntimePermissions", "FEXITBS": "ForceExitBootServices"}
_LINE = re.compile(r"OCABC: (?:[A-Z]+ [01]\s*)+")


def oc_quirks(text):
    """{quirk name: bool} from the last OCABC quirk line, plus DevirtualiseMmio when the log shows it ran."""
    lines = _LINE.findall(text)
    if not lines:
        return {}
    pairs = re.findall(r"([A-Z]+) ([01])", lines[-1])
    q = {ABBR[k]: v == "1" for k, v in pairs if k in ABBR}
    q["DevirtualiseMmio"] = "OCABC: MMIO devirt" in text
    return q


def cpu_of(text):
    """The CPU model token from "OCCPU: Found <brand string>", or None."""
    m = re.search(r"OCCPU: Found (.+)", text)
    if not m:
        return None
    t = re.search(r"(\d{4,5}[A-Z]{0,3}\d?[A-Z]{0,2})(?![0-9A-Za-z])", re.sub(r"\(R\)|\(TM\)|@.*", "", m.group(1)))
    return t.group(1) if t else None


def aggregate(records, min_pass=5, max_fail=0.10, other_fail=0.20):
    """records: [{'batch', 'cpu', 'quirks', 'passed', 'failed'}] -> known_machines entries (see the module text)."""
    by = collections.defaultdict(lambda: collections.defaultdict(lambda: [set(), set()]))
    for r in records:
        v = by[r["cpu"]][json.dumps(r["quirks"], sort_keys=True)]
        if r["passed"]:
            v[0].add(r["batch"])
        elif r["failed"]:
            v[1].add(r["batch"])
    out = []
    for cpu, variants in sorted(by.items()):
        stats = {q: (len(p), len(f), len(p | f), len(f - p) / max(1, len(p | f | f))) for q, (p, f) in variants.items()}
        stats = {q: (p, f, n, len(variants[q][1] - variants[q][0]) / n) for q, (p, f, n, _) in stats.items() if n}
        good = [q for q, (p, f, n, rate) in stats.items() if p >= min_pass and rate <= max_fail]
        if len(good) != 1:
            continue
        others = [(q, v) for q, v in stats.items() if q != good[0] and v[2] >= min_pass]
        if not others or any(v[3] < other_fail or v[3] < 2 * max(stats[good[0]][3], 0.001) for _, v in others):
            continue
        p, f, n, rate = stats[good[0]]
        out.append({"board": "", "cpu": cpu, "status": "works", "booter_quirks": json.loads(good[0]),
                    "source": f"stick logs 10-11/2026: {p} batches passed the hand-off with these quirks and {f} did not; "
                              + "; ".join(f"the other set passed {v[0]} and failed {v[1]}" for _, v in others)})
    return out


def collect(folders):
    """One record per opencore-*.txt upload: its CPU, the quirks it ran with, and whether it passed the hand-off."""
    out = []
    for folder in folders:
        for meta in glob.glob(os.path.join(folder, "*.json")):
            try:
                with open(meta, encoding="utf-8") as fh:
                    d = json.load(fh)
                if not str(d.get("original_name") or "").startswith("opencore-"):
                    continue
                with open(meta[:-5] + ".txt", errors="replace") as fh:
                    text = fh.read()
            except (OSError, ValueError):
                continue
            cpu = cpu_of(text)
            q = oc_quirks(text)
            if not cpu or not q:
                continue
            f = bootfix.findings([text])
            out.append({"batch": d.get("batch"), "cpu": cpu, "quirks": q, "passed": bool(f["macos_disk"]), "failed": bool(f["stop16"])})
    return out


def merge(existing, new):
    have = {(m["board"].lower(), m["cpu"].lower()) for m in existing}
    return existing + [m for m in new if (m["board"].lower(), m["cpu"].lower()) not in have]


def main(argv):
    folders = [a for a in argv if not a.startswith("--")]
    entries = aggregate(collect(folders))
    with open(KNOWN, encoding="utf-8") as fh:
        table = json.load(fh)
    merged = merge(table["machines"], entries)
    print(f"{len(entries)} CPU(s) qualify; {len(merged) - len(table['machines'])} new")
    for m in entries:
        print(f"  {m['cpu']} | {m['booter_quirks']} | {m['source']}")
    if "--write" in argv:
        table["machines"] = merged
        tmp = KNOWN + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(table, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, KNOWN)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
