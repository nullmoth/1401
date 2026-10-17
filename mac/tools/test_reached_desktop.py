#!/usr/bin/env python3
"""The one-time "reached the desktop" confirmation (Sources/ReachedDesktop.swift): opt-in during setup, sent once at the
first login after an install, and self-removing. The arms below read the Swift for the rules, then compile the real
ReachedDesktop with the install's surrounding calls stubbed and a throwaway HOME, and prove the behaviour: (a) without
consent nothing is armed and nothing is sent, (b) with consent the login item is written, runs the report binary, and is
taken back out once a send succeeds, and (c) a send that keeps failing is retried a bounded number of times and then
removed too. No network is used: the send is driven directly through its outcome."""
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
src = (ROOT / "Sources/ReachedDesktop.swift").read_text()
main = (ROOT / "Sources/main.swift").read_text()
fails = 0


def arm(name, ok, detail=""):
    global fails
    print(("ok   " if ok else "FAIL ") + name + (f" ({detail})" if detail else ""))
    fails += not ok


# --- the rules, read from the source ---
armf = src.split("static func arm(", 1)[1].split("static func remove(", 1)[0]
arm("without consent it arms nothing and clears any prior arming",
    "if !consent { remove(); return nil }" in armf)
arm("arming is refused when another user could replace 1401", "p & 0o002 != 0" in armf)
arm("the login item runs the reached-desktop report once at login",
    '"--reached-desktop"' in armf and '"RunAtLoad": true' in armf)
arm("the installed app dispatches the reached-desktop report",
    'argv.contains("--reached-desktop")' in main and "ReachedDesktop.report()" in main)

reportf = src.split("static func report()", 1)[1].split("static func advance(", 1)[0]
arm("the report does nothing without consent or once already sent",
    '(s["consent"] as? Bool) == true' in reportf and '(s["sent"] as? Bool) != true' in reportf)
arm("what is sent is redacted first, like Send logs", "let text = summary()" in reportf and "redact(text)" in reportf)
arm("a first login where the driver did not come up sends the driver files, a clean one the short text alone",
    "let signs = failureSigns(text)" in reportf and "if !signs.isEmpty { return advance(sent: reportFailure(text, signs: signs)) }" in reportf
    and '"reached-desktop.txt", forHTTPHeaderField: "X-File-Name"' in reportf)
failf = src.split("static func reportFailure(", 1)[1].split("static func advance(", 1)[0]
arm("the failed report goes through Send logs' own upload path, one batch", "uploadReports(files: [summaryFile] + gathered.files" in failf
    and "newUploadBatch()" in failf)
arm("its notes lead with the reached-desktop tag", '"reached desktop; 1401 Mac' in failf)
arm("the driver files are collected by the same collector scripts, in their driver scope, with no password",
    'NULLMOTH_COLLECT_SCOPE=driver' in main and 'admin: false' in main.split("func collectDriverLogs(into dir: URL)", 1)[1].split("\n}\n", 1)[0]
    and "nullmoth-log-capture.sh" in main.split("func collectDriverLogs(into dir: URL)", 1)[1].split("\n}\n", 1)[0])
setup = (ROOT / "Resources/nullmoth-setup.sh").read_text()
capture = (ROOT / "Resources/nullmoth-log-capture.sh").read_text()
arm("the collector's driver scope runs without root and keeps the driver sections only",
    'SCOPE=${NULLMOTH_COLLECT_SCOPE:-full}' in setup and '[ "$SCOPE" = driver ]; } ||' in setup
    and setup.count("want full") >= 8 and 'elif [ "${NULLMOTH_COLLECT_SCOPE:-}" = driver ]; then' in capture)
arm("it posts to the same upload endpoint", "nullmothsystems.com/api/upload" in reportf)
arm("the notes lead with the fixed reached-desktop tag so the catalog can find it",
    '"reached desktop;' in reportf)

advf = src.split("static func advance(", 1)[1]
arm("a successful send removes the login item", "if sent {\n            remove()" in advf)
arm("a bounded number of failed tries, then it removes itself too",
    "tries >= maxTries" in advf and "remove()" in advf.split("tries >= maxTries", 1)[1])

summ = src.split("static func summary()", 1)[1].split("static func report()", 1)[0]
for label, needle in [("macOS version and build", "sw_vers"), ("Mac model", 'sysctl("hw.model")'),
                      ("CPU brand", 'sysctl("machdep.cpu.brand_string")'), ("display PCI devices", "pciDisplays()"),
                      ("a Metal device", "MTLCreateSystemDefaultDevice()"), ("the NVIDIA driver", "com.nullmoth"),
                      ("1401's version", "CFBundleShortVersionString"), ("OpenCore's version", "opencore-version"),
                      ("each display's mode", "displayModes()"), ("the installed driver binaries' hashes", "installedComponents()")]:
    arm(f"the summary reports {label}", needle in summ)
# the release gate counts a "reached desktop" as a boot receipt for the exact binaries that ran: every component by path
comps = src.split("static let components:", 1)[1].split("= [", 1)[1].split("]", 1)[0]
for name, path in [("NVRM", "/Library/Extensions/NVRM.kext/Contents/MacOS/NVRM"),
                   ("NVAccel", "/Library/Extensions/NVAccel.kext/Contents/MacOS/NVAccel"),
                   ("NVRMFB", "/Library/Extensions/NVRMFB.kext/Contents/MacOS/NVRMFB"),
                   ("NVRMAGDC", "/Library/Extensions/NVRMAGDC.kext/Contents/MacOS/NVRMAGDC"),
                   ("NVMTLDriver", "/Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver")]:
    arm(f"the installed {name} is hashed from its real path", f'("{name}", "{path}")' in comps)
arm("the recorded driver version rides along", "/Library/NullMoth/driver-version" in summ)
arm("display modes come from CoreGraphics (size and refresh rate per active display)",
    "CGGetActiveDisplayList" in summ and "CGDisplayCopyDisplayMode" in summ and "refreshRate" in summ)

# the install flow asks once, defaults to not sending, and arms only a successful install the user agreed to
runf = main.split("func run(mode:", 1)[1]
arm("the install flow asks for consent and defaults to not sending",
    "reachedDesktopConsent" in runf and 'addButton(withTitle: "Send once after it boots")' in runf
    and "a.runModal() == .alertFirstButtonReturn" in runf)
arm("it is armed only when a real install succeeded and the user agreed",
    "ReachedDesktop.arm(consent: succeeded && reachedDesktopConsent)" in runf)

# --- the behaviour, compiled and run against a throwaway HOME (no network) ---
harness = r'''
import Foundation
// The install's surroundings, stubbed so the state machine can be exercised on its own. `support` and the login item
// resolve under $HOME, which the test points at a throwaway directory; launchctl is a no-op here.
let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("NullMoth")
func sh(_ path: String, _ args: [String]) -> String { return "" }
func sysctl(_ k: String) -> String { return "" }
func redact(_ s: String) -> String { return s }
func pciDisplays() -> [[String: Any]] { return [] }
// The file hasher: a fixed digest for every component but one, which stands for a kext that is not installed.
func sha256(_ url: URL) -> String? { url.path.contains("NVRMAGDC") ? nil : String(repeating: "ab", count: 32) }
func newUploadBatch() -> String { return "batch" }
let logs = FileManager.default.urls(for: .libraryDirectory, in: .userDomainMask)[0].appendingPathComponent("Logs/NullMoth")
// The shared upload path and the driver collector, counted instead of run: every call and every file name is recorded.
struct UploadOutcome { var queued = true; var ids: [String] = []; var errors: [String] = []; var acknowledgements: [[String: String]] = [] }
var uploads: [[String]] = []
func uploadReports(files: [URL], pendingFiles: [URL], in dir: URL, notes: String, batch: String) -> UploadOutcome {
    uploads.append(files.map { $0.lastPathComponent } + [notes])
    var o = UploadOutcome(); o.ids = files.map { _ in "NM-TEST" }
    o.acknowledgements = files.map { ["name": $0.lastPathComponent, "sha256": "x", "id": "NM-TEST"] }
    return o
}
var collectCalls = 0
func collectDriverLogs(into dir: URL) -> [String] {
    collectCalls += 1
    for n in ["driver-state.txt", "driver-kernel-log.txt", "driver-plugin-log.txt", "driver-crash-window.txt",
              "macos-WindowServer-2026-10-17-010203.ips", "gpu-all.txt", "collect.txt"] {
        try? "x".write(to: dir.appendingPathComponent(n), atomically: true, encoding: .utf8)
    }
    return []
}
enum SavedReports {
    static func session(in root: URL) throws -> URL {
        let d = root.appendingPathComponent("s-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: d, withIntermediateDirectories: true); return d
    }
    static func create(_ data: Data, in dir: URL, name: String) throws -> URL {
        let u = dir.appendingPathComponent(name); try data.write(to: u); return u
    }
}
final class ReportUploadResult: @unchecked Sendable {
    func finish(data: Data?, response: URLResponse?, error: Error?, sha256: String) {}
    func take(timedOut: Bool) -> (String?, String?) { return (nil, "stub") }
}

func exists(_ u: URL) -> Bool { FileManager.default.fileExists(atPath: u.path) }

// (a) no consent: nothing armed, nothing on disk
ReachedDesktop.arm(consent: false)
print("a_agent=\(exists(ReachedDesktop.agentFile))")
print("a_state=\(exists(ReachedDesktop.stateFile))")

// (b) consent: the login item is written and runs the report; one success takes it back out
let e = ReachedDesktop.arm(consent: true)
let plist = (try? String(contentsOf: ReachedDesktop.agentFile, encoding: .utf8)) ?? ""
print("b_armerr=\(e ?? "")")
print("b_agent=\(exists(ReachedDesktop.agentFile))")
print("b_flag=\(plist.contains("--reached-desktop"))")
print("b_consent=\((ReachedDesktop.state()["consent"] as? Bool) ?? false)")
print("b_tries=\((ReachedDesktop.state()["tries"] as? Int) ?? -1)")
let rc = ReachedDesktop.advance(sent: true)
print("b_rc=\(rc)")
print("b_agent_after=\(exists(ReachedDesktop.agentFile))")
print("b_state_after=\(exists(ReachedDesktop.stateFile))")

// (c) consent, but every send fails: retried a bounded number of times, then removed
_ = ReachedDesktop.arm(consent: true)
var traj: [String] = []
for i in 1...ReachedDesktop.maxTries {
    let r = ReachedDesktop.advance(sent: false)
    traj.append("\(i),\(r),\(exists(ReachedDesktop.agentFile)),\((ReachedDesktop.state()["tries"] as? Int) ?? -1)")
}
print("c_max=\(ReachedDesktop.maxTries)")
print("c_traj=" + traj.joined(separator: "|"))

// (d) the report text itself, as it would be sent (one line, base64, so the test can parse it whole)
print("d_summary=" + Data(ReachedDesktop.summary().utf8).base64EncodedString())

// (e) a first login where the driver did not come up attaches the driver files; a clean one collects nothing
let clean = "1401 reached the desktop\n\nMetal device: yes (NVIDIA GeForce RTX 3060)\nNVIDIA driver loaded (com.nullmoth): yes\n"
    + "installed NVRM: " + String(repeating: "ab", count: 32) + "\ninstalled NVMTLDriver: " + String(repeating: "cd", count: 32) + "\n"
let failed = "1401 reached the desktop\n\nMetal device: no\nNVIDIA driver loaded (com.nullmoth): no\n"
    + "installed NVRM: (not present)\ninstalled NVAccel: " + String(repeating: "ab", count: 32) + "\n"
print("e_clean_signs=\(ReachedDesktop.failureSigns(clean).count)")
print("e_failed_signs=" + ReachedDesktop.failureSigns(failed).joined(separator: ","))
let d1 = try! SavedReports.session(in: support)
let a1 = ReachedDesktop.attachments(for: clean, into: d1)
print("e_clean_calls=\(collectCalls)")
print("e_clean_files=\(a1.files.count)")
let d2 = try! SavedReports.session(in: support)
let a2 = ReachedDesktop.attachments(for: failed, into: d2)
print("e_failed_calls=\(collectCalls)")
print("e_failed_files=" + a2.files.map { $0.lastPathComponent }.joined(separator: ","))
let ok = ReachedDesktop.reportFailure(failed, signs: ReachedDesktop.failureSigns(failed))
print("e_report_ok=\(ok)")
print("e_uploads=\(uploads.count)")
print("e_upload_files=" + (uploads.last ?? []).joined(separator: "|"))
'''

try:
    with tempfile.TemporaryDirectory() as home:
        d = pathlib.Path(home)
        (d / "main.swift").write_text(harness)
        exe = d / "t"
        subprocess.run(["xcrun", "swiftc", "-Onone", str(ROOT / "Sources/ReachedDesktop.swift"), str(d / "main.swift"),
                        "-o", str(exe)], check=True, capture_output=True, timeout=600)
        out = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120,
                             env={"HOME": str(d), "PATH": "/usr/bin:/bin"})
        vals = dict(line.split("=", 1) for line in out.stdout.splitlines() if "=" in line)
        arm("(a) no consent: no login item is written", vals.get("a_agent") == "false", out.stdout + out.stderr)
        arm("(a) no consent: no state is written", vals.get("a_state") == "false")
        arm("(b) consent: the login item is written", vals.get("b_armerr") == "" and vals.get("b_agent") == "true",
            vals.get("b_armerr", ""))
        arm("(b) the login item runs the reached-desktop report", vals.get("b_flag") == "true")
        arm("(b) consent is recorded and the try count starts at zero",
            vals.get("b_consent") == "true" and vals.get("b_tries") == "0")
        arm("(b) one successful send removes the login item and its state",
            vals.get("b_rc") == "0" and vals.get("b_agent_after") == "false" and vals.get("b_state_after") == "false")
        # (c) the item survives the first maxTries-1 failures and is gone on the last
        max_tries = int(vals.get("c_max", "0"))
        steps = [s.split(",") for s in vals.get("c_traj", "").split("|") if s]
        shaped = len(steps) == max_tries and max_tries >= 2
        arm("(c) a failed send returns non-zero every time", shaped and all(s[1] == "1" for s in steps),
            vals.get("c_traj", ""))
        arm("(c) the login item is kept through the first tries", shaped and all(s[2] == "true" for s in steps[:-1]),
            vals.get("c_traj", ""))
        arm("(c) after the bounded number of tries it removes itself", shaped and steps[-1][2] == "false",
            vals.get("c_traj", ""))
        # (d) the report text: one hash line per component, 64 hex chars (or "(not present)"), the version, the modes
        import base64, re  # noqa: E401
        text = base64.b64decode(vals.get("d_summary", "")).decode("utf-8", "replace")
        hashes = dict(re.findall(r"^installed ([A-Za-z]+): (.+)$", text, re.M))
        arm("(d) every component has an 'installed <name>:' line",
            sorted(hashes) == ["NVAccel", "NVMTLDriver", "NVRM", "NVRMAGDC", "NVRMFB"], str(sorted(hashes)))
        arm("(d) an installed binary's line is its SHA-256, 64 hex chars",
            all(re.fullmatch(r"[0-9a-f]{64}", hashes.get(n, "")) for n in ("NVRM", "NVAccel", "NVRMFB", "NVMTLDriver")),
            str(hashes))
        arm("(d) a component that is not on disk says so instead of a hash", hashes.get("NVRMAGDC") == "(not present)")
        arm("(d) the recorded driver version has its line", re.search(r"^driver-version: .+$", text, re.M) is not None)
        modes = re.search(r"^display modes: (.+)$", text, re.M)
        arm("(d) the display modes line is present and well formed",
            modes is not None and (modes.group(1).startswith("(no ") or
                                   re.fullmatch(r"(\d+x\d+ @ (\d+(\.\d+)? Hz|unknown Hz))(; \d+x\d+ @ (\d+(\.\d+)? Hz|unknown Hz))*", modes.group(1))),
            modes.group(1) if modes else text[-200:])
        # (e) the driver files ride along only when the driver did not come up
        arm("(e) a clean summary has no failure signs", vals.get("e_clean_signs") == "0")
        arm("(e) a failed summary names what did not come up",
            vals.get("e_failed_signs") == "no Metal device,driver not loaded,NVRM missing", vals.get("e_failed_signs", ""))
        arm("(e) a clean summary does not run the collector and attaches nothing",
            vals.get("e_clean_calls") == "0" and vals.get("e_clean_files") == "0")
        arm("(e) a failed summary runs the collector once", vals.get("e_failed_calls") == "1", vals.get("e_failed_calls", ""))
        arm("(e) and attaches the driver files and the WindowServer crash reports, nothing else",
            vals.get("e_failed_files") == "driver-crash-window.txt,driver-kernel-log.txt,driver-plugin-log.txt,driver-state.txt,"
                                          "macos-WindowServer-2026-10-17-010203.ips", vals.get("e_failed_files", ""))
        up = vals.get("e_upload_files", "").split("|")
        arm("(e) the failed report goes up as one batch: the summary first, then the driver files",
            vals.get("e_uploads") == "1" and up[:1] == ["reached-desktop.txt"] and "driver-state.txt" in up and "driver-plugin-log.txt" in up, str(up))
        arm("(e) its notes keep the reached-desktop tag and say what did not come up",
            up[-1].startswith("reached desktop; ") and "driver did not come up: no Metal device, driver not loaded, NVRM missing" in up[-1], up[-1])
        arm("(e) the report counts as sent when the summary itself was confirmed", vals.get("e_report_ok") == "true")
except subprocess.CalledProcessError as e:
    arm("the behaviour harness compiles", False, (e.stderr or b"").decode()[:600])
except FileNotFoundError:
    arm("the Swift toolchain is available for the behaviour harness", False)

print(f"{fails} failed")
sys.exit(1 if fails else 0)
