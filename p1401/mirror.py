"""Content-addressed fallback for build dependencies.

Networks that block or reset GitHub (common in mainland China and on some school and work networks) could not finish a
build: OpenCore, its drivers, the kexts and the patch lists all come from GitHub. Each release ships mirror.json beside
this file: every dependency URL the build can fetch, with the size and SHA-256 of the exact bytes recorded when the
release was packaged (tools/record_mirror.py). The same bytes are served as nullmothsystems.com/mirror/<sha256>.

A mirrored file is used only when its size and SHA-256 equal the manifest's, so the mirror can never change what a
build gets; it can only make a build possible that GitHub's reachability would otherwise stop. After the first
dependency that GitHub fails and the mirror serves, the rest of the build asks the mirror first, so a blocked network
does not wait out every GitHub timeout again for each file."""
import email.message
import hashlib
import io
import json
import os
import re
import threading
import urllib.error
import urllib.request

BASE = "https://nullmothsystems.com/mirror/"
MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mirror.json")
SCHEMA = 1
# OcBinaryData's master.zip is the largest recorded file (about 120 MB); anything far above that is not ours.
MAX_SIZE = 512 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}")

_lock = threading.Lock()
_state = {"entries": None, "problem": None, "preferred": False}


class MirrorError(RuntimeError):
    pass


def _valid(entry):
    return (isinstance(entry, dict) and isinstance(entry.get("sha256"), str) and _SHA.fullmatch(entry["sha256"])
            and type(entry.get("size")) is int and 0 < entry["size"] <= MAX_SIZE)


def entries(path=None):
    """url -> {sha256, size}. A missing or malformed manifest gives no entries, and problem() says why."""
    with _lock:
        if _state["entries"] is None or path:
            got, problem = {}, None
            try:
                with open(path or MANIFEST, encoding="utf-8") as fh:
                    data = json.load(fh)
                if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(data.get("entries"), dict):
                    problem = "mirror.json has an unknown layout"
                else:
                    got = {u: e for u, e in data["entries"].items() if isinstance(u, str) and u.startswith("https://") and _valid(e)}
                    if len(got) != len(data["entries"]):
                        problem = f"mirror.json: {len(data['entries']) - len(got)} malformed entries ignored"
            except FileNotFoundError:
                problem = "no mirror.json in this build"
            except (OSError, ValueError) as error:
                problem = f"mirror.json unreadable ({type(error).__name__})"
            _state["entries"], _state["problem"] = got, problem
        return _state["entries"]


def problem():
    entries()
    return _state["problem"]


def has(url):
    return url in entries()


def prefer():
    _state["preferred"] = True


def preferred():
    return _state["preferred"]


class Response(io.BytesIO):
    """The parts of an http.client.HTTPResponse the engine reads: read, getcode, info, getheader, a context manager."""

    def __init__(self, data, url):
        super().__init__(data)
        self.url = url
        self.status = self.code = 200
        self.headers = email.message.Message()
        self.headers["Content-Length"] = str(len(data))

    def getcode(self):
        return 200

    def info(self):
        return self.headers

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def geturl(self):
        return self.url


def fetch(url, context=None, timeout=30, user_agent="1401"):
    """The recorded bytes for url from the mirror, verified against the manifest. Raises MirrorError with the reason."""
    entry = entries().get(url)
    if not entry:
        raise MirrorError("not in this build's mirror manifest")
    request = urllib.request.Request(BASE + entry["sha256"], headers={"User-Agent": user_agent, "Accept-Encoding": "identity"})
    digest, data = hashlib.sha256(), bytearray()
    try:
        with urllib.request.urlopen(request, timeout=min(max(timeout, 10), 60), context=context) as response:
            while True:
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                data += chunk
                digest.update(chunk)
                if len(data) > entry["size"]:
                    raise MirrorError("mirror sent more bytes than were recorded")
    except urllib.error.HTTPError as error:
        error.close()
        raise MirrorError(f"mirror returned HTTP {error.code}") from None
    except (urllib.error.URLError, OSError) as error:
        cause = getattr(error, "reason", error)
        raise MirrorError(f"mirror unreachable ({type(cause).__name__})") from None
    if len(data) != entry["size"] or digest.hexdigest() != entry["sha256"]:
        raise MirrorError("mirror file does not match the recorded size and SHA-256 - refused")
    return Response(bytes(data), url)


def selftest():
    import tempfile  # noqa: PLC0415
    from unittest.mock import patch  # noqa: PLC0415
    results = []

    def arm(name, ok, detail=""):
        results.append(bool(ok))
        print(("  ok   " if ok else "  FAIL ") + name + (f"   [{detail}]" if detail else ""))

    body = b"recorded dependency bytes"
    sha = hashlib.sha256(body).hexdigest()
    url = "https://github.com/acidanthera/Lilu/releases/download/1.0.0/Lilu-1.0.0-RELEASE.zip"

    class Served(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.close()

    served = {"data": body, "asked": []}

    def urlopen(request, timeout=None, context=None):
        served["asked"].append(request.full_url)
        return Served(served["data"])

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "mirror.json")
        with open(path, "w") as fh:
            json.dump({"schema": SCHEMA, "entries": {url: {"sha256": sha, "size": len(body)},
                                                     "https://x/bad": {"sha256": "nothex", "size": 1}}}, fh)
        entries(path)
        arm("a malformed entry is dropped and reported, the good one kept", has(url) and not has("https://x/bad") and "malformed" in (problem() or ""), problem())
        with patch("urllib.request.urlopen", urlopen):
            got = fetch(url)
            arm("the mirror is asked by content hash, never by the original path", served["asked"] == [BASE + sha], served["asked"][0])
            arm("the recorded bytes come back with the response shape the engine reads",
                got.read() == body and got.getcode() == 200 and got.info().get("Content-Length") == str(len(body)) and got.getheader("Content-Encoding") is None)
            served["data"] = body[:-1] + b"X"
            try:
                fetch(url); arm("a mirror file with one changed byte is refused", False)
            except MirrorError as error:
                arm("a mirror file with one changed byte is refused", "refused" in str(error), str(error))
            served["data"] = body + b"tail"
            try:
                fetch(url); arm("a mirror file longer than recorded is refused", False)
            except MirrorError as error:
                arm("a mirror file longer than recorded is refused", "more bytes" in str(error), str(error))
            try:
                fetch("https://github.com/other/file.zip"); arm("a URL outside the manifest is never fetched", False)
            except MirrorError as error:
                arm("a URL outside the manifest is never fetched", len(served["asked"]) == 3, str(error))
        os.remove(path)
        entries(path)
        arm("no manifest: no entries, and the reason is kept", not has(url) and problem() == "no mirror.json in this build", problem())
    _state["entries"] = None
    print(f"mirror: {sum(results)}/{len(results)}")
    return all(results)


if __name__ == "__main__":
    import sys  # noqa: PLC0415
    sys.exit(0 if selftest() else 1)
