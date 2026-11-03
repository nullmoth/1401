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
arm("the package is checked against its SHA-256 and the release signature, and a bad one is deleted",
    "sha256(dst) == b.sha256" in fetch and "ReleaseSignature.verify(zip: dst, signatureBase64: text)" in fetch
    and fetch.count("removeItem(at: dst)") == 2)
arm("the manifest takes only https links, a 64-hex SHA-256 and a nullmoth-arm-*.tar.gz name",
    'u.scheme == "https"' in src and 's.scheme == "https"' in src and "validSha(sha), validPackageName(n)" in src)
inst = src.split("static func installCommand(", 1)[1].split("static func validUser(", 1)[0]
order = [inst.find(k) for k in ("mktemp -d /private/var/root/", "/bin/cp -X", "shasum -a 256", "tar -xzf", "install.sh\\\" && echo")]
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
arm("a request uses the same verified Turn on path and records source 1401-windows; its failure records off with the reason",
    "ArmApps.saveDecision(on: true, source: source)" in auto and "ArmApps.saveDecision(on: false, source: source, skipped: why)" in auto
    and "self.armTurnOn(source: ArmApps.windowsSource)" in src)
arm("turning off by hand records the user's off", 'ArmApps.saveDecision(on: false, source: "user")' in src)
arm("the request fires only after a successful driver install, after its result went to the page, or at launch",
    'if mode == "install" && succeeded && !cancelled { self.armWindowsRequest(afterInstall: true) }' in main
    and 'armWindowsRequest(afterInstall: false)' in src)
arm("Translate is enabled only when on and the check passed", '$("armtr").disabled = !(A.on && A.ok) || A.running' in js)

# compile ArmApps.swift against stand-ins for the rest of the app
STUBS = r'''
import Foundation
import AppKit
let support = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("arm-test-support")
let logs = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("arm-test-logs")
func sh(_ path: String, _ args: [String]) -> String {
    let p = Process(); p.executableURL = URL(fileURLWithPath: path); p.arguments = args
    let o = Pipe(); p.standardOutput = o; p.standardError = Pipe()
    do { try p.run() } catch { return "" }
    let d = o.fileHandleForReading.readDataToEndOfFile(); p.waitUntilExit()
    return String(decoding: d, as: UTF8.self)
}
func syncGet(_ url: URL, timeout: TimeInterval) -> Data? { nil }
func sha256(_ url: URL) -> String? { nil }
func redact(_ s: String) -> String { s }
func sysctl(_ k: String) -> String { "" }
enum ReleaseSignature { static func verify(zip: URL, signatureBase64: String) -> Bool { false } }
enum Privileged {
    struct Result { let output: String; let error: String?; let cancelled: Bool }
    static func run(_ c: String, timeout: TimeInterval) -> Result { Result(output: "", error: nil, cancelled: false) }
}
final class App: NSObject {
    func send(_ e: String, _ d: Any) {}
    static func runBounded(_ exe: URL, _ args: [String], seconds: Double) -> (status: Int32, out: Data, timedOut: Bool) { (0, Data(), false) }
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
case "cpu":
    print(ArmApps.cpuGate(features: a[2]) ?? "OK")
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
    arm("a request with no prior decision turns ARM apps on (installed profile's windows_candidates)",
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
    full = "FPU SSE3 SSSE3 SSE4.1 SSE4.2 POPCNT CX16 AES AVX1.0 AVX2"
    arm("a v2 CPU with AES passes the automatic path's CPU gate", run("cpu", full) == "OK", run("cpu", full))
    out = run("cpu", full.replace(" AES", ""))
    arm("negative control: no AES stops the automatic path before any download", "lacks AES" in out, out)

    # the install line, run in a sandbox: a good package installs; a package swapped after the check does not run
    sandbox = d / "root"; sandbox.mkdir()
    pkgdir = d / "pkg"; (pkgdir / "pkgroot").mkdir(parents=True)
    ran = d / "installer-ran"
    (pkgdir / "pkgroot/install.sh").write_text(f"#!/bin/bash\ntouch '{ran}'\n")
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
    arm("a quote in the SHA-256 yields no command at all", run("install", str(good), "a" * 63 + "'") == "NIL")

    # the uninstall line: absent package = already off; refused when not root-owned or writable by others
    out = subprocess.run(["/bin/bash", "-c", run("uninstall", "jane")], capture_output=True, text=True, timeout=30).stdout
    if not os.path.exists("/Library/NullMoth/arm/uninstall.sh"):
        arm("with nothing installed, turning off reports off", "NULLMOTH_ARM_REMOVED" in out, out.strip())
    fake = d / "uninstall.sh"; fake.write_text(f"#!/bin/bash\necho \"removing $1\"\n")
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

print(f"{fails} failed")
sys.exit(1 if fails else 0)
