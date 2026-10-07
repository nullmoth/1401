#!/usr/bin/env python3
"""Run 1401 over every corpus report (one subprocess each - the engine keeps module-level state that
must not leak from one machine into the next). Prints one row per machine.

    python3 tests/run_corpus.py plan            # planning only, no downloads
    python3 tests/run_corpus.py build           # full build + validate into out/corpus/<slug>
"""
import json, os, subprocess, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(REPO, "tests", "corpus", "cache")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "plan"
    only = sys.argv[2:]
    rows = []
    for slug in sorted(os.listdir(CACHE)):
        d = os.path.join(CACHE, slug)
        acpi = os.path.join(d, "ACPI")
        if only and slug not in only:
            continue
        if not os.listdir(acpi):
            rows.append((slug, "SKIP", "no ACPI dump in corpus", "", "", 0))
            continue
        args = [sys.executable, "-m", "p1401", mode, os.path.join(d, "Report.json"), acpi]
        if mode == "build":
            out = os.path.join(REPO, "out", "corpus", slug)
            args.append(out)
        t = time.time()
        p = subprocess.run(args + ["--json"], cwd=REPO, capture_output=True, text=True, timeout=900)
        dt = time.time() - t
        try:
            r = json.loads(p.stdout)
        except Exception:
            rows.append((slug, "CRASH", (p.stderr or p.stdout).strip().splitlines()[-1][:160] if (p.stderr or p.stdout).strip() else "no output", "", "", dt))
            continue
        rows.append((slug, "OK" if r["ok"] else "FAIL", r["error"][:160], r["macos_version"], r["smbios"], dt,
                     r.get("needs_oclp"), [x["prompt"][:40] + "->" + x["answer"] for x in r["decisions"]], r.get("validation")))
    for row in rows:
        slug, st, err, mv, sm, dt = row[:6]
        print(f"{slug:<22} {st:<5} {dt:5.1f}s macOS={mv:<9} {sm:<14} {'OCLP' if len(row) > 6 and row[6] else ''} {err}")
        if len(row) > 7:
            for dec in row[7]:
                print(f"{'':30}decided {dec}")
        if len(row) > 8 and row[8]:
            print(f"{'':30}validation: {row[8]}")
    bad = [r for r in rows if r[1] not in ("OK", "SKIP")]
    print(f"\n{len(rows) - len(bad)}/{len(rows)} OK or skipped")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
