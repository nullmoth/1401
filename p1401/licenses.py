"""Which downloads NullMoth may host a copy of, by the licence of the project they come from.

licenses.json names every project 1401 can download from and its licence, read from the project itself (LICENSE file,
or the licence grant in its source headers when there is no LICENSE file). The mirror (mirror.py, tools/record_mirror.py)
hosts a copy only when that licence allows it:

- permissive and nullmoth: hosted with the bytes unchanged.
- copyleft: hosted only when the corresponding source can be named and is hosted beside it (build-repo builds carry
  their commit, GitHub release assets their tag).
- none, restricted, tool-payload: never hosted. The engine still downloads grandfathered ones from their authors, because
  machines rely on them today; a project added later must be permissive or copyleft.

A URL that matches no project is not hosted either: an unknown licence is not a licence."""
import json
import os
import re
import urllib.parse

TABLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "licenses.json")
HOSTED = ("permissive", "nullmoth")
ADMITTED = ("permissive", "copyleft", "nullmoth")       # classes a new project may have

_GH = re.compile(r"https://github\.com/([^/]+)/([^/]+)(/.*)?$")
_RAW = re.compile(r"https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/")
_NIGHTLY = re.compile(r"https://nightly\.link/([^/]+)/([^/]+)/")
_BUILD = re.compile(r"/releases/download/(.+)-([0-9a-f]{7,40})/")
_TAG = re.compile(r"/releases/download/([^/]+)/")
_BITBUCKET = {"rehabman/os-x-null-ethernet": "RehabMan/OS-X-Null-Ethernet"}
_table = {}


def table():
    if not _table:
        with open(TABLE, encoding="utf-8") as fh:
            _table.update(json.load(fh))
    return _table


def project(name):
    """The licences.json entry for owner/repo, matched without case (GitHub URLs are case-insensitive)."""
    projects = table()["projects"]
    for key, entry in projects.items():
        if key.lower() == name.lower():
            return key, entry
    return None, None


def classify(url):
    """-> (kind, project name or None, source URL or None). kind is binary, source or metadata."""
    if url.startswith("https://nullmothsystems.com/mirror/"):
        return "binary", "nullmoth", None
    if url == "https://raw.githubusercontent.com/dortania/build-repo/builds/latest.json":
        return "metadata", None, None                   # the build index: names, URLs and hashes, no code
    m = _GH.match(url)
    if m:
        owner, repo, rest = m.group(1), m.group(2), m.group(3) or ""
        if owner.lower() == "nullmoth":
            return "binary", "nullmoth", None
        if rest in ("/releases", "") or rest.startswith("/releases/expanded_assets/") or rest.endswith("/SHA256SUMS.txt"):
            return "metadata", None, None               # release index pages are reduced to their tag link
        if rest.startswith("/archive/"):
            return "source", f"{owner}/{repo}", None
        if owner.lower() == "dortania" and repo.lower() == "build-repo":
            b = _BUILD.search(rest)
            name = b and table()["build_repo"].get(b.group(1))
            if not name:
                return "binary", None, None
            return "binary", name, f"https://github.com/{name}/archive/{b.group(2)}.tar.gz"
        t = _TAG.match(rest)
        if t:
            return "binary", f"{owner}/{repo}", f"https://github.com/{owner}/{repo}/archive/refs/tags/{t.group(1)}.tar.gz"
        return "binary", f"{owner}/{repo}", None        # a raw file on a branch: no fixed source to pair it with
    for pattern in (_RAW, _NIGHTLY):
        m = pattern.match(url)
        if m:
            return "binary", f"{m.group(1)}/{m.group(2)}", None
    parts = urllib.parse.urlsplit(url)
    if parts.netloc == "bitbucket.org":
        key = "/".join(parts.path.strip("/").split("/")[:2]).lower()
        return "binary", _BITBUCKET.get(key), None
    return "binary", None, None


def hostable(url):
    """-> (True, None, source URL or None) when NullMoth may host a copy of url, else (False, reason, None)."""
    kind, name, source = classify(url)
    if kind == "metadata":
        return True, None, None
    key, entry = project(name) if name else (None, None)
    if not entry:
        return False, f"{name or url}: not in licenses.json", None
    cls = entry["class"]
    if kind == "source":
        return (cls == "copyleft", None if cls == "copyleft" else f"{key}: source is hosted only for copyleft", None)
    if cls in HOSTED:
        return True, None, None
    if cls == "copyleft":
        if source:
            return True, None, source
        return False, f"{key}: {entry['license']} binary with no fixed source to host beside it", None
    return False, f"{key}: {entry['license']} ({cls}) is not ours to host", None
