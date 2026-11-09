#!/usr/bin/env python3
"""Does one AMD kernel-patch list cover another?

Usage: compare_amd_kernel_patches.py <reference patches.plist> <candidate patches.plist>

Both are OpenCore property lists with Kernel > Patch (the shape OpCore-Simplify downloads at build time). A reference patch
is covered when the candidate holds patches with the same target (identifier, base symbol), the same find/replace bytes
and masks, and kernel ranges whose union spans the reference patch's range. A list that only splits a patch over
several kernel versions therefore covers the original. Prints the uncovered reference patches and exits 1 when there
are any, so 1401's build can check a patch source against the list it replaces.
"""
import plistlib
import sys


def ver(s):
    s = (s or "").strip()
    return tuple(int(x) for x in s.split(".")) if s else None


def ident(p):
    return (p.get("Identifier"), p.get("Base"), bytes(p.get("Find", b"")), bytes(p.get("Replace", b"")),
            bytes(p.get("Mask", b"")), bytes(p.get("ReplaceMask", b"")), p.get("Count"), p.get("Skip"), p.get("Limit"))


def rng(p):
    lo = ver(p.get("MinKernel")) or (0,)
    hi = ver(p.get("MaxKernel")) or (999, 0, 0)
    return lo, hi


def covered(ref, group):
    """True when the (lo, hi) ranges of 'group' leave no gap inside ref's range. A range written as 24.99.99 means 'to
    the end of Darwin 24', so the next range starts at 25.0.0; the helper below turns an end into the first version
    after it."""
    lo, hi = ref
    cur = lo
    for a, b in sorted(group):
        if a > cur:
            return False
        if b >= cur:
            cur = _after(b)
        if cur > hi:
            return True
    return cur > hi


def _after(v):
    major, minor, patch = (list(v) + [0, 0])[:3]
    if minor >= 99 and patch >= 99:
        return (major + 1, 0, 0)
    if patch >= 99:
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


def load(path):
    with open(path, "rb") as fh:
        return [p for p in plistlib.load(fh)["Kernel"]["Patch"] if p.get("Enabled", True)]


def missing(reference, candidate):
    groups = {}
    for p in candidate:
        groups.setdefault(ident(p), []).append(rng(p))
    return [p for p in reference if not covered(rng(p), groups.get(ident(p), []))]


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    ref, cand = load(argv[1]), load(argv[2])
    gaps = missing(ref, cand)
    print(f"reference {len(ref)} patches, candidate {len(cand)}: {len(gaps)} not covered")
    for p in gaps:
        print(f"  {p.get('Comment')}  [{p.get('MinKernel') or '*'} .. {p.get('MaxKernel') or '*'}]")
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
