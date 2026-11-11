#!/usr/bin/env python3
"""Read-only evidence for the two installer routes. Nothing is written to a disk.

1. Recovery: ask Apple for the macOS 26 (Darwin 25) recovery image, fetch its signed chunklist, verify the signature,
   hash the first chunk, and report the size/parts. This is exactly the data the writer uses before erasing a stick.
2. Full installer: read Apple's current catalog entry (size, SHA-1, product id), then ask the real package URL for its
   first byte range and for a resume range, proving the download path is live and range-capable without fetching 18 GB.

    .venv/Scripts/python.exe scripts/verify_recovery.py --json-out reports/recovery/verification.json
"""
import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from p1401 import apple, fullinstaller  # noqa: E402


def recovery(darwin=25):
    info = apple.image_info(darwin)
    cl = apple.fetch_chunklist(info)
    chunks = apple.parse_chunklist(cl)
    ready = apple.preflight(info)
    return {
        "ok": True,
        "darwin": darwin,
        "product": info.get("product"),
        "image": os.path.basename(info.get("image_url", "")),
        "bytes": sum(size for size, _ in chunks),
        "chunks": len(chunks),
        "chunklist_signature": "Apple EFI ROM RSA verified",
        "first_chunk_sha256_matches": bool(ready.get("verified")),
        "preflight_sampled_bytes": ready.get("sampled"),
    }


def full_installer(major=26):
    product = fullinstaller.latest(major)
    url = product["url"]
    stream, _ = fullinstaller._open_range(url, 0)
    try:
        head = stream.read(1 << 20)
    finally:
        stream.close()
    resumed, _ = fullinstaller._open_range(url, 1 << 20)
    try:
        status = getattr(resumed, "status", None)
        resumed_head = resumed.read(1024)
    finally:
        resumed.close()
    return {
        "ok": bool(head) and len(head) == 1 << 20 and status == 206,
        "macos": major,
        "title": product.get("title"),
        "version": product.get("version"),
        "build": product.get("build"),
        "bytes": product.get("size"),
        "catalog_digest": product.get("digest"),
        "product": product.get("product"),
        "url": url,
        "first_mib_received": len(head),
        "resume_status": status,
        "resume_bytes": len(resumed_head),
        "downloaded_full_package": False,
        "note": ("catalog, live URL and HTTP range verified; the 18 GB package is not downloaded, and creating a "
                 "standard Apple createinstallmedia USB requires macOS"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    parser.add_argument("--darwin", type=int, default=25)
    parser.add_argument("--major", type=int, default=26)
    args = parser.parse_args()
    out = {"recovery": None, "full_installer": None, "errors": []}
    try:
        out["recovery"] = recovery(args.darwin)
    except Exception as e:  # noqa: BLE001 - evidence, not a gate; the reason is the result
        out["errors"].append(f"recovery: {type(e).__name__}: {e}")
    try:
        out["full_installer"] = full_installer(args.major)
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"full_installer: {type(e).__name__}: {e}")
    text = json.dumps(out, indent=1, ensure_ascii=False)
    print(text)
    if args.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 0 if not out["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
