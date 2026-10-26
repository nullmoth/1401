"""Runs the EFI rules over uploaded stick configs and the OpenCore log each one sent with it, read-only.

python3 tools/efi_rules_corpus.py <incoming archive> [--since 2026-10-01]

For each upload batch with a stick-config and an opencore log: the CPU comes from the log's "OCCPU: Found" line, the
outcome from the same log (stopped in boot.efi at EB.MM.AKM, or reached the kernel hand-off). The board, GPU and target
macOS are not in either file, so rules keyed on them are not judged here. Prints, per rule: configs flagged, and the
EB.MM.AKM rate of flagged vs passing configs on the machines that rule applies to.
"""
import argparse
import collections
import glob
import json
import os
import plistlib
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from p1401 import bootfix, efi_rules  # noqa: E402

CPU_LINE = re.compile(r"OCCPU: Found (.+)")


def batches(root, since):
    by = collections.defaultdict(dict)
    for meta in glob.glob(os.path.join(root, "20*", "*.json")):
        if os.path.basename(os.path.dirname(meta)) < since:
            continue
        try:
            with open(meta, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        name, stored = d.get("original_name", ""), os.path.join(root, d.get("stored_as", ""))
        slot = "config" if name.startswith("stick-config") else "log" if name.startswith("opencore-") else None
        if slot and os.path.isfile(stored):
            # the newest of each per batch: a batch is one Send logs press, so they describe the same stick
            prev = by[d.get("batch") or d["id"]].get(slot)
            if not prev or d.get("received_utc", "") > prev[0]:
                by[d.get("batch") or d["id"]][slot] = (d.get("received_utc", ""), stored)
    return {b: v for b, v in by.items() if "config" in v and "log" in v}


def facts_from_log(text):
    m = CPU_LINE.search(text)
    name = m.group(1).strip() if m else ""
    vendor = "AMD" if "AMD" in name else "Intel" if "Intel" in name else ""
    hw = {"CPU": {"Manufacturer": vendor, "Processor Name": name, "Codename": ""}, "Motherboard": {"Chipset": "", "Platform": None}}
    f = efi_rules.facts_from_report(hw, "")
    f["laptop"] = None   # unknown from a log: a rule keyed on it is not judged
    return f, name


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--since", default="2026-01-01")
    a = ap.parse_args(argv)
    rules = efi_rules.load()
    rows, unreadable = [], collections.Counter()
    for b, v in batches(a.root, a.since).items():
        try:
            with open(v["config"][1], "rb") as fh:
                cfg = plistlib.load(fh)
            with open(v["log"][1], encoding="utf-8", errors="replace") as fh:
                log = fh.read()
        except Exception as e:  # noqa: BLE001 - counted and printed, never dropped silently
            unreadable[type(e).__name__] += 1
            continue
        facts, cpu = facts_from_log(log)
        if not facts["cpu_vendor"]:
            unreadable["no CPU line"] += 1
            continue
        akm = bootfix.findings([log])["stop16"]
        handoff = "EXITBS:START" in log
        flagged = {i["id"] for i in efi_rules.check(cfg, facts, "stick", rules)}
        applies = {r["id"] for r in rules["rules"] if "stick" in r["scope"] and efi_rules.matches(r["match"], facts)}
        rows.append({"cpu": cpu, "akm": akm, "handoff": handoff, "flagged": flagged, "applies": applies,
                     "day": os.path.basename(os.path.dirname(v["config"][1]))})
    print(f"batches judged: {len(rows)}   unreadable: {dict(unreadable)}")
    print(f"overall: {sum(r['akm'] for r in rows)} stopped at EB.MM.AKM, {sum(r['handoff'] and not r['akm'] for r in rows)} reached the hand-off")
    print(f"configs with no issue: {sum(not r['flagged'] for r in rows)}")
    print(f"{'rule':34} {'applies':>7} {'flagged':>7} {'AKM if flagged':>15} {'AKM if passing':>15}")
    for r in rules["rules"]:
        rid = r["id"]
        on = [x for x in rows if rid in x["applies"]]
        if not on:
            continue
        fl = [x for x in on if rid in x["flagged"]]
        ok = [x for x in on if rid not in x["flagged"]]

        def rate(xs):
            return f"{sum(x['akm'] for x in xs)}/{len(xs)} {100 * sum(x['akm'] for x in xs) / len(xs):4.0f}%" if xs else "-"
        print(f"{rid:34} {len(on):7} {len(fl):7} {rate(fl):>15} {rate(ok):>15}")
    # A stick built by a current 1401 should pass; an issue that persists into the newest days is a builder or rule bug.
    print("\nby upload day: configs, with no issue, and the rules still flagged")
    for day in sorted({r["day"] for r in rows}):
        rs = [r for r in rows if r["day"] == day]
        c = collections.Counter(i for r in rs for i in r["flagged"])
        print(f"{day} {len(rs):5} {sum(not r['flagged'] for r in rs):5}  " + ", ".join(f"{k} {v}" for k, v in c.most_common(4)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
