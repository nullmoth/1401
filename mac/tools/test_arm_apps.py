#!/usr/bin/env python3
"""ARM apps (opt-in), Sources/ArmApps.swift: the translator package is installed only after its SHA-256 and the release
signature check out, and root checks the SHA-256 again on its own copy before unpacking it; the uninstaller runs only
when root owns it; translation runs as the user and Cancel ends the whole process tree; the page shows every error;
Send logs carries the translator's logs. ArmApps.swift is compiled against small stand-ins for the rest of the app and
its root shell lines are run in a sandbox (the root-only folder is swapped for a temporary one)."""
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
src = (ROOT / "Sources/ArmApps.swift").read_text()
main = (ROOT / "Sources/main.swift").read_text()
build = (ROOT / "build.sh").read_text()
html = (ROOT / "Resources/index.html").read_text()
js = (ROOT / "Resources/app.js").read_text()
fails = 0


def arm(name, ok, detail=""):
    global fails
    print(("ok   " if ok else "FAIL ") + name + (f" ({detail})" if detail else ""))
    fails += not ok


# source-level arms
fetch = src.split("static func fetch(", 1)[1].split("static func installCommand(", 1)[0]
arm("the SHA-256 and the signature are checked on ONE in-memory buffer, written to disk only afterwards",
    "let digest = hex(data)" in fetch and "ReleaseSignature.verifyBound(data: data, product: \"nullmoth-arm\", version: b.version, signatureBase64: text)" in fetch
    and "verify(zip:" not in fetch and fetch.index("verifyBound(data: data") < fetch.index("data.write(to: dst")
    and fetch.count("removeItem(at: dst)") == 2)
arm("root is handed the digest of the verified buffer", "installCommand(package: path, sha: digest)" in src)
arm("the manifest takes only https links, a 64-hex SHA-256 and a nullmoth-arm-*.tar.gz name",
    'u.scheme == "https"' in src and 's.scheme == "https"' in src and "validSha(sha), validPackageName(n)" in src)
inst = src.split("static func installCommand(", 1)[1].split("static func validUser(", 1)[0]
# 2.7: the installer ran under the private copy's umask 077 and left /Library/NullMoth root-only, hiding nm-arm
arm("the package installer runs with umask 022, not the private copy's 077", "(umask 022; /bin/bash" in inst)
arm("a successful install makes /Library/NullMoth and its arm folder traversable again (repairs 2.7 installs)",
    "/bin/chmod 755 /Library/NullMoth /Library/NullMoth/arm" in inst)
order = [inst.find(k) for k in ("mktemp -d /private/var/root/", "/bin/cp -X", "shasum -a 256", "tar -xzf", "install.sh\\\"); rc=$?")]
arm("root copies, re-checks the SHA-256 on its copy, then unpacks, then installs (in that order)",
    all(i >= 0 for i in order) and order == sorted(order), str(order))
turn_on = src.split("func armTurnOn(source:", 1)[1].split("func armTurnOff()", 1)[0]
arm("success is the installer's marker line plus the installed command, never the absence of an error",
    "r.output.contains(ArmApps.installedMarker), ArmApps.isInstalled" in turn_on)
arm("a cancelled password prompt is reported, not silent", "if r.cancelled { return fail(" in turn_on and "self.armFail(" in turn_on)
job = src.split("final class Job", 1)[1].split("\n}\n", 1)[0]
arm("translation runs as the user (a plain Process, no password prompt)", "Privileged" not in job and "osascript" not in job)
translate = src.split("func armTranslate()", 1)[1]
arm("translation is refused unless the package is installed and the check passes",
    "guard ArmApps.isInstalled" in translate and 'c["ok"] as? Bool == true' in translate)
arm("the app answers the page's arm messages", 'case "arm": armAction(b)' in main)
arm("build.sh compiles ArmApps.swift", "Sources/ArmApps.swift" in build)
arm("Send logs copies ~/Library/Logs/NullMoth/arm into the session, where the queue redacts every file",
    "files += self.armLogCopies(into: dir)" in main and 'logs.appendingPathComponent("arm")' in src
    and "redact(String(decoding: bytes" in main)
arm("the page has the card and its controls",
    all(f'id="{i}"' in html for i in ("armcard", "armon", "armoff", "armchk", "armclt", "armtr", "armbar", "armcancel", "armapps")))
ev = js.split("function armEvent(d)", 1)[1].split("\nfunction render(", 1)[0]
arm("every error and refusal reaches the page escaped", 'kind === "error"' in ev and "esc(d.why)" in ev and "esc(c.why" in ev)
auto = src.split("func armTurnOn(source:", 1)[1].split("func armWindowsRequest(", 1)[0]
arm("the banner's Turn on is the same verified path, records source 1401-windows, and a failure records off with the reason",
    "ArmApps.saveDecision(on: true, source: source)" in auto and "ArmApps.saveDecision(on: false, source: source, skipped: why)" in auto
    and 'b["from"] as? String == "windows" ? ArmApps.windowsSource' in src)
arm("turning off by hand records the user's off", 'ArmApps.saveDecision(on: false, source: "user")' in src)
arm("Not now records a decision so the banner shows once", 'skipped: "not now"' in src)
arm("nothing installs on its own: the request only sends a banner, never calls Turn on",
    "armTurnOn" not in src.split("func armWindowsRequest()", 1)[1].split("func armTurnOff()", 1)[0]
    and "armWindowsRequest" not in main)
arm("the page opens Tools with the ARM card first and the banner on it",
    'kind === "request"' in js and '$("armreqon").hidden = !d.canRun' in js and 'sec.insertBefore(card, first)' in js
    and 'id="armreq"' in html and 'id="armreqno"' in html)
arm("nm-arm check's note is shown in the card, escaped", "if (A.on && c.note)" in ev and "esc(c.note)" in ev)
arm("a partly blank sysctl answer steps the pre-check aside (the package reads CPUID then)",
    "parts.contains { $0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty } ? \"\"" in src)
arm("Translate is enabled only when on and the check passed", '$("armtr").disabled = !(A.on && A.ok) || A.running' in js)

# Homebrew (nm-arm brew): one root step for the folders, the rest as the user through the same Job as a translation
brew = (src.split("func armBrew(pick:", 1) + [""])[1]   # empty on the old code, so every arm below FAILs there
arm("Set up Homebrew asks first, checks the Mac for the ARM side, and creates the folders with ONE password prompt",
    "a.runModal() == .alertFirstButtonReturn" in brew and 'c["ok"] as? Bool == true' in brew
    and brew.count("Privileged.run(") == 1 and "ArmApps.brewRootCommand(user: NSUserName()" in brew)
arm("success of the folder step is its marker line, never the absence of an error",
    "r.output.contains(ArmApps.brewDirsMarker)" in brew and "if r.cancelled {" in brew)
arm("the setup itself runs as the user through the translation Job (no second password, Cancel works)",
    "ArmApps.Job(arguments: args)" in brew and 'what: "brew"' in brew and "--no-sudo" in src)
arm("Set up Homebrew is refused while a translation runs and before the translator is installed",
    "guard ArmApps.job == nil" in brew and "guard ArmApps.isInstalled" in brew)
arm("the folder list is Homebrew's installer list (kept equal to nm_arm_brew.PREFIX_DIRS)",
    '"var/homebrew/linked", "Cellar", "Caskroom"]' in src and '"share/fish/vendor_completions.d"' in src)
arm("the page has the Homebrew controls, and sends only the two choices",
    all(f'id="{i}"' in html for i in ("armbrew", "armbrewpick", "armbrewprim", "armbrewgo", "armbrewr"))
    and 'op: "brew", pick: $("armbrewpick").value, primary: $("armbrewprim").value' in js)
arm("Homebrew status and outcomes reach the page escaped", "esc(b.why)" in js and 'esc(d.why || "the setup did not finish")' in js)
arm("turning ARM apps off says what happens to each Homebrew", "An ARM Homebrew in /opt/homebrew stops working" in src
    and "Intel Homebrew in /usr/local is not affected" in src)

# compile ArmApps.swift against stand-ins for the rest of the app
STUBS = r'''
import Foundation
import AppKit
import CryptoKit
let support = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("arm-test-support")
let logs = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("arm-test-logs")
func sh(_ path: String, _ args: [String]) -> String {
    let p = Process(); p.executableURL = URL(fileURLWithPath: path); p.arguments = args
    let o = Pipe(); p.standardOutput = o; p.standardError = Pipe()
    do { try p.run() } catch { return "" }
    let d = o.fileHandleForReading.readDataToEndOfFile(); p.waitUntilExit()
    return String(decoding: d, as: UTF8.self)
}
// served from ARM_TEST_SERVE/<last path component>
func syncGet(_ url: URL, timeout: TimeInterval) -> Data? {
    guard let dir = ProcessInfo.processInfo.environment["ARM_TEST_SERVE"] else { return nil }
    return try? Data(contentsOf: URL(fileURLWithPath: dir).appendingPathComponent(url.lastPathComponent))
}
func sha256(_ url: URL) -> String? { nil }
func redact(_ s: String) -> String { s }
func sysctl(_ k: String) -> String { "" }
// a stand-in key: the "signature" is the package's own SHA-256 prefixed with SIGNED:
enum ReleaseSignature {
    static func verifyBound(data: Data, product: String, version: String, signatureBase64: String) -> Bool {
        signatureBase64 == "SIGNED:" + SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
    static func boundURL(sig: URL) -> URL { sig }
    static func isDowngrade(_ candidate: String, installed: String) -> Bool { false }
}
enum Privileged {
    struct Result { let output: String; let error: String?; let cancelled: Bool }
    static func run(_ c: String, timeout: TimeInterval) -> Result { Result(output: "", error: nil, cancelled: false) }
}
final class App: NSObject {
    func send(_ e: String, _ d: Any) {}
    // canned nm-arm answers from ARM_TEST_CLI_OUT / ARM_TEST_CLI_STATUS
    static func runBounded(_ exe: URL, _ args: [String], seconds: Double) -> (status: Int32, out: Data, timedOut: Bool) {
        let env = ProcessInfo.processInfo.environment
        return (Int32(env["ARM_TEST_CLI_STATUS"] ?? "0") ?? 0, Data((env["ARM_TEST_CLI_OUT"] ?? "").utf8), false)
    }
    static func machineProfile(_ g: [[String: Any]]) -> [String: Any] { [:] }
    static func recordedDriverVersion() -> String { "" }
}
'''
HARNESS = r'''
import Foundation
let a = CommandLine.arguments
switch a[1] {
case "install": print(ArmApps.installCommand(package: a[2], sha: a[3]) ?? "NIL")
case "uninstall": print(ArmApps.uninstallCommand(user: a[2]) ?? "NIL")
case "names":
    print(ArmApps.validPackageName("nullmoth-arm-1.0.0.tar.gz"), ArmApps.validPackageName("../nullmoth-arm-1.tar.gz"),
          ArmApps.validPackageName("nullmoth-arm-1.tar.gz;rm"), ArmApps.validPackageName("other-1.tar.gz"))
    print(ArmApps.validSha(String(repeating: "a", count: 64)), ArmApps.validSha(String(repeating: "a", count: 63) + "'"))
    print(ArmApps.validUser("jane"), ArmApps.validUser("ja'ne"), ArmApps.validUser("-x"))
    print(ArmApps.validAppName("Foo"), ArmApps.validAppName("../x"), ArmApps.validAppName(".."))
    let o = ArmApps.outputDir.path
    print(ArmApps.inOutputDir(o + "/Foo.app"), ArmApps.inOutputDir(o + "/../../Applications/Safari.app"), ArmApps.inOutputDir("/Applications/Foo.app"))
case "progress":
    let p1 = ArmApps.parseProgress(#"{"stage":"lift","pct":140,"msg":"lifting"}"#)!
    let p2 = ArmApps.parseProgress("plain text line")!
    print(p1["stage"] as! String, p1["pct"] as! Double, p2["msg"] as! String, ArmApps.parseProgress("   ") == nil)
case "job":
    let job = ArmApps.Job(app: URL(fileURLWithPath: "/tmp/X.app"), executable: a[2])
    let done = DispatchSemaphore(value: 0)
    var lines: [String] = []; let lk = NSLock()
    var result = ""
    let why = job.start(line: { p in lk.lock(); lines.append("\(p["stage"] ?? "")"); lk.unlock() },
                        done: { st, c, _ in result = "status=\(st) cancelled=\(c)"; done.signal() })
    if let why { print("START", why); exit(1) }
    if a[3] == "cancel" { Thread.sleep(forTimeInterval: 1.0); job.stop() }
    if done.wait(timeout: .now() + 20) == .timedOut { print("TIMEOUT"); exit(1) }
    lk.lock(); print(result, lines.joined(separator: ",")); lk.unlock()
case "decide":
    // a[2]: JSON array of profile records; a[3]: decision JSON or "none"; a[4]: driver installed
    let recs = try! JSONSerialization.jsonObject(with: Data(a[2].utf8)) as! [[String: Any]]
    let dec = a[3] == "none" ? nil : (try! JSONSerialization.jsonObject(with: Data(a[3].utf8)) as! [String: Any])
    let req = ArmApps.windowsRequest(recs)
    print(req, ArmApps.shouldHonourRequest(request: req, decision: dec, driverInstalled: a[4] == "yes"))
case "decision":
    try? FileManager.default.removeItem(at: ArmApps.decisionFile)
    let before = ArmApps.decision() == nil
    ArmApps.saveDecision(on: false, source: "1401-windows", skipped: "no network")
    let d = ArmApps.decision()!
    print(before, d["on"] as! Bool, d["source"] as! String, d["skipped"] as! String)
    try? FileManager.default.removeItem(at: ArmApps.decisionFile)
case "banner":
    // a[2]: request yes/no; a[3]: decision JSON or none; a[4]: cpu features
    let dec = a[3] == "none" ? nil : (try! JSONSerialization.jsonObject(with: Data(a[3].utf8)) as! [String: Any])
    if let b = ArmApps.banner(request: a[2] == "yes", decision: dec, driverInstalled: true, cpuFeatures: a[4]) {
        print(b["canRun"] as! Bool ? "BUTTON" : "NOBUTTON", b["text"] as! String)
    } else { print("NONE") }
case "names2":
    let u = { (s: String) in URL(string: s)! }
    print(ArmApps.manifestNamesMatch(version: "1.2", name: "nullmoth-arm-1.2.tar.gz", url: u("https://x/d/nullmoth-arm-1.2.tar.gz")),
          ArmApps.manifestNamesMatch(version: "1.2", name: "nullmoth-arm-1.3.tar.gz", url: u("https://x/d/nullmoth-arm-1.3.tar.gz")),
          ArmApps.manifestNamesMatch(version: "1.2", name: "nullmoth-arm-1.2.tar.gz", url: u("https://x/d/nullmoth-driver-2.7.tar.gz")),
          ArmApps.manifestNamesMatch(version: "../1", name: "nullmoth-arm-../1.tar.gz", url: u("https://x/d/1.tar.gz")))
case "fetch":
    // a[2]: sha the manifest claims; a[3]: sig file name
    let b = ArmApps.Build(version: "1.0", name: "nullmoth-arm-1.0.tar.gz", url: URL(string: "https://x/nullmoth-arm-1.0.tar.gz")!,
                          sha256: a[2], sig: URL(string: "https://x/" + a[3])!)
    let r = ArmApps.fetch(b)
    print(r.path ?? "NOPATH", r.sha256 ?? "NOSHA", r.why ?? "OK")
case "list":
    let l = ArmApps.parseList(try? JSONSerialization.jsonObject(with: Data(a[2].utf8)))
    print(l.map { $0.map { $0["name"]! + "=" + $0["path"]! }.joined(separator: ";") } ?? "NIL")
case "remove":
    print(ArmApps.remove(a[2]) ?? "OK")
case "cpu":
    print(ArmApps.cpuGate(features: a[2]) ?? "OK")
case "brewroot":
    print(ArmApps.brewRootCommand(user: a[2], arm: a[3] == "1", intel: a[4] == "1") ?? "NIL")
case "brewargs":
    print((ArmApps.brewSetupArguments(pick: a[2], primary: a[3]) ?? ["NIL"]).joined(separator: " "))
default: break
}
'''

with tempfile.TemporaryDirectory() as d:
    d = pathlib.Path(d)
    (d / "stubs.swift").write_text(STUBS)
    (d / "main.swift").write_text(HARNESS)
    exe = d / "t"
    c = subprocess.run(["xcrun", "swiftc", "-Onone", str(ROOT / "Sources/ArmApps.swift"), str(d / "stubs.swift"), str(d / "main.swift"),
                        "-o", str(exe)], capture_output=True, text=True, timeout=900)
    arm("ArmApps.swift compiles", c.returncode == 0, c.stderr[-800:])
    if c.returncode:
        print(f"{fails} failed"); sys.exit(1)
    run = lambda *a: subprocess.run([str(exe), *a], capture_output=True, text=True, timeout=60).stdout.strip()

    names = run("names").splitlines()
    arm("package names: only nullmoth-arm-*.tar.gz, no path or shell characters", names[0] == "true false false false", names[0])
    arm("a SHA-256 that is not 64 hex digits never reaches the root shell", names[1] == "true false", names[1])
    arm("the uninstaller is given only a plain account name", names[2] == "true false false", names[2])
    arm("app names with a path in them are refused", names[3] == "true false false", names[3])
    arm("Open accepts only apps inside ~/Applications/NullMoth ARM (no ../ escape)", names[4] == "true false false", names[4])
    arm("progress lines parse, pct is clamped, plain output is kept, blanks dropped",
        run("progress") == "lift 100.0 plain text line true", run("progress"))

    # the 1401 for Windows request: consumed only with no recorded decision, after a driver install, literal true only
    import json
    req = {"opt_in": {"arm_apps": True, "from": "1401-windows", "schema": 1}}
    def decide(records, decision, driver="yes"):
        return run("decide", json.dumps(records), "none" if decision is None else json.dumps(decision), driver)
    arm("a request with no prior decision shows the offer (installed profile windows_candidates)",
        decide([{"windows_candidates": [{}, req]}], None) == "true true", decide([{"windows_candidates": [{}, req]}], None))
    arm("a request read straight from a stick's profile counts too", decide([req], None) == "true true")
    arm("negative control: a prior off (user turned it off) is respected",
        decide([{"windows_candidates": [req]}], {"on": False, "source": "user"}) == "true false")
    arm("negative control: a request already handled (skipped with a reason) never fires again",
        decide([{"windows_candidates": [req]}], {"on": False, "source": "1401-windows", "skipped": "no network"}) == "true false")
    arm("a prior on is left alone", decide([{"windows_candidates": [req]}], {"on": True, "source": "user"}) == "true false")
    arm("no request means no change", decide([{"windows_candidates": [{}]}, {}], None) == "false false")
    arm("arm_apps of 1 or \"true\" is not a request",
        decide([{"opt_in": {"arm_apps": 1}}, {"opt_in": {"arm_apps": "true"}}], None) == "false false")
    arm("no driver install, no action", decide([req], None, "no") == "true false")
    arm("the decision record round-trips with its source and reason (and an absent file reads as no decision)",
        run("decision") == "true false 1401-windows no network", run("decision"))
    full = "FPU SSE3 PCLMULQDQ SSSE3 SSE4.1 SSE4.2 POPCNT AES AVX1.0 AVX2"
    arm("a CPU with AES, PCLMULQDQ, SSE4.2 and POPCNT passes the gate (by features, any vendor)", run("cpu", full) == "OK", run("cpu", full))
    out = run("cpu", full.replace(" AES", ""))
    arm("negative control: no AES fails the gate with the reason", "lacks AES" in out, out)

    # the banner: shown once, for a request with no decision; a CPU that cannot run it gets the reason and no button
    out = run("banner", "yes", "none", full)
    arm("request + no decision shows the banner with Turn on", out.startswith("BUTTON 1401 for Windows set up ARM apps for this Mac. Press Turn on"), out)
    out = run("banner", "yes", json.dumps({"on": False, "source": "1401-windows", "skipped": "not now"}), full)
    arm("negative control: a prior decision (Not now) hides the banner", out == "NONE", out)
    out = run("banner", "yes", json.dumps({"on": True, "source": "user"}), full)
    arm("a prior decision (on) hides the banner", out == "NONE", out)
    out = run("banner", "no", "none", full)
    arm("no request means no banner", out == "NONE", out)
    arm("an empty CPU answer (AMD without the sysctl keys) is left to nm-arm check, not refused", run("cpu", " ") == "OK", run("cpu", " "))
    arm("PCLMUL spelled either way counts", run("cpu", full.replace("PCLMULQDQ", "PCLMUL")) == "OK")
    out = run("banner", "yes", "none", full.replace(" AES", ""))
    arm("negative control: a CPU without AES shows the reason and no Turn on button", out.startswith("NOBUTTON") and "lacks AES" in out, out)

    names2 = run("names2")
    arm("the manifest's name and link must be nullmoth-arm-<its own version>.tar.gz (another product or version is refused)",
        names2 == "true false false false", names2)

    # nm-arm list / remove in the package's real shapes (runCLI needs the installed command, so only when it exists)
    o = str(pathlib.Path.home() / "Applications/NullMoth ARM")
    def cli(out, status="0", *a):
        e = dict(os.environ, ARM_TEST_CLI_OUT=out, ARM_TEST_CLI_STATUS=status)
        return subprocess.run([str(exe), *a], capture_output=True, text=True, timeout=60, env=e).stdout.strip()
    listing = json.dumps({"apps": [{"name": "L6", "path": o + "/L6.app", "output": o + "/L6.app"},
                                   {"name": "Old", "output": o + "/Old.app"},
                                   {"name": "Evil", "path": "/Applications/Safari.app"}], "output_dir": o})
    out = run("list", listing)
    arm("nm-arm list's object form is read, output stands in for path, a path outside the folder is dropped",
        out == f"L6={o}/L6.app;Old={o}/Old.app", out)
    arm("negative control: a list that is neither the object nor an array is refused", run("list", '{"x":1}') == "NIL")
    out = cli(json.dumps({"ok": False, "why": "L7 is not in the manifest"}), "2", "remove", "L7")
    arm("a refused remove shows nm-arm's own reason", out == "could not remove L7: L7 is not in the manifest", out)
    out = cli(json.dumps({"ok": True, "removed": ["L6"]}), "0", "remove", "L6")
    arm("a successful remove reports nothing wrong", out == "OK", out)

    # fetch: hash and signature on one buffer; a bad signature or SHA leaves nothing behind
    import hashlib as _h
    serve = d / "serve"; serve.mkdir()
    payload = b"arm package bytes"
    (serve / "nullmoth-arm-1.0.tar.gz").write_bytes(payload)
    psha = _h.sha256(payload).hexdigest()
    (serve / "good.sig").write_text("SIGNED:" + psha)
    (serve / "bad.sig").write_text("SIGNED:" + "0" * 64)
    env = dict(os.environ, ARM_TEST_SERVE=str(serve))
    frun = lambda *a: subprocess.run([str(exe), "fetch", *a], capture_output=True, text=True, timeout=60, env=env).stdout.split()
    got = frun(psha, "good.sig")
    arm("a signed package is written and its verified digest returned",
        len(got) == 3 and got[1] == psha and got[2] == "OK" and pathlib.Path(got[0]).read_bytes() == payload, " ".join(got))
    fetched = pathlib.Path(got[0]) if got and got[0] != "NOPATH" else None
    got = frun(psha, "bad.sig")
    arm("negative control: a bad signature returns nothing and removes the download",
        got[:2] == ["NOPATH", "NOSHA"] and (fetched is None or not fetched.exists()), " ".join(got))
    got = frun("1" * 64, "good.sig")
    arm("negative control: bytes that differ from the manifest's SHA-256 return nothing", got[:2] == ["NOPATH", "NOSHA"], " ".join(got))

    # the install line, run in a sandbox: a good package installs; a package swapped after the check does not run
    sandbox = d / "root"; sandbox.mkdir()
    pkgdir = d / "pkg"; (pkgdir / "pkgroot").mkdir(parents=True)
    ran = d / "installer-ran"
    (pkgdir / "pkgroot/install.sh").write_text(f"#!/bin/bash\ntouch '{ran}'\nexit ${{FAKE_RC:-0}}\n")
    good = d / "nullmoth-arm-1.0.tar.gz"
    with tarfile.open(good, "w:gz") as t:
        t.add(pkgdir / "pkgroot", arcname="pkgroot")
    import hashlib
    sha = hashlib.sha256(good.read_bytes()).hexdigest()

    def sandboxed(cmd):
        assert cmd.count("/private/var/root/") == 1
        return subprocess.run(["/bin/bash", "-c", cmd.replace("/private/var/root/", str(sandbox) + "/")],
                              capture_output=True, text=True, timeout=60).stdout

    out = sandboxed(run("install", str(good), sha))
    arm("a checked package unpacks, its installer runs, and the marker is printed",
        "NULLMOTH_ARM_INSTALLED" in out and ran.exists(), out.strip())
    arm("the private folder is removed afterwards", not any(sandbox.iterdir()))
    ran.unlink(missing_ok=True)
    out = sandboxed(run("install", str(good), "0" * 64))
    arm("negative control: a package whose bytes differ from the checked SHA-256 is refused and its installer never runs",
        "NULLMOTH_ARM_INSTALLED" not in out and "changed after it was checked" in out and not ran.exists(), out.strip())
    # the swap: the user-owned download changes after the app checked it; root re-hashes its own copy and refuses
    swapped = d / "nullmoth-arm-1.0-swap.tar.gz"
    shutil.copy(good, swapped)
    cmd = run("install", str(swapped), sha)
    with tarfile.open(swapped, "w:gz") as t:
        t.add(pkgdir / "pkgroot", arcname="pkgroot")
        extra = d / "evil"; extra.write_text("x"); t.add(extra, arcname="pkgroot/evil")
    out = sandboxed(cmd)
    arm("negative control: a package swapped after the check is refused by root and its installer never runs",
        "NULLMOTH_ARM_INSTALLED" not in out and "changed after it was checked" in out and not ran.exists(), out.strip())
    ran.unlink(missing_ok=True)
    os.environ["FAKE_RC"] = "4"
    out = sandboxed(run("install", str(good), sha))
    del os.environ["FAKE_RC"]
    arm("negative control: an installer that exits 4 gives its reason and no success marker",
        "NULLMOTH_ARM_INSTALLED" not in out and "cannot run on this Mac" in out, out.strip())
    arm("a quote in the SHA-256 yields no command at all", run("install", str(good), "a" * 63 + "'") == "NIL")

    # the uninstall line: absent package = already off; refused when not root-owned or writable by others
    out = subprocess.run(["/bin/bash", "-c", run("uninstall", "jane")], capture_output=True, text=True, timeout=30).stdout
    if not os.path.exists("/Library/NullMoth/arm/uninstall.sh"):
        arm("with nothing installed, turning off reports off", "NULLMOTH_ARM_REMOVED" in out, out.strip())
    # the real uninstall.sh accepts only --user NAME (a bare name exits 2), so the fake insists on that form too
    fake = d / "uninstall.sh"; fake.write_text(f"#!/bin/bash\n[ \"$1\" = --user ] || exit 2\necho \"removing $2\"\n")
    cmd = run("uninstall", "jane").replace("/Library/NullMoth/arm/uninstall.sh", str(fake))
    fake.chmod(0o644)
    out = subprocess.run(["/bin/bash", "-c", cmd], capture_output=True, text=True, timeout=30).stdout
    arm("negative control: an uninstaller not owned by root is refused", "not owned by root" in out and "NULLMOTH_ARM_REMOVED" not in out, out.strip())
    mine = cmd.replace('[ "$o" = 0 ]', f'[ "$o" = {os.getuid()} ]')
    assert mine != cmd
    out = subprocess.run(["/bin/bash", "-c", mine], capture_output=True, text=True, timeout=30).stdout
    arm("an owner-only uninstaller runs with the account name and prints the marker",
        "removing jane" in out and "NULLMOTH_ARM_REMOVED" in out, out.strip())
    for mode in (0o664, 0o646):
        fake.chmod(mode)
        out = subprocess.run(["/bin/bash", "-c", mine], capture_output=True, text=True, timeout=30).stdout
        arm(f"negative control: an uninstaller with mode {mode:o} is refused", "changed by other users" in out and "removing" not in out, out.strip())

    # translation: progress streams, and Cancel ends the translator and the child it started
    child_pid = d / "child.pid"
    cli = d / "nm-arm"
    cli.write_text(f'''#!/bin/bash
echo '{{"stage":"scan","pct":5,"msg":"reading"}}'
/bin/sleep 300 &
echo $! > '{child_pid}'
echo '{{"stage":"lift","pct":40,"msg":"lifting"}}'
if [ "$3" = fast ]; then exit 0; fi
wait
''')
    cli.chmod(0o755)
    fast = d / "nm-arm-fast"; fast.write_text(f'#!/bin/bash\nexec "{cli}" "$@" fast\n'); fast.chmod(0o755)
    out = run("job", str(fast), "wait")
    arm("a finished translation reports status 0 and every progress line, in order", out == "status=0 cancelled=false scan,lift", out)
    if child_pid.exists():
        os.kill(int(child_pid.read_text()), 9); child_pid.unlink()
    t0 = time.time()
    out = run("job", str(cli), "cancel")
    pid = int(child_pid.read_text()) if child_pid.exists() else 0
    time.sleep(0.5)
    alive = False
    if pid:
        try: os.kill(pid, 0); alive = True
        except ProcessLookupError: alive = False
    arm("Cancel ends the translator and the process it started", "cancelled=true" in out and pid and not alive,
        f"{out}; child {pid} alive={alive}; {time.time() - t0:.1f} s")
    if alive: os.kill(pid, 9)
    shutil.rmtree(sandbox, ignore_errors=True)

    # Homebrew's folder step, run against a sandbox (the two prefixes moved into it, chown left out)
    arm("Set up Homebrew's arguments: both, ARM only, Intel only; anything else gives none",
        run("brewargs", "both", "arm") == "brew setup --arm --intel --primary arm --no-sudo"
        and run("brewargs", "arm", "intel") == "brew setup --arm --primary intel --no-sudo"
        and run("brewargs", "intel", "intel") == "brew setup --intel --primary intel --no-sudo"
        and run("brewargs", "all", "arm") == "NIL" and run("brewargs", "both", "x86") == "NIL")
    arm("negative control: a user name with a quote, or no prefix chosen, gives no root line",
        run("brewroot", "ja'ne", "1", "1") == "NIL" and run("brewroot", "jane", "0", "0") == "NIL")
    line = run("brewroot", os.environ.get("USER", "nobody"), "1", "1")
    arm("the root line never chowns recursively and never chowns /usr/local itself",
        "chown -R" not in line and 'chown "$u:$g" /usr/local;' not in line and line.endswith("echo NULLMOTH_BREW_DIRS_READY"))
    import re as _re
    arm("every chown in the root line is chown -h (never follows a link), and the prefix is handed over last",
        all(c.startswith("/usr/sbin/chown -h") for c in _re.findall(r"/usr/sbin/chown[^;]*", line))
        and line.index('/usr/sbin/chown -h "$u:$g" /opt/homebrew;') > line.index('for d in $todo'), line[:200])
    arm("folders under a parent the user already owns are made as the user, never by root",
        'rootchain "$(/usr/bin/dirname "$d")" || continue' in line and '/usr/bin/sudo -u "$u" /bin/mkdir -p' in line)
    bs = pathlib.Path(os.path.realpath(d)) / "brewroot"   # /var is a link on macOS; the chain check refuses links
    bs.mkdir(); (bs / "opt").mkdir(); (bs / "usr").mkdir()   # /opt is made by root, /usr always exists
    sb = (line.replace("/opt/homebrew", f"{bs}/opt/homebrew").replace("/usr/local", f"{bs}/usr/local")
          .replace("/usr/sbin/chown", ":").replace("/usr/bin/stat -f %Su", "echo root || :")
          .replace('/usr/bin/sudo -u "$u" ', ""))
    out = subprocess.run(["/bin/bash", "-c", sb], capture_output=True, text=True, timeout=60).stdout
    arm("the root line (sandboxed) creates both prefixes' folders and prints the marker",
        "NULLMOTH_BREW_DIRS_READY" in out and (bs / "opt/homebrew/Cellar").is_dir() and (bs / "usr/local/Homebrew").is_dir()
        and (bs / "usr/local/var/homebrew/linked").is_dir(), out.strip())
    shutil.rmtree(bs / "opt/homebrew"); (bs / "elsewhere").mkdir(); os.symlink(bs / "elsewhere", bs / "opt/homebrew")
    out = subprocess.run(["/bin/bash", "-c", sb], capture_output=True, text=True, timeout=60).stdout
    arm("negative control: a symlinked /opt/homebrew stops the root line without the marker",
        "STOP" in out and "NULLMOTH_BREW_DIRS_READY" not in out, out.strip())

print(f"{fails} failed")
sys.exit(1 if fails else 0)
