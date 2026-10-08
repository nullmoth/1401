"""Gets macOS from Apple straight onto the user's machine. 1401 never hosts, mirrors, or ships any Apple files.

Protocol: Apple Internet Recovery (osrecovery.apple.com), as implemented by OpenCorePkg's macrecovery.py
(Copyright (c) 2019, vit9696, BSD-3-Clause; the chunklist format and Apple's EFI ROM public key below come from
it, see NOTICE.md). The recovery image goes on a FAT32 USB at com.apple.recovery.boot/ next to the EFI, the only
installer layout Windows can write without an HFS+ driver. Recovery then installs macOS from Apple over the network.

The image and chunklist come over plain HTTP (Apple's URLs), so the transport isn't trusted. The chunklist is
RSA-signed with Apple's EFI ROM key and every chunk of the image is sha256-checked against it while it streams.
An unsigned chunklist (signature method 2) is refused.

Not importing macrecovery.py because its run_query calls sys.exit(1) on any HTTP error (which kills a GUI) and
get_session returns Ellipsis if Apple's first Set-Cookie isn't session=. Here errors raise with the reason.

    python3 -m p1401.apple probe [darwin-major ...]   # metadata + signed chunklist + chunk 0, no multi-GB download
    python3 -m p1401.apple --selftest
"""
import hashlib
import http.client
import json
import os
import random
import string
import socket
import struct
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
from . import tls
tls.install()   # downloads verify against the OS certificate store + certifi

TIMEOUT = 60  # seconds per request
MLB_ZERO = "00000000000000000"  # the generic MLB: Apple serves that board's newest recovery image
UA = "InternetRecovery/1.0"

# Darwin major -> (macOS name, board-id). The board-ids are the ones Dortania's install guide uses. The selftest
# checks each against boards.json from the pinned OpenCore release in case a board stops getting that OS.
TARGETS = {
    25: ("macOS 26 Tahoe", "Mac-CFF7D910A743CAAF"),
    24: ("macOS 15 Sequoia", "Mac-937A206F2EE63C01"),
    23: ("macOS 14 Sonoma", "Mac-827FAC58A8FDFA22"),
    22: ("macOS 13 Ventura", "Mac-4B682C642B45593E"),
    21: ("macOS 12 Monterey", "Mac-FFE5EF870D7BA81A"),
    20: ("macOS 11 Big Sur", "Mac-42FD25EABCABB274"),
    19: ("macOS 10.15 Catalina", "Mac-00BE6ED71E35EB86"),
}
MAJOR = {25: "26", 24: "15", 23: "14", 22: "13", 21: "12", 20: "11", 19: "10.15"}

# From macrecovery.py (zhangyoufu, gist MCJack123/943eaca762730ca4b7ae460b731b68e7, 2021-10-08): Apple EFI ROM key 1.
APPLE_EFI_ROM_KEY_1 = int(
    "C3E748CAD9CD384329E10E25A91E43E1A762FF529ADE578C935BDDF9B13F2179D4855E6FC89E9E29CA12517D17DFA1EDCE0BEBF0EA7B461FFE"
    "61D94E2BDF72C196F89ACD3536B644064014DAE25A15DB6BB0852ECBD120916318D1CCDEA3C84C92ED743FC176D0BACA920D3FCF3158AFF731"
    "F88CE0623182A8ED67E650515F75745909F07D415F55FC15A35654D118C55A462D37A3ACDA08612F3F3F6571761EFCCBCC299AEE99B3A4FD62"
    "12CCFFF5EF37A2C334E871191F7E1C31960E010A54E86FA3F62E6D6905E1CD57732410A3EB0C6B4DEFDABE9F59BF1618758C751CD56CEF851D"
    "1C0EAA1C558E37AC108DA9089863D20E2E7E4BF475EC66FE6B3EFDCF", 16)
HEADER = struct.Struct("<4sIBBBxQQQ")
CHUNK = struct.Struct("<I32s")


class AppleError(RuntimeError):
    pass


# Write failures on 6 machines in one day were Apple's servers dropping a connection once: osrecovery answered
# "RemoteDisconnected", oscdn reset the chunklist request (WinError 10054), or the image stream ended mid-chunk. Each
# was a whole failed stick. Transient connection errors are retried; HTTP errors (a refused token, a 404) are not.
OPEN_TRIES = 4
RESUMES = 8


def _transient(e):
    if isinstance(e, urllib.error.HTTPError):
        return e.code in (500, 502, 503, 504)
    return isinstance(e, (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError, socket.timeout))


def _open(url, headers, data=None, sleep=None):
    req = urllib.request.Request(url, headers={"Connection": "close", "User-Agent": UA, **headers}, data=data)
    for attempt in range(OPEN_TRIES):
        try:
            return urllib.request.urlopen(req, timeout=TIMEOUT)
        except Exception as e:  # keep the URL so the UI can show what failed
            if attempt + 1 < OPEN_TRIES and _transient(e):
                (sleep or time.sleep)(2 ** (attempt + 1))
                continue
            raise AppleError(f"{url}: {type(e).__name__}: {e}") from e


def _hex(n):
    return "".join(random.choices(string.hexdigits[:16].upper(), k=n))


def session():
    r = _open("http://osrecovery.apple.com/", {"Host": "osrecovery.apple.com"})
    for k, v in r.headers.items():
        if k.lower() == "set-cookie":
            for c in v.split("; "):
                if c.startswith("session="):
                    return c
    raise AppleError(f"osrecovery gave no session cookie (headers: {dict(r.headers)})")


def image_info(darwin_major, sess=None):
    """Asks Apple which recovery image serves this macOS. Returns URLs + tokens; downloads nothing."""
    if darwin_major not in TARGETS:
        raise AppleError(f"no recovery target for Darwin {darwin_major}")
    name, board = TARGETS[darwin_major]
    post = {"cid": _hex(16), "sn": MLB_ZERO, "bid": board, "k": _hex(64), "fg": _hex(64), "os": "latest"}
    r = _open("http://osrecovery.apple.com/InstallationPayload/RecoveryImage",
              {"Host": "osrecovery.apple.com", "Cookie": sess or session(), "Content-Type": "text/plain"},
              "\n".join(f"{k}={v}" for k, v in post.items()).encode())
    info = dict(l.split(": ", 1) for l in r.read().decode().splitlines() if ": " in l)
    missing = [k for k in ("AP", "AU", "AH", "AT", "CU", "CH", "CT") if k not in info]
    if missing:
        raise AppleError(f"Apple's answer for {board} lacks {missing}")
    return {"name": name, "board": board, "product": info["AP"], "image_url": info["AU"], "image_token": info["AT"],
            "chunklist_url": info["CU"], "chunklist_token": info["CT"]}


def _asset(url, token, extra=None):
    return _open(url, {"Host": urlparse(url).hostname, "Cookie": "AssetToken=" + token, **(extra or {})})


def parse_chunklist(data):
    """Signed chunklist bytes -> [(size, sha256)]. Raises unless Apple's EFI ROM key signed exactly these bytes."""
    if len(data) < HEADER.size:
        raise AppleError("chunklist truncated")
    magic, hsize, ver, cmethod, smethod, count, coff, soff = HEADER.unpack_from(data)
    if (magic, hsize, ver, cmethod, coff) != (b"CNKL", HEADER.size, 1, 1, HEADER.size) or count <= 0 \
            or soff != coff + CHUNK.size * count:
        raise AppleError(f"not an Apple chunklist (magic={magic!r} version={ver} chunks={count})")
    if smethod != 1:
        # method 2 is a bare sha256 anyone can compute: it proves nothing about who made the image
        raise AppleError(f"chunklist signature method {smethod} is not Apple-signed - refused")
    body = data[:soff]
    sig = data[soff:]
    if len(sig) != 256:
        raise AppleError(f"chunklist signature is {len(sig)} bytes, want 256")
    digest = hashlib.sha256(body).digest()
    want = int("1" + "f" * 404 + "003031300d060960864801650304020105000420" + "0" * 64, 16) | int.from_bytes(digest, "big")
    if pow(int.from_bytes(sig, "little"), 0x10001, APPLE_EFI_ROM_KEY_1) != want:
        raise AppleError("chunklist signature does not verify against Apple's EFI ROM key - refused")
    return [CHUNK.unpack_from(data, coff + i * CHUNK.size) for i in range(count)]


def fetch_chunklist(info):
    return _asset(info["chunklist_url"], info["chunklist_token"]).read()


def download(info, usb_root, progress=None):
    """Streams the recovery image into <usb_root>/com.apple.recovery.boot/, checking every chunk as it arrives.
    Writes to .part files and only renames them after the last chunk checks out, so a half image never looks done."""
    dest = os.path.join(usb_root, "com.apple.recovery.boot")
    os.makedirs(dest, exist_ok=True)
    cl = fetch_chunklist(info)
    chunks = parse_chunklist(cl)
    total = sum(s for s, _ in chunks)
    img = os.path.join(dest, os.path.basename(urlparse(info["image_url"]).path))
    cnk = os.path.splitext(img)[0] + ".chunklist"
    done = 0
    resumes = 0
    r = _asset(info["image_url"], info["image_token"])
    try:
        with open(img + ".part", "wb") as fh:
            for i, (size, sha) in enumerate(chunks, 1):
                while True:
                    try:
                        buf = _read_exact(r, size)
                        break
                    except (AppleError, OSError, http.client.HTTPException) as e:
                        # The stream dropped: ask for the rest from the last chunk that checked out. Every byte is
                        # still checked against Apple's signed chunklist, so a resumed stream cannot change the image.
                        resumes += 1
                        if resumes > RESUMES:
                            raise AppleError(f"{e} (after {RESUMES} resumed connections)") from None
                        r.close()
                        r = _resume(info, done)
                if hashlib.sha256(buf).digest() != sha:
                    raise AppleError(f"chunk {i}/{len(chunks)} of {info['product']} fails Apple's hash - download refused")
                fh.write(buf)
                done += size
                if progress:
                    progress(done, total)
            if r.read(1):
                raise AppleError("image is larger than its signed chunklist - refused")
    finally:
        r.close()
    with open(cnk + ".part", "wb") as fh:
        fh.write(cl)
    os.replace(img + ".part", img)
    os.replace(cnk + ".part", cnk)
    return {"image": img, "chunklist": cnk, "bytes": total, "chunks": len(chunks)}


def _resume(info, offset):
    time.sleep(2)
    r = _asset(info["image_url"], info["image_token"], {"Range": f"bytes={offset}-"})
    got = (r.headers.get("Content-Range") or "") if getattr(r, "headers", None) else ""
    if getattr(r, "status", None) != 206 or not got.startswith(f"bytes {offset}-"):
        r.close()
        raise AppleError(f"Apple's server would not resume the image at byte {offset} (status {getattr(r, 'status', '?')})")
    return r


def _read_exact(r, n):
    parts, got = [], 0
    while got < n:
        b = r.read(min(n - got, 1 << 20))
        if not b:
            raise AppleError(f"stream ended at {got}/{n} bytes of a chunk")
        parts.append(b)
        got += len(b)
    return b"".join(parts)


def probe(darwin_major, sess=None):
    """Quick end-to-end check: Apple's metadata, the signed chunklist, and chunk 0 of the real image (~10 MB, not GBs)."""
    info = image_info(darwin_major, sess)
    chunks = parse_chunklist(fetch_chunklist(info))
    size0, sha0 = chunks[0]
    with _asset(info["image_url"], info["image_token"], {"Range": f"bytes=0-{size0 - 1}"}) as r:
        c0 = _read_exact(r, size0)
    return {**info, "chunks": len(chunks), "bytes": sum(s for s, _ in chunks),
            "chunk0_ok": hashlib.sha256(c0).digest() == sha0, "chunk0": c0, "chunklist": fetch_chunklist(info)}


def _boards_json():
    import zipfile  # noqa: PLC0415
    from . import validate  # noqa: PLC0415
    url, sha = validate._opencore_release()
    z = os.path.join(validate.CACHE, os.path.basename(url))
    if not os.path.exists(z) or validate._sha256(z) != sha:
        validate.ocvalidate_path()  # fetches + verifies the same pinned zip
    with zipfile.ZipFile(z) as zf:
        return json.loads(zf.read(next(m for m in zf.namelist() if m.endswith("macrecovery/boards.json"))))


def selftest():
    res = []

    def arm(name, cond, shown):
        res.append(bool(cond))
        print(("ok   " if cond else "FAIL ") + name + f"  [{shown}]")

    boards = _boards_json()
    bad = {d: (b, boards.get(b)) for d, (_, b) in TARGETS.items()
           if not str(boards.get(b, "")).startswith(MAJOR[d] + ".") and boards.get(b) != MAJOR[d]}
    arm("each board-id's newest OS in boards.json is the macOS we use it for", not bad, bad or "7/7")

    p = probe(25)
    arm("Apple's Tahoe chunklist verifies against Apple's EFI ROM key", p["chunks"] > 0,
        f"{p['product']} {p['chunks']} chunks {p['bytes'] / 2**30:.2f} GiB")
    arm("chunk 0 of the real Tahoe image matches its signed hash", p["chunk0_ok"], f"{len(p['chunk0'])} bytes")

    cl = bytearray(p["chunklist"])
    cl[HEADER.size + 4] ^= 1  # one bit of chunk 0's recorded hash
    try:
        parse_chunklist(bytes(cl))
        fired = False
    except AppleError:
        fired = True
    arm("chunklist with one flipped bit is refused (signature covers it)", fired, "refused" if fired else "ACCEPTED")

    cl = bytearray(p["chunklist"])
    cl[10] = 2  # signature method -> 2 (bare sha256)
    try:
        parse_chunklist(bytes(cl))
        fired = False
    except AppleError as e:
        fired = "not Apple-signed" in str(e)
    arm("unsigned (method 2) chunklist is refused", fired, "refused" if fired else "ACCEPTED")

    c0 = bytearray(p["chunk0"])
    c0[len(c0) // 2] ^= 1
    size0, sha0 = parse_chunklist(p["chunklist"])[0]
    arm("image chunk 0 with one flipped bit fails its hash", hashlib.sha256(bytes(c0)).digest() != sha0, "mismatch")

    s = session()
    rows = []
    for d in sorted(TARGETS, reverse=True):
        try:
            i = image_info(d, s)
            rows.append(f"{MAJOR[d]}:{i['product']}")
        except AppleError as e:
            rows.append(f"{MAJOR[d]}:FAILED {e}")
    arm("Apple serves a recovery image for every target (Catalina -> Tahoe)", all("FAILED" not in r for r in rows), " ".join(rows))
    print(f"\n{sum(res)}/{len(res)} passed")
    return all(res)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    if len(sys.argv) > 1 and sys.argv[1] == "probe":
        for d in [int(x) for x in sys.argv[2:]] or sorted(TARGETS, reverse=True):
            p = probe(d)
            print(f"{p['name']:<22} {p['product']:<16} {p['bytes'] / 2**30:.2f} GiB {p['chunks']} chunks  chunk0 "
                  f"{'ok' if p['chunk0_ok'] else 'FAIL'}  {p['image_url']}")
