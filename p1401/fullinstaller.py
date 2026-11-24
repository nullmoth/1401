"""The full macOS installer, for a stick that installs without downloading 18 GB inside Recovery.

Why. Recovery's Data volume is a 5 GB RAM disk. The online installer downloads the whole system (18 GB on macOS 26) into
it and fails (1401 #127, #112). Apple publishes the full installer as InstallAssistant.pkg in its software-update
catalog. Installed with `installer -pkg ... -target <disk>` it streams its payload to the target disk, not to the RAM disk,
and leaves "Install macOS <name>.app" there, which then installs without the network.

What this module does, offline-testable end to end:
  1. parse_catalog(): Apple's sucatalog (plain or gzip) into installer products: title, version, build, the
     InstallAssistant.pkg URL, size and digest.
  2. choose(): the newest product for a macOS major (15 or 26).
  3. fetch(): download with byte-range resume, size check, the catalog's digest when it has one, and verify_xar().
  4. verify_xar(): the package is a xar archive. The table of contents is read, its own checksum is checked, and every
     file's archived checksum is checked while streaming, so a damaged or swapped download is refused. The signature
     chain is not checked here: macOS's installer checks it when it opens the package.
  5. layout(): what goes on the stick's second partition (exFAT, label NMINSTALL), and the diskpart text that makes it.
     The first partition stays the small FAT32 one that carries OpenCore and the recovery image.
Nothing here runs unless the user picks the full installer; the default stick is unchanged.
"""
import gzip
import hashlib
import os
import plistlib
import re
import struct
import urllib.request
import zlib
import xml.etree.ElementTree as ET

CATALOG_URLS = {
    26: "https://swscan.apple.com/content/catalogs/others/index-26-15-14-13-12-10.16-10.15-10.14-10.13-10.12-10.11-10.10-10.9-mountainlion-lion-snowleopard-leopard.merged-1.sucatalog.gz",
    15: "https://swscan.apple.com/content/catalogs/others/index-15-14-13-12-10.16-10.15-10.14-10.13-10.12-10.11-10.10-10.9-mountainlion-lion-snowleopard-leopard.merged-1.sucatalog.gz",
}
PACKAGE_NAME = "InstallAssistant.pkg"
LABEL = "NMINSTALL"
FIRST_PARTITION = 2 * (1 << 30)    # OpenCore, drivers and the recovery image fit in 2 GiB; the rest of the stick is the data partition
# A stick sold as "32 GB" holds 32 * 10**9 bytes, about 29.8 GiB; the 3.0 limit of 32 GiB refused every one of them
# (#173, where a user patched the check down to 25 GB and the install worked). The package is 17-19 GB and the first
# partition takes 2 GiB, so 28 * 10**9 bytes leaves room with any "32 GB" stick and still refuses a 16 GB one.
MIN_STICK = 28 * 10**9


class FullInstallerError(RuntimeError):
    pass


# --- the catalog ---------------------------------------------------------------------------------------------------

def _dist_field(text, key):
    m = re.search(r"<key>%s</key>\s*<string>([^<]*)</string>" % re.escape(key), text)
    return m.group(1).strip() if m else ""


def parse_distribution(text):
    """(title, version, build) from a product's distribution file; empty strings where it does not say."""
    title = re.search(r"<title>([^<]*)</title>", text)
    return (title.group(1).strip() if title else "", _dist_field(text, "VERSION"), _dist_field(text, "BUILD"))


def parse_catalog(data, distributions=None):
    """Installer products in an Apple software-update catalog: [{product, title, version, build, url, size, digest, date}].
    `data` is the plist bytes, gzip-compressed or not. `distributions` maps a distribution URL to its text when the caller
    has fetched them (the catalog itself carries neither the title nor the version)."""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    try:
        cat = plistlib.loads(data)
    except Exception as e:  # noqa: BLE001 - any parse failure is the same answer for the user
        raise FullInstallerError(f"the software-update catalog could not be read ({type(e).__name__})") from None
    out = []
    for pid, p in (cat.get("Products") or {}).items():
        pkg = next((x for x in p.get("Packages") or [] if str(x.get("URL", "")).endswith("/" + PACKAGE_NAME)), None)
        if not pkg or not str(pkg.get("URL", "")).startswith("https://"):
            continue
        dist_url = next(iter((p.get("Distributions") or {}).values()), "")
        title, version, build = parse_distribution((distributions or {}).get(dist_url, ""))
        out.append({"product": pid, "title": title, "version": version, "build": build, "url": pkg["URL"],
                    "size": int(pkg.get("Size") or 0), "digest": (pkg.get("Digest") or "").lower(),
                    "integrity_url": str(pkg.get("IntegrityDataURL") or ""),
                    "integrity_size": int(pkg.get("IntegrityDataSize") or 0),
                    "date": str(p.get("PostDate") or ""), "distribution": dist_url})
    return out


def _vkey(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)) or (0,)


def choose(products, major):
    """The newest product whose version starts with this macOS major, or None."""
    mine = [p for p in products if p["version"].split(".")[0] == str(major)]
    return max(mine, key=lambda p: (_vkey(p["version"]), p["date"])) if mine else None


# --- the package ---------------------------------------------------------------------------------------------------

XAR_MAGIC = b"xar!"


def _alg(name):
    return {"sha1": hashlib.sha1, "sha256": hashlib.sha256, "sha512": hashlib.sha512, "md5": hashlib.md5}.get(name.lower())


def read_toc(fh):
    """(files, heap_offset, toc_checksum_ok) from an open xar. files: [{name, offset, length, size, alg, digest}] for
    regular files, offsets relative to the heap. Raises FullInstallerError for anything that is not a well-formed xar."""
    head = fh.read(28)
    if len(head) < 28 or head[:4] != XAR_MAGIC:
        raise FullInstallerError("this is not a macOS installer package (no xar header)")
    size, _ver, clen, ulen, calg = struct.unpack(">HHQQI", head[4:28])
    fh.seek(size)
    ctoc = fh.read(clen)
    if len(ctoc) != clen or clen > 64 * (1 << 20):
        raise FullInstallerError("the package's table of contents is cut short")
    try:
        toc = zlib.decompress(ctoc, 0, 64 * (1 << 20))
        if b"<!DOCTYPE" in toc or b"<!ENTITY" in toc:   # a table of contents never declares entities; refuse the expansion tricks
            raise FullInstallerError("the package's table of contents is not a valid one")
        root = ET.fromstring(toc)
    except (zlib.error, ET.ParseError, ValueError):
        raise FullInstallerError("the package's table of contents is damaged") from None
    heap = size + clen
    # the TOC's own checksum sits first in the heap
    ck = root.find("./toc/checksum")
    toc_ok = True
    if ck is not None:
        fn = _alg(ck.get("style", ""))
        off, ln = int(ck.findtext("offset", "0")), int(ck.findtext("size", "0"))
        fh.seek(heap + off)
        stored = fh.read(ln)
        toc_ok = bool(fn) and fn(ctoc).digest() == stored
    files = []

    def walk(node, prefix):
        for f in node.findall("file"):
            name = prefix + (f.findtext("name") or "")
            if (f.findtext("type") or "") == "file":
                d = f.find("data")
                if d is not None:
                    ac = d.find("archived-checksum")
                    files.append({"name": name, "offset": int(d.findtext("offset", "0")), "length": int(d.findtext("length", "0")),
                                  "size": int(d.findtext("size", "0")), "alg": (ac.get("style") if ac is not None else ""),
                                  "digest": ((ac.text or "").strip().lower() if ac is not None else "")})
            walk(f, name + "/")
    walk(root.find("toc") if root.find("toc") is not None else root, "")
    return files, heap, toc_ok


def toc_digest(path):
    """SHA-1 of the package's compressed table of contents. This is what the catalog's Digest names - measured 11-23
    on a catalog package: Digest 9f35208a... = SHA-1 of the compressed TOC = the TOC checksum stored first in the heap,
    while the SHA-1 of the whole file is 3cee5a0c... . 1401 3.0 compared Digest with the whole file, so every
    full-installer download failed after 17 GB with "does not match Apple's digest" (#200, #174). The chain is
    complete without a whole-file hash: catalog Digest -> table of contents -> each file's checksum (verify_xar)."""
    with open(path, "rb") as fh:
        head = fh.read(28)
        if len(head) < 28 or head[:4] != XAR_MAGIC:
            raise FullInstallerError("this is not a macOS installer package (no xar header)")
        size, _ver, clen, _ulen, _calg = struct.unpack(">HHQQI", head[4:28])
        if clen > 64 * (1 << 20):
            raise FullInstallerError("the package's table of contents is not a valid one")
        fh.seek(size)
        ctoc = fh.read(clen)
    if len(ctoc) != clen:
        raise FullInstallerError("the package's table of contents is cut short")
    return hashlib.sha1(ctoc).hexdigest()


def parse_integrity(data):
    """Apple's InstallAssistant.pkg.integrityDataV1: a chunklist (CNKL, 10 MiB chunks, SHA-256 each) whose trailer is
    a plain SHA-256 of the body (method 2), not a signature. It comes over HTTPS from Apple's CDN with the size the
    catalog names, and is used only to find and fetch again the chunks a download damaged; whether the package is
    Apple's is decided by the catalog Digest and the checksums inside it. Returns [(offset, size, sha256)]."""
    if len(data) < 36:
        raise FullInstallerError("the installer's integrity data is cut short")
    magic, hsize, ver, cmethod, smethod, count, coff, soff = struct.unpack_from("<4sIBBBxQQQ", data)
    if (magic, hsize, ver, cmethod, smethod, coff) != (b"CNKL", 36, 1, 1, 2, 36) or count <= 0 \
            or soff != coff + 36 * count or len(data) != soff + 32:
        raise FullInstallerError("the installer's integrity data is not in the expected form")
    if hashlib.sha256(data[:soff]).digest() != data[soff:]:
        raise FullInstallerError("the installer's integrity data fails its own checksum")
    out, off = [], 0
    for i in range(count):
        size, sha = struct.unpack_from("<I32s", data, coff + 36 * i)
        out.append((off, size, sha))
        off += size
    return out


def repair(path, chunks, url, opener, progress=None, rounds=2):
    """Checks the file chunk by chunk and fetches the damaged ones again in place. Returns the number of chunks that
    were replaced; raises when a chunk is still wrong after `rounds` tries. A damaged 10 MiB chunk no longer costs the
    whole 17 GB download."""
    fixed = 0
    total = sum(s for _, s, _ in chunks)
    for attempt in range(rounds + 1):
        bad, done = [], 0
        with open(path, "rb") as fh:
            for off, size, sha in chunks:
                fh.seek(off)
                if hashlib.sha256(fh.read(size)).digest() != sha:
                    bad.append((off, size, sha))
                done += size
                if progress:
                    progress(done, total)
        if not bad:
            return fixed
        if attempt == rounds:
            raise FullInstallerError(f"{len(bad)} part(s) of the download are still damaged after fetching them again - "
                                     "something on this network or computer changes the download: turn off web/HTTP "
                                     "scanning in your antivirus, or connect through a phone hotspot or a VPN")
        with open(path, "r+b") as out:
            for off, size, _sha in bad:
                stream, _t = opener(url, off)
                try:
                    buf = b""
                    while len(buf) < size:
                        b = stream.read(min(1 << 20, size - len(buf)))
                        if not b:
                            break
                        buf += b
                finally:
                    close = getattr(stream, "close", None)
                    if close:
                        close()
                out.seek(off)
                out.write(buf)
                fixed += 1


def verify_xar(path, progress=None, chunk=4 << 20):
    """Checks the package's table of contents and every file's archived checksum. Returns the file names. Raises
    FullInstallerError naming what is wrong. Reads the package once, in order."""
    total = os.path.getsize(path)
    with open(path, "rb") as fh:
        files, heap, toc_ok = read_toc(fh)
        if not toc_ok:
            raise FullInstallerError("the package's table of contents fails its own checksum - the download is damaged")
        names = {f["name"] for f in files}
        if "Distribution" not in names and not any(n.endswith("Payload") for n in names):
            raise FullInstallerError("this package has no installer payload")
        done = 0
        for f in sorted(files, key=lambda x: x["offset"]):
            fn = _alg(f["alg"])
            if f["offset"] + f["length"] + heap > total:
                raise FullInstallerError(f"{f['name']} runs past the end of the file - the download is cut short")
            if not fn or not f["digest"]:
                continue
            h = fn()
            fh.seek(heap + f["offset"])
            left = f["length"]
            while left:
                b = fh.read(min(chunk, left))
                if not b:
                    raise FullInstallerError(f"{f['name']} is cut short")
                h.update(b)
                left -= len(b)
                done += len(b)
                if progress:
                    progress(done, total)
            if h.hexdigest() != f["digest"]:
                raise FullInstallerError(f"{f['name']} fails its checksum - the download is damaged")
    return sorted(names)


def fetch(product, dest_dir, progress=None, opener=None, tries=12, integrity_get=None):
    """Downloads product['url'] to dest_dir/InstallAssistant.pkg with resume, then verifies size, digest and structure.
    `opener(url, start)` returns (stream, total_or_None); the default is urllib with a Range header."""
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, PACKAGE_NAME)
    part = path + ".part"
    integrity = None
    iu = product.get("integrity_url") or ""
    if iu.startswith("https://"):
        try:
            data = (integrity_get or _http_get)(iu)
            if product.get("integrity_size") and len(data) != product["integrity_size"]:
                raise FullInstallerError(f"{len(data)} bytes, the catalog says {product['integrity_size']}")
            integrity = parse_integrity(data)
            if sum(s for _, s, _ in integrity) != int(product["size"]):
                raise FullInstallerError("it covers another size than the package")
        except (OSError, FullInstallerError) as error:
            print(f"(the installer's integrity data could not be used: {error}; damaged parts cannot be repaired)")
            integrity = None
    want = int(product["size"])
    opener = opener or _open_range
    last = None
    # A partial download is resumed only when it is for this same package. 3.0 resumed any .part it found: a part from
    # an earlier macOS build grew past this package's size (#161: "stopped at 19032695007 of 18388869343 bytes",
    # HTTP 416) or ended in a file that failed Apple's digest after 17 GB (#200).
    tag = part + ".for"
    mine = f"{product['url']}\n{want}\n{product.get('digest') or ''}\n"
    try:
        with open(tag, encoding="utf-8") as fh:
            same = fh.read() == mine
    except OSError:
        same = False
    if not same or (want and os.path.exists(part) and os.path.getsize(part) > want):
        if os.path.exists(part):
            os.remove(part)
        with open(tag, "w", encoding="utf-8") as fh:
            fh.write(mine)
    for _ in range(tries):
        have = os.path.getsize(part) if os.path.exists(part) else 0
        if want and have == want:
            break
        if want and have > want:
            os.remove(part)      # never append past the end; start this package again
            have = 0
        try:
            stream, _total = opener(product["url"], have)
            with open(part, "ab") as out:
                while True:
                    b = stream.read(1 << 20)
                    if not b:
                        break
                    out.write(b)
                    if progress:
                        progress(out.tell(), want)
        except OSError as e:
            last = e
            continue
    have = os.path.getsize(part) if os.path.exists(part) else 0
    if want and have != want:
        raise FullInstallerError(f"the download stopped at {have} of {want} bytes ({last or 'the server closed the connection'})")
    if integrity:
        try:
            repair(part, integrity, product["url"], opener)
        except (OSError, FullInstallerError) as error:
            raise FullInstallerError(f"the download is damaged and could not be repaired ({error}); "
                                     "it is kept, so pressing Next again continues from here") from None
    if product.get("digest") and toc_digest(part) != product["digest"]:
        os.remove(part)
        if os.path.exists(tag):
            os.remove(tag)
        raise FullInstallerError("the download does not match Apple's digest in the catalog; it was thrown away")
    try:
        verify_xar(part)
    except FullInstallerError:
        os.remove(part)
        raise
    os.replace(part, path)
    if os.path.exists(tag):
        os.remove(tag)
    return path


def _open_range(url, start):
    if not url.startswith("https://"):
        raise FullInstallerError("refusing a download address that is not https")
    req = urllib.request.Request(url, headers={"Range": f"bytes={start}-"} if start else {})
    r = urllib.request.urlopen(req, timeout=30)  # noqa: S310 - https only, checked above
    if start and r.status != 206:
        r.close()
        raise OSError("the server ignored the resume request")
    if start:
        # the bytes must continue exactly where the part ends; a range that starts elsewhere would corrupt the file
        m = re.match(r"bytes (\d+)-", r.headers.get("Content-Range") or "")
        if not m or int(m.group(1)) != start:
            r.close()
            raise OSError(f"the server resumed at {m.group(1) if m else 'an unstated offset'}, not at byte {start}")
    return r, None


# --- the stick -----------------------------------------------------------------------------------------------------

SCRIPT_NAME = "Install-macOS-from-this-disk.sh"
SCRIPT = r'''#!/bin/bash
# Run this in Recovery: Utilities > Terminal, then   bash /Volumes/NMINSTALL/Install-macOS-from-this-disk.sh "Macintosh HD"
# It installs the full macOS installer from this disk onto the disk you erased in Disk Utility, and starts it. Nothing is
# downloaded, and nothing is unpacked into Recovery's small memory disk: the package streams to the target disk.
set -u
PKG=/Volumes/NMINSTALL/InstallAssistant.pkg
T="/Volumes/${1:-Macintosh HD}"
[ -f "$PKG" ] || { echo "STOP: $PKG is not here. Is the NMINSTALL partition of the stick mounted?"; exit 1; }
[ -d "$T" ] || { echo "STOP: there is no disk called ${1:-Macintosh HD}. Erase one in Disk Utility (APFS) first, or give its name."; exit 1; }
echo "Installing the macOS installer onto $T (this takes several minutes)..."
/usr/sbin/installer -pkg "$PKG" -target "$T" || { echo "STOP: the installer package did not install."; exit 1; }
APP=$(ls -d "$T"/Applications/Install\ macOS*.app 2>/dev/null | head -1)
[ -n "$APP" ] || { echo "STOP: the installer app did not appear on $T."; exit 1; }
echo "Starting $APP ..."
exec "$APP/Contents/Resources/startosinstall" --agreetolicense --volume "$T" --nointeraction
'''
README = ("This partition holds Apple's full macOS installer ({name} {version}), so the install needs no download.\n"
          "In Recovery: erase a disk as APFS in Disk Utility, open Utilities > Terminal and run:\n"
          "  bash /Volumes/%s/%s \"Macintosh HD\"\n"
          "Replace Macintosh HD with the name you gave the disk.\n" % (LABEL, SCRIPT_NAME))


def layout(product):
    """{relative path: bytes or the source marker} for the data partition. The package itself is copied from its file."""
    return {SCRIPT_NAME: SCRIPT.encode(), "README.txt": README.format(name=product.get("title") or "macOS",
                                                                      version=product.get("version") or "").encode(),
            PACKAGE_NAME: None}


def diskpart_script(disk_number, letter, first_partition_mib):
    """The second partition: everything after the first one, exFAT (macOS Recovery reads and writes it, files over 4 GB
    are allowed), labelled NMINSTALL."""
    if not str(disk_number).isdigit() or not (letter[:1].isalpha() and len(letter) == 1):
        raise FullInstallerError("bad disk number or drive letter")
    return (f"select disk {int(disk_number)}\r\ncreate partition primary\r\nformat fs=exfat label={LABEL} quick\r\n"
            f"assign letter={letter.upper()}\r\nexit\r\n")


def check_stick(size_bytes):
    if size_bytes < MIN_STICK:
        raise FullInstallerError(f"the full installer needs a 32 GB stick or larger (at least {MIN_STICK // 10**9} GB); "
                                 f"this one holds {size_bytes / 10**9:.1f} GB")


def place(root, pkg_path, product, copy=None, progress=None):
    """Copies the package and the helper files onto the mounted data partition `root`, then reads the package back and
    compares its size and SHA-256 with the source, so a stick that loses writes is caught."""
    copy = copy or _copy_file
    lay = layout(product)
    for rel, data in lay.items():
        dst = os.path.join(root, rel)
        if data is None:
            copy(pkg_path, dst, progress)
        else:
            with open(dst, "wb") as fh:
                fh.write(data)
    src_h, dst_h = hashlib.sha256(), hashlib.sha256()
    for p, h in ((pkg_path, src_h), (os.path.join(root, PACKAGE_NAME), dst_h)):
        with open(p, "rb") as fh:
            for b in iter(lambda: fh.read(4 << 20), b""):
                h.update(b)
    if src_h.digest() != dst_h.digest():
        raise FullInstallerError("the package on the stick reads back different from the verified download - the stick lost data; use another stick")
    return sorted(lay)


def _copy_file(src, dst, progress=None):
    total = os.path.getsize(src)
    done = 0
    with open(src, "rb") as a, open(dst + ".part", "wb") as b:
        for chunk in iter(lambda: a.read(4 << 20), b""):
            b.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
        b.flush()
        os.fsync(b.fileno())
    os.replace(dst + ".part", dst)


# --- the command the Windows app runs -----------------------------------------------------------------------------

def latest(major, get=None):
    """Downloads the catalog and the distribution files of its installer products, and returns the newest one for `major`."""
    get = get or _http_get
    url = CATALOG_URLS.get(int(major))
    if not url:
        raise FullInstallerError(f"no full installer is offered for macOS {major}")
    prods = parse_catalog(get(url))
    dists = {}
    for p in prods:
        if p["distribution"].startswith("https://"):
            try:
                dists[p["distribution"]] = get(p["distribution"]).decode("utf-8", "replace")
            except OSError:
                pass
    prods = [dict(p, **dict(zip(("title", "version", "build"), parse_distribution(dists.get(p["distribution"], ""))))) for p in prods]
    best = choose(prods, major)
    if not best:
        raise FullInstallerError(f"Apple's catalog lists no full installer for macOS {major}")
    return best


def _http_get(url):
    if not url.startswith("https://"):
        raise FullInstallerError("refusing an address that is not https")
    with urllib.request.urlopen(url, timeout=30) as r:  # noqa: S310 - https only, checked above
        return r.read(64 << 20)


def cli_fetch(argv):
    """fetch <darwin major 24|25> <folder>: STEP/OK/PROGRESS/STOP lines for the window; prints the package path."""
    major = {24: 15, 25: 26}.get(int(argv[0]), int(argv[0]))
    try:
        p = latest(major)
        print(f"OK Apple's full installer for macOS {major}: {p['title']} {p['version']} ({p['build']}), {p['size'] / (1 << 30):.1f} GiB", flush=True)
        last = [-1]

        def prog(done, total):
            pct = int(done * 100 / total) if total else 0
            if pct != last[0]:
                last[0] = pct
                print(f"PROGRESS {pct} downloading the full macOS installer from Apple", flush=True)
        path = fetch(p, argv[1], progress=prog)
        print(f"OK verified {path}", flush=True)
        return 0
    except FullInstallerError as e:
        print(f"STOP 1401-FULL-INSTALLER: {e}", flush=True)
        return 1


if __name__ == "__main__":
    import sys
    raise SystemExit(cli_fetch(sys.argv[2:]) if len(sys.argv) > 2 and sys.argv[1] == "fetch" else 2)
