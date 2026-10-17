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
arm("what is sent is redacted first, like Send logs", "redact(summary())" in reportf)
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
                      ("1401's version", "CFBundleShortVersionString"), ("OpenCore's version", "opencore-version")]:
    arm(f"the summary reports {label}", needle in summ)

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
func newUploadBatch() -> String { return "batch" }
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
except subprocess.CalledProcessError as e:
    arm("the behaviour harness compiles", False, (e.stderr or b"").decode()[:600])
except FileNotFoundError:
    arm("the Swift toolchain is available for the behaviour harness", False)

print(f"{fails} failed")
sys.exit(1 if fails else 0)
