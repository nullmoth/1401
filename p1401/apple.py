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
    18: ("macOS 10.14 Mojave", "Mac-7BA5B2D9E42DDD94"),
    17: ("macOS 10.13 High Sierra", "Mac-7BA5B2D9E42DDD94"),
}
MAJOR = {25: "26", 24: "15", 23: "14", 22: "13", 21: "12", 20: "11", 19: "10.15", 18: "10.14", 17: "10.13"}
# Before Catalina the generic MLB returns that board's newest OS, not the one asked for: Apple picks the image from a
# real board serial with os=default (Dortania's macrecovery commands). WAS missing: 18 High Sierra builds in two days
# (Maxwell/Pascal cards) stopped at "no recovery target for Darwin 17".
OLD_MLB = {18: "00000000000KXPG00", 17: "00000000000J80300"}

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
OPEN_TRIES = 6  # WAS 4: osrecovery answered 502 and timed out past 4 tries on 1.7 (10-10); 6 tries back off ~2 min in all
FORBIDDEN_TRIES = 3
# drops in a row with no new chunk verified. WAS 8 for the whole image: 78 writes in two days failed "after 8 resumed
# connections" while every resume was still making progress, on networks that drop a long stream every few minutes.
RESUMES = 8
RESUMES_TOTAL = 400
# After a network cuts the first stream, every later request asks for at most this many bytes. 1.3.0 logs (14 machines,
# 10-09): the first connection delivered exactly 1 MiB, then every resumed "bytes=N-" request (the ~887 MB rest of the
# image) delivered 0 bytes - a middlebox resetting large HTTP responses. Apple's CDN serves small ranges fine (measured
# 10-09: 206, byte-identical), so small windows get under the cap. Every chunk is still checked against the signed list.
WINDOW = 512 * 1024
# Once windowed, a network may hand out nothing for minutes before letting windows through again (1.5.0 logs 10-10: one
# write reached 8 MiB after 19 resumes, others gave up "after 9 resumed connections, 8 in a row with no progress" about
# 2.5 minutes in). In windowed mode allow this many empty connections in a row, backing off up to WINDOW_MAX_DELAY s each
# (about 15 minutes in all), and every REFRESH_EVERY empty connections ask osrecovery for a fresh image URL and token.
RESUMES_WINDOWED = 20
WINDOW_MAX_DELAY = 60
REFRESH_EVERY = 4


def _transient(e):
    if isinstance(e, urllib.error.HTTPError):
        return e.code in (500, 502, 503, 504)
    return isinstance(e, (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError, socket.timeout))


# Public DNS-over-HTTPS resolvers, tried in order. Alibaba's answers inside China, where the others may not.
DOH = ("https://dns.google/resolve?name={}&type=A", "https://cloudflare-dns.com/dns-query?name={}&type=A",
       "https://dns.alidns.com/resolve?name={}&type=1")
_doh_cache = {}


def _doh(host, fetch=None):
    """An IPv4 address for host from DNS-over-HTTPS, or None. The download still comes from Apple's own server."""
    if host in _doh_cache:
        return _doh_cache[host]
    import json  # noqa: PLC0415
    for tmpl in DOH:
        try:
            if fetch:
                body = fetch(tmpl.format(host))
            else:
                req = urllib.request.Request(tmpl.format(host), headers={"Accept": "application/dns-json", "User-Agent": UA})
                with urllib.request.urlopen(req, timeout=15) as r:
                    body = r.read(65536)
            for a in json.loads(body).get("Answer") or []:
                ip = str(a.get("data", ""))
                if a.get("type") == 1 and ip.count(".") == 3 and all(p.isdigit() and int(p) < 256 for p in ip.split(".")):
                    _doh_cache[host] = ip
                    return ip
        except Exception:  # noqa: BLE001 - the next resolver is tried; None means none answered
            continue
    return None


def _dns_failure(e):
    """The network could not reach the host by name or the connection was refused/reset before HTTP started."""
    r = getattr(e, "reason", e)
    return isinstance(r, (socket.gaierror, ConnectionRefusedError, ConnectionResetError))


def _open(url, headers, data=None, sleep=None, doh=None):
    # Write logs 10-10 (1.6-1.9): osrecovery.apple.com failed with getaddrinfo 11001, WinError 10061 (refused) and 10054
    # (reset) on networks whose DNS is broken or poisoned. Apple's recovery service and its CDN speak plain HTTP, so the
    # same request goes to the address DNS-over-HTTPS gives, with the real Host header; the image is still Apple's and is
    # still checked chunk by chunk against Apple's signed chunklist.
    req = urllib.request.Request(url, headers={"Connection": "close", "User-Agent": UA, **headers}, data=data)
    rerouted = False
    for attempt in range(OPEN_TRIES):
        try:
            return urllib.request.urlopen(req, timeout=TIMEOUT)
        except Exception as e:  # keep the URL so the UI can show what failed
            if not rerouted and url.startswith("http://") and _dns_failure(e):
                host = urlparse(url).hostname
                ip = (doh or _doh)(host)
                if ip:
                    rerouted = True
                    print(f"(could not reach {host} through this network's DNS; using {ip} from DNS-over-HTTPS)", flush=True)
                    req = urllib.request.Request(url.replace("//" + host, "//" + ip, 1),
                                                 headers={"Connection": "close", "User-Agent": UA, **headers, "Host": host}, data=data)
                    continue
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
    old = darwin_major in OLD_MLB
    # 403 here is osrecovery refusing that one session (23 Sequoia writes in two days, while 108 others passed):
    # ask again with a new session and new client ids before giving up
    for attempt in range(FORBIDDEN_TRIES):
        post = {"cid": _hex(16), "sn": OLD_MLB.get(darwin_major, MLB_ZERO), "bid": board, "k": _hex(64), "fg": _hex(64),
                "os": "default" if old else "latest"}
        try:
            r = _open("http://osrecovery.apple.com/InstallationPayload/RecoveryImage",
                      {"Host": "osrecovery.apple.com", "Cookie": (sess if attempt == 0 and sess else session()),
                       "Content-Type": "text/plain"},
                      "\n".join(f"{k}={v}" for k, v in post.items()).encode())
            break
        except AppleError as e:
            if "HTTP Error 403" not in str(e) or attempt + 1 == FORBIDDEN_TRIES:
                raise
            time.sleep(3 * (attempt + 1))
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
    resumes = stalled = 0
    window = 0       # 0 = ask for the rest of the image; WINDOW once the network has cut a stream
    conn_start = 0   # image offset where the current connection started
    # What each connection did, for the STOP line. 1.9.0 logs (10-10, 15 writes): "stream ended at 1048576 ... 20 in a row
    # with no progress" reported only the first drop, so nobody could tell whether the resumes got empty 206s, resets
    # or refusals.
    trail, t0 = [], time.monotonic()
    def note(s):
        trail.append(f"{time.monotonic() - t0:.0f}s {s}")
        del trail[1:-7]  # the first cut (how much one full stream got) plus the last seven
    r = _asset(info["image_url"], info["image_token"])
    try:
        with open(img + ".part", "wb") as fh:
            for i, (size, sha) in enumerate(chunks, 1):
                part = bytearray()
                while True:
                    before = len(part)
                    try:
                        _read_into(r, part, size)
                        break
                    except (AppleError, OSError, http.client.HTTPException) as e:
                        pos = done + len(part)
                        if not (window and pos - conn_start >= window):
                            note(f"connection at {conn_start} gave {pos - conn_start} B, then {type(e).__name__}")
                        if window and pos - conn_start >= window:
                            # windowed mode: this connection delivered its whole window - normal, open the next one
                            r.close()
                            r = _resume(info, pos, window, delay=0)
                            conn_start, stalled = pos, 0
                            continue
                        # The stream dropped: ask for the rest from the last byte received. Every byte is still
                        # checked against Apple's signed chunklist, so a resumed stream cannot change the image.
                        # WAS: resumed from the start of the chunk. Some networks close every connection after 1 MiB
                        # (1.2.0 logs: "stream ended at 1048576/10485760", 9 resumes), so each retry fetched the same
                        # first MiB of a 10 MiB chunk and the download never moved.
                        stalled = 1 if len(part) > before else stalled + 1  # a connection that added bytes is progress
                        r.close()
                        while True:
                            resumes += 1
                            limit = RESUMES_WINDOWED if window else RESUMES
                            if stalled > limit or resumes > RESUMES_TOTAL:
                                raise AppleError(f"{e} (after {resumes - 1} resumed connections, {stalled - 1} in a row "
                                                 f"with no progress). Something on this network cuts Apple's download: "
                                                 f"turn off web/HTTP scanning in your antivirus, or connect through a phone "
                                                 f"hotspot or a VPN, and press Next. Last connections: {'; '.join(trail)}") from None
                            if window and stalled > 1 and (stalled - 1) % REFRESH_EVERY == 0:
                                _refresh(info)
                            window = WINDOW  # from now on never ask for more than one window per connection
                            try:
                                # back off when nothing arrives
                                r = _resume(info, pos, window, delay=min(2 ** stalled, WINDOW_MAX_DELAY))
                                break
                            except (AppleError, OSError, http.client.HTTPException) as again:
                                if "(status 200)" in str(again):
                                    raise  # the server ignores ranges: no retry can resume, so refuse at once
                                # WAS: a resume whose own request failed (reset, refused range) ended the whole
                                # download; it is one more empty connection
                                note(f"resume at {pos} refused: {type(again).__name__} {str(again)[-80:]}")
                                e, stalled = again, stalled + 1
                        conn_start = pos
                buf = bytes(part)
                if hashlib.sha256(buf).digest() != sha:
                    raise AppleError(f"chunk {i}/{len(chunks)} of {info['product']} fails Apple's hash - download refused")
                fh = _write_settled(fh, img + ".part", done, buf)
                done += size
                stalled = 0
                if progress:
                    progress(done, total)
            if r.read(1):
                raise AppleError("image is larger than its signed chunklist - refused")
    finally:
        r.close()
        fh.close()  # the handle may be a reopened one (_write_settled); the with only closed the first
    with open(cnk + ".part", "wb") as fh:
        fh.write(cl)
    os.replace(img + ".part", img)
    os.replace(cnk + ".part", cnk)
    return {"image": img, "chunklist": cnk, "bytes": total, "chunks": len(chunks)}


def local_image(folder):
    """A recovery image the user downloaded elsewhere (BaseSystem.dmg + BaseSystem.chunklist, e.g. macrecovery on another
    network), as an info dict for copy_local, or None. Apple refuses some networks outright (HTTP 403 on every session,
    1.2.0 logs), and one user asked for an offline installer: this is it. Nothing is trusted - copy_local checks every
    chunk against Apple's signed chunklist, exactly like a download."""
    if not folder or not os.path.isdir(folder):
        return None
    for cl in sorted(n for n in os.listdir(folder) if n.lower().endswith(".chunklist")):
        img = os.path.join(folder, os.path.splitext(cl)[0] + ".dmg")
        if os.path.isfile(img):
            return {"local": True, "image_path": img, "chunklist_path": os.path.join(folder, cl),
                    "image_url": "file:///" + os.path.basename(img), "name": "recovery image from " + folder,
                    "product": os.path.basename(img)}
    return None


def copy_local(info, usb_root, progress=None):
    """Like download(), from local files: the chunklist must carry Apple's signature and every chunk its hash."""
    dest = os.path.join(usb_root, "com.apple.recovery.boot")
    os.makedirs(dest, exist_ok=True)
    with open(info["chunklist_path"], "rb") as fh:
        cl = fh.read()
    chunks = parse_chunklist(cl)
    total = sum(s for s, _ in chunks)
    if os.path.getsize(info["image_path"]) != total:
        raise AppleError(f"{os.path.basename(info['image_path'])} is {os.path.getsize(info['image_path'])} bytes; its signed chunklist says {total}")
    img = os.path.join(dest, os.path.basename(info["image_path"]))
    cnk = os.path.splitext(img)[0] + ".chunklist"
    done = 0
    with open(info["image_path"], "rb") as src, open(img + ".part", "wb") as fh:
        for i, (size, digest) in enumerate(chunks, 1):
            buf = src.read(size)
            if hashlib.sha256(buf).digest() != digest:
                raise AppleError(f"chunk {i}/{len(chunks)} of {os.path.basename(info['image_path'])} fails Apple's hash - refused")
            fh.write(buf)
            done += size
            if progress:
                progress(done, total)
    with open(cnk + ".part", "wb") as fh:
        fh.write(cl)
    os.replace(img + ".part", img)
    os.replace(cnk + ".part", cnk)
    return {"image": img, "chunklist": cnk, "bytes": total, "chunks": len(chunks)}


def _write_settled(fh, path, offset, buf, tries=6, sleep=time.sleep):
    """Writes buf at offset, surviving the stick's volume blinking out under the open file: 1.5.0 log 10-10, Windows
    re-mounted a just-formatted stick mid-download and the next write failed "PermissionError: [Errno 13]". The partial
    image is reopened at the same offset and the write repeated; every chunk is still hash-checked before this."""
    for attempt in range(tries):
        try:
            fh.write(buf)
            return fh
        except OSError as error:
            if attempt == tries - 1:
                raise
            print(f"(the stick was busy: {type(error).__name__}; writing that piece again)", flush=True)
            try:
                fh.close()
            except OSError:
                pass
            for _ in range(20):
                if os.path.isfile(path):
                    break
                sleep(1)
            sleep(2)
            try:
                fh = open(path, "r+b")
                fh.seek(offset)
                fh.truncate()
            except OSError:
                fh = _Broken()
    return fh


class _Broken:
    """A handle that could not be reopened yet: its write fails, so the retry loop tries again."""
    def write(self, b):
        raise OSError("the stick's file could not be reopened")

    def close(self):
        pass


def _refresh(info):
    """Swaps in a fresh image URL and token for the same image from osrecovery. Any failure keeps the old ones: this only
    helps when a token or edge was the problem, and every byte is still checked against the signed chunklist."""
    major = next((k for k, (name, board) in TARGETS.items() if board == info.get("board") and name == info.get("name")), None)
    if major is None:
        return
    try:
        fresh = image_info(major)
    except (AppleError, OSError, http.client.HTTPException):
        return
    if fresh.get("product") == info.get("product"):
        info["image_url"], info["image_token"] = fresh["image_url"], fresh["image_token"]


def _resume(info, offset, window=0, delay=2):
    if delay:
        time.sleep(delay)
    rng = f"bytes={offset}-{offset + window - 1}" if window else f"bytes={offset}-"
    r = _asset(info["image_url"], info["image_token"], {"Range": rng})
    got = (r.headers.get("Content-Range") or "") if getattr(r, "headers", None) else ""
    if getattr(r, "status", None) != 206 or not got.startswith(f"bytes {offset}-"):
        r.close()
        raise AppleError(f"Apple's server would not resume the image at byte {offset} (status {getattr(r, 'status', '?')})")
    return r


def _read_into(r, part, n):
    """Appends to `part` until it holds n bytes; what arrived before a drop stays in `part`."""
    while len(part) < n:
        b = r.read(min(n - len(part), 1 << 20))
        if not b:
            raise AppleError(f"stream ended at {len(part)}/{n} bytes of a chunk")
        part += b


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
    # pre-Catalina targets name their OS through OLD_MLB, not the board's newest OS
    bad = {d: (b, boards.get(b)) for d, (_, b) in TARGETS.items() if d not in OLD_MLB
           and not str(boards.get(b, "")).startswith(MAJOR[d] + ".") and boards.get(b) != MAJOR[d]}
    arm("each board-id's newest OS in boards.json is the macOS we use it for", not bad, bad or "7/7")
    arm("High Sierra and Mojave have a recovery target", 17 in TARGETS and 18 in TARGETS, sorted(TARGETS))

    # a stream that drops after every chunk: 11 drops in all, never two in a row without progress
    import tempfile  # noqa: PLC0415
    data = [bytes([i]) * 64 for i in range(12)]

    class Drop:
        def __init__(self, start):
            self.i, self.left, self.headers, self.status = start, 64, {}, 206

        def read(self, n):
            if self.i >= len(data) or self.left == 0:
                return b""
            got = data[self.i][64 - self.left:64 - self.left + n]
            self.left -= len(got)
            return got

        def close(self):
            pass
    g = globals()
    keep = {k: g[k] for k in ("fetch_chunklist", "parse_chunklist", "_asset", "_resume")}
    g["fetch_chunklist"] = lambda info: b""
    g["parse_chunklist"] = lambda cl: [(64, hashlib.sha256(c).digest()) for c in data]
    g["_asset"] = lambda *a, **k: Drop(0)
    g["_resume"] = lambda info, off: Drop(off // 64)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            info = {"image_url": "http://x/BaseSystem.dmg", "image_token": "", "product": "test"}
            try:
                out = download(info, tmp)
                ok, shown = out["bytes"] == 64 * 12, f"{out['bytes']} bytes after 11 drops"
            except AppleError as e:
                ok, shown = False, str(e)
            arm("a download that drops after every chunk still finishes (drops with progress are not counted)", ok, shown)
            blob = b"".join(data)

            class Capped:  # a network that closes every connection after 16 bytes, mid-chunk (chunks are 64 bytes)
                def __init__(self, off):
                    self.off, self.left, self.headers, self.status = off, 16, {}, 206

                def read(self, n):
                    got = blob[self.off:self.off + min(n, self.left)]
                    self.off += len(got)
                    self.left -= len(got)
                    return got

                def close(self):
                    pass
            g["_asset"] = lambda *a, **k: Capped(0)
            g["_resume"] = lambda info, off: Capped(off)
            try:
                out = download(info, tmp)
                ok, shown = out["bytes"] == 64 * 12, f"{out['bytes']} bytes, 16 per connection"
            except AppleError as e:
                ok, shown = False, str(e)[:90]
            arm("a network that cuts every connection mid-chunk still finishes (resume from the last byte)", ok, shown)
            g["_asset"] = lambda *a, **k: Drop(0)
            g["_resume"] = lambda info, off: Drop(len(data))  # every resume returns nothing: no progress
            try:
                download(info, tmp)
                ok, shown = False, "finished with no data"
            except AppleError as e:
                ok, shown = "in a row" in str(e), str(e)[:80]
            arm("a stream that never makes progress still stops", ok, shown)
    finally:
        g.update(keep)

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
