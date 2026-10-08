"""Records every build dependency the engine can fetch, for the content-addressed mirror (p1401/mirror.py).

python3 tools/record_mirror.py <out dir>

Runs the engine's own fetch code against the real network with every kext selected, keeps each response body as the
bytes the engine reads (content encoding removed), reduces release index pages to their first tag link, and writes <out dir>/files/<sha256> for each plus
<out dir>/mirror.json. For a release, mirror.json goes to p1401/ and files/ to the server's /srv/nullmoth/mirror/
(files are never removed there, so every earlier release keeps its mirror). Exits non-zero when anything the engine
would need could not be recorded, and names it."""
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
    # iasl is not recorded: the Windows package ships iasl.exe (windows/App/Engine.cs), so a build never downloads it.

    os.makedirs(os.path.join(out, "files"), exist_ok=True)
    from p1401.mirror_metadata import release_index
    entries = {}
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
    return 0 if not failures else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(os.path.abspath(sys.argv[1])))
