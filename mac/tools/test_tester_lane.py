#!/usr/bin/env python3
"""The AMD/Intel test program (Sources/TesterLane.swift): a test build is used only when its SHA-256 and the release
signature over its bytes both check out; the per-start report runs only for a user who joined, once per start, and
leaving removes its login item. The Swift is compiled and the signature check is exercised against a throwaway key."""
import base64
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
src = (ROOT / "Sources/TesterLane.swift").read_text()
main = (ROOT / "Sources/main.swift").read_text()
fails = 0


def arm(name, ok, detail=""):
    global fails
    print(("ok   " if ok else "FAIL ") + name + (f" ({detail})" if detail else ""))
    fails += not ok


fetch = src.split("static func fetch(", 1)[1].split("static func set(", 1)[0]
arm("a test build is checked against its SHA-256 before use", "sha256(dst) == b.sha256" in fetch)
arm("a test build must carry the release signature over its exact bytes",
    "ReleaseSignature.verify(zip: dst, signatureBase64: text)" in fetch and "removeItem(at: dst)" in fetch)
arm("the manifest only accepts https links and a bare file name",
    'u.scheme == "https"' in src and 's.scheme == "https"' in src and '!n.contains("/")' in src)
report = src.split("static func report()", 1)[1]
arm("the report does nothing for a user who has not joined", report.lstrip().startswith("-> Int32 {\n        guard isOn else { return 0 }"))
arm("the report runs once per start (boot session id)", 's["lastBoot"] as? String == boot' in report and 'kern.bootsessionuuid' in report)
arm("a start counts as reported only when something reached the site", "if sent > 0 {" in report)
arm("every file is redacted like Send logs before it leaves", "redact(String(decoding: bytes" in report)
setf = src.split("static func set(", 1)[1].split("static func report()", 1)[0]
arm("leaving removes the login item and stops it", "bootout" in setf and "removeItem(at: agentFile)" in setf)
arm("joining is refused when another user could replace 1401", "p & 0o002 != 0" in setf)
arm("only the tester report mode remains (the crash-check login item is gone)",
    'argv.contains("--tester-report")' in main and "--crash-check" not in main and "func crashCheck" not in main)

# the signature check itself, with a throwaway key: a signed file passes, a changed byte fails
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        k = Ed25519PrivateKey.generate()
        pub = base64.b64encode(k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
        pkg = d / "p.tar.gz"; pkg.write_bytes(b"test build bytes")
        sig = base64.b64encode(k.sign(pkg.read_bytes())).decode()
        harness = d / "main.swift"
        harness.write_text(f'''import Foundation
let ok = ReleaseSignature.verify(zip: URL(fileURLWithPath: "{pkg}"), signatureBase64: "{sig}", publicKeyBase64: "{pub}")
try! Data("test build bytez".utf8).write(to: URL(fileURLWithPath: "{pkg}"))
let bad = ReleaseSignature.verify(zip: URL(fileURLWithPath: "{pkg}"), signatureBase64: "{sig}", publicKeyBase64: "{pub}")
print(ok, bad)
''')
        exe = d / "t"
        subprocess.run(["xcrun", "swiftc", "-Onone", str(ROOT / "Sources/ReleaseSignature.swift"), str(harness), "-o", str(exe)],
                       check=True, capture_output=True, timeout=600)
        out = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60).stdout.split()
        arm("a test build signed with the key verifies", out[:1] == ["true"], " ".join(out))
        arm("negative control: one changed byte fails the signature", out[1:2] == ["false"], " ".join(out))
except ImportError:
    arm("cryptography is installed for the signature arm", False)

print(f"{fails} failed")
sys.exit(1 if fails else 0)
