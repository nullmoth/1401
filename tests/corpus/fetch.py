#!/usr/bin/env python3
"""Fetch the 1401 test corpus: real Hardware Sniffer reports (Report.json + ACPI dump) from public repos.

Every entry is pinned to a commit, not a branch, so the corpus can't change under the tests. The first fetch
resolves HEAD and writes the sha back into manifest.json.

The reports aren't committed (tests/corpus/cache is ignored). They're other people's repos and machines; we fetch
them by commit and never redistribute them.

    python3 tests/corpus/fetch.py            # fetch every entry (GITHUB_TOKEN optional, raises the API limit)
    python3 tests/corpus/fetch.py --selftest
"""
import json
import os
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "manifest.json")
CACHE = os.path.join(HERE, "cache")
API = "https://api.github.com"
TIMEOUT = 30  # seconds


def _get(url, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": "1401-corpus"})
    tok = os.environ.get("GITHUB_TOKEN")
    if tok and url.startswith(API):
        req.add_header("Authorization", "Bearer " + tok)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read()
    return data if raw else json.loads(data)


def _contents(repo, path, ref):
    q = urllib.parse.quote(path) if path else ""
    return _get(f"{API}/repos/{repo}/contents/{q}?ref={ref}")


def resolve_commit(repo):
    info = _get(f"{API}/repos/{repo}")
    return _get(f"{API}/repos/{repo}/commits/{info['default_branch']}")["sha"]


def fetch_entry(e):
    """Download Report.json and ACPI/*.aml for one manifest entry into cache/<slug>. Returns a status string."""
    dest = os.path.join(CACHE, e["slug"])
    base = e["path"].strip("/")
    join = (lambda *p: "/".join(x for x in (base,) + p if x))
    os.makedirs(os.path.join(dest, "ACPI"), exist_ok=True)
    listing = {f["name"]: f for f in _contents(e["repo"], base, e["commit"])}
    if "Report.json" not in listing:
        return "NO Report.json at " + (base or "/")
    _write(os.path.join(dest, "Report.json"), _get(listing["Report.json"]["download_url"], raw=True))
    n = 0
    if "ACPI" in listing:
        for f in _contents(e["repo"], join("ACPI"), e["commit"]):
            if f["type"] == "file" and f["name"].lower().endswith((".aml", ".dat")):
                _write(os.path.join(dest, "ACPI", f["name"]), _get(f["download_url"], raw=True))
                n += 1
    return f"ok report + {n} ACPI tables"


def _write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def main():
    with open(MANIFEST) as fh:
        manifest = json.load(fh)
    changed = False
    for e in manifest["entries"]:
        if not e.get("commit"):
            e["commit"] = resolve_commit(e["repo"])
            changed = True
        try:
            status = fetch_entry(e)
        except Exception as ex:  # report it and keep going; one bad repo shouldn't hide the rest
            status = f"FAILED {type(ex).__name__}: {ex}"
        print(f"{e['slug']:<34} {e['commit'][:8]}  {status}")
    if changed:
        tmp = MANIFEST + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(manifest, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, MANIFEST)
        print("manifest: pinned new commits")


def selftest():
    ok = True

    def arm(name, cond, shown):
        nonlocal ok
        print(("ok   " if cond else "FAIL ") + name + f"  [{shown}]")
        ok &= bool(cond)

    with open(MANIFEST) as fh:
        m = json.load(fh)
    slugs = [e["slug"] for e in m["entries"]]
    arm("every slug is unique, so no report can overwrite another's cache", len(set(slugs)) == len(slugs), f"{len(slugs)} slugs")
    unpinned = [e["slug"] for e in m["entries"] if not e.get("commit")]
    arm("every entry is pinned to a commit (run fetch once to pin)", not unpinned, f"unpinned={unpinned}")
    return ok


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    main()
