"""Records every build dependency the engine can fetch, for the content-addressed mirror (p1401/mirror.py).

python3 tools/record_mirror.py <out dir>

Runs the engine's own fetch code against the real network with every kext selected, keeps each response body as the
bytes the engine reads (content encoding removed), reduces release index pages to their first tag link, and writes <out dir>/files/<sha256> for each plus
<out dir>/mirror.json. For a release, mirror.json goes to p1401/ and files/ to the server's /srv/nullmoth/mirror/
(files are never removed there, so every earlier release keeps its mirror). Only what p1401/licenses.json lets NullMoth
host is written, and each copyleft binary gets its source recorded beside it; the rest is listed as NOT HOSTED and the
engine keeps fetching it from its author. Exits non-zero when anything hostable could not be recorded, and names it."""
import copy
import gzip
import hashlib
import json
import os
import sys
import zlib

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)


def main(out):
    from p1401 import downloads, engine, mirror, scan
    engine._load_engine()
    mirror._state.update(entries={}, preferred=False)        # record from the origin only, never from a mirror
    recorded, failures = {}, []
    direct = downloads._direct

    def recording(fetcher, url, timeout=20):
        with direct(fetcher, url, timeout) as response:
            body = response.read()
            encoding = (response.info().get("Content-Encoding") or "").lower()
        if encoding == "gzip" or (encoding == "" and body[:2] == b"\x1f\x8b" and not url.endswith((".zip", ".gz"))):
            body = gzip.decompress(body)
        elif encoding == "deflate":
            body = zlib.decompress(body)
        recorded[url] = body
        return mirror.Response(body, url)
    downloads._direct = recording

    from Scripts.gathering_files import gatheringFiles
    from Scripts.datasets import kext_data
    g = gatheringFiles()
    kexts = []
    for k in kext_data.kexts:
        k = copy.copy(k)
        k.checked = True
        kexts.append(k)

    def get(url, sha=None, what=None):
        if not url or not url.startswith("https://"):
            failures.append(f"{what or '?'}: no usable URL ({url!r})")
            return
        try:
            data = downloads.make_request(g.fetcher, url).read()
        except Exception as error:  # noqa: BLE001 - every failure is named in the summary
            failures.append(f"{what or url}: {type(error).__name__}: {str(error)[:160]}")
            return
        if sha and hashlib.sha256(data).hexdigest() != sha:
            failures.append(f"{what or url}: SHA-256 differs from the one the engine checks - not recorded")
            recorded.pop(url, None)

    try:
        products = g.fetch_latest_products_info(kexts, {})
    except Exception as error:  # noqa: BLE001
        failures.append(f"product list: {type(error).__name__}: {error}")
        products = {}
    for name, product in sorted(products.items()):
        if isinstance(product, dict):
            get(product.get("url"), product.get("sha256"), name)
    for url in (g.ocbinarydata_url, g.amd_vanilla_patches_url, g.aquantia_macos_patches_url, g.hyper_threading_patches_url):
        get(url)
    get(scan.ACPIDUMP["url"], scan.ACPIDUMP["sha256"], "acpidump.exe")
    from p1401 import community
    for d in community.DRIVERS:                                  # every macOS build, not only the one registered
        for url, _size, sha in sorted(set(d["builds"].values())):
            get(url, sha, d["name"])

    # Host only what the licence allows (p1401/licenses.py). A copyleft binary is hosted only with its source beside it.
    from p1401 import licenses
    skipped = []
    for url in sorted(recorded):
        ok, reason, source = licenses.hostable(url)
        if not ok:
            skipped.append(reason)
            recorded.pop(url)
        elif source and source not in recorded:
            get(source, what=f"source of {url}")
            if source not in recorded:
                failures.append(f"{url}: its source {source} could not be recorded - binary not hosted")
                recorded.pop(url)
    # iasl is not recorded: the Windows package ships iasl.exe (windows/App/Engine.cs), so a build never downloads it.

    os.makedirs(os.path.join(out, "files"), exist_ok=True)
    from p1401.mirror_metadata import release_index
    # NullMoth's own builds (netsupport.py, amd_rdna4.py) are pinned into the manifest by hand, not fetched by the
    # engine, so they are carried over as they are, with their bytes taken from the mirror and checked against the pin.
    with open(mirror.MANIFEST, encoding="utf-8") as fh:
        entries = {u: e for u, e in json.load(fh)["entries"].items() if licenses.classify(u)[1] == "nullmoth"}
    for url, entry in sorted(entries.items()):
        path = os.path.join(out, "files", entry["sha256"])
        if not os.path.exists(path):
            try:   # straight from the server: the recording hook above would gunzip a .tar.gz served without a suffix
                import urllib.request
                with urllib.request.urlopen(mirror.BASE + entry["sha256"], timeout=60) as response:
                    body = response.read()
            except Exception as error:  # noqa: BLE001 - named in the summary
                failures.append(f"{url}: {type(error).__name__}: {str(error)[:160]}")
                continue
            if hashlib.sha256(body).hexdigest() != entry["sha256"] or len(body) != entry["size"]:
                failures.append(f"{url}: the mirror's bytes do not match the pin - not carried over")
                continue
            with open(path + ".tmp", "wb") as fh:
                fh.write(body)
            os.replace(path + ".tmp", path)
    for url, body in sorted(recorded.items()):
        original_sha = hashlib.sha256(body).hexdigest()
        body = release_index(url, body)
        sha = hashlib.sha256(body).hexdigest()
        path = os.path.join(out, "files", sha)
        if not os.path.exists(path):
            with open(path + ".tmp", "wb") as fh:
                fh.write(body)
            os.replace(path + ".tmp", path)
        entries[url] = {"sha256": sha, "size": len(body)}
        if sha != original_sha:
            entries[url].update(source_sha256=original_sha, metadata_kind="release-tag")
    manifest = os.path.join(out, "mirror.json")
    with open(manifest + ".tmp", "w") as fh:
        json.dump({"schema": mirror.SCHEMA, "entries": entries}, fh, indent=1, sort_keys=True)
        fh.write("\n")
    os.replace(manifest + ".tmp", manifest)
    total = sum(e["size"] for e in entries.values())
    print(f"recorded {len(entries)} URLs, {len(set(e['sha256'] for e in entries.values()))} files, {total / 2**20:.1f} MB")
    for f in failures:
        print("  NOT RECORDED  " + f)
    for reason in sorted(set(skipped)):
        print("  NOT HOSTED    " + reason)
    return 0 if not failures else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(os.path.abspath(sys.argv[1])))
