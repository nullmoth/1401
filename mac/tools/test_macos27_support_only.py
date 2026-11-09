#!/usr/bin/env python3
"""On macOS 27 this app is a support tool only: it never installs its driver there, and Send logs, the first-login
report and the app's own update keep working and report macOS 27.

The driver this app carries is built for macOS 15 and 26; macOS 27 has its own driver and installer. Three independent
refusals keep it that way: the app (OSGate, before setup is ever started and before a driver download), setup
(driver_os_ok, before the package is even opened) and the page (the install button's reason). Each is exercised here
in both directions. The first-login report on 27 names the display bring-up result, and a go(2) failure counts as a
failure that attaches the macOS 27 files. Negative controls: setup and the app before this change (6474c03) have no
macOS-version refusal for an install."""
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
fails = 0


def arm(name, ok, detail=""):
    global fails
    fails += not ok
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f" ({str(detail).strip()[-400:]})"))


setup = (ROOT / "Resources/nullmoth-setup.sh").read_text()
main = (ROOT / "Sources/main.swift").read_text()
appjs = (ROOT / "Resources/app.js").read_text()
build = (ROOT / "build.sh").read_text()

# 1. setup: driver_os_ok, run on real version strings
fn = re.search(r"^driver_os_ok\(\) \{.*\}$", setup, re.M)
arm("setup defines driver_os_ok", bool(fn))
if fn:
    script = fn.group(0) + '\nfor v in 14.7 15.0 15.7.1 26.0 26.7.1 27.0 27.2 28.0 "" x; do driver_os_ok "$v" && echo "$v=yes" || echo "$v=no"; done\n'
    out = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=30).stdout
    got = dict(line.split("=", 1) for line in out.splitlines())
    arm("setup allows 15.0, 15.7.1, 26.0 and 26.7.1",
        all(got.get(v) == "yes" for v in ("15.0", "15.7.1", "26.0", "26.7.1")), out)
    arm("setup refuses 14.7, 27.0, 27.2, 28.0 and an unreadable version",
        all(got.get(v) == "no" for v in ("14.7", "27.0", "27.2", "28.0", "", "x")), out)
gate = setup.find('driver_os_ok "$(sw_vers -productVersion 2>/dev/null)" || stop')
arm("setup refuses before the package is checked, unpacked or anything is changed",
    0 < gate < setup.index('step "Checking the driver package"') < setup.index("RUNTIME_PREFLIGHT=")
    and "Nothing was changed" in setup[gate:gate + 400])
arm("setup's macOS 27 log collection is not behind the install refusal",
    setup.index('if [ "$(m27_os_major)" -ge 27 ]; then') < gate)
arm("the script still parses", subprocess.run(["/bin/bash", "-n", str(ROOT / "Resources/nullmoth-setup.sh")]).returncode == 0)

# 2. the app: OSGate itself (compiled and run), and where it is called
with tempfile.TemporaryDirectory() as td:
    exe = pathlib.Path(td) / "os_gate"
    c = subprocess.run(["xcrun", "swiftc", "-Onone", str(ROOT / "Sources/OSGate.swift"), str(ROOT / "tests/os_gate/main.swift"),
                        "-o", str(exe)], capture_output=True, text=True, timeout=600)
    r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60) if c.returncode == 0 else None
    arm("OSGate: 15/26 install, 14/27/28 refuse every install mode, support modes stay open on 27",
        r is not None and r.returncode == 0, (r.stdout if r else c.stderr))
run_at = main.index("    func run(mode: String, pkg: String, efi: String, extra: [String], expectedSha: String? = nil) {")
guard = main.find("if let why = OSGate.refusal(mode: mode, major: OSGate.currentMajor)", run_at)
arm("run() refuses an install mode before anything else happens (alert, report file, setup)",
    run_at < guard < main.index("let a = NSAlert()", run_at) < main.index("SavedReports.session", run_at), guard)
upd_at = main.index("    func updateDriver(efi: String) {")
arm("a driver download is refused on 27 before the download is offered",
    main.find("guard OSGate.driverInstallAllowed(major: OSGate.currentMajor)", upd_at) < main.index("NSAlert()", upd_at)
    and main.find("guard OSGate.driverInstallAllowed(major: OSGate.currentMajor)", upd_at) > 0)
arm("the app's own update (updateApp) and Send logs carry no OS gate",
    "OSGate" not in main[main.index("    func updateApp() {"):main.index("    func updateApp() {") + 3000]
    and "OSGate" not in main[main.index("func collectDriverLogs"):main.index("func collectDriverLogs") + 2000])
arm("the profile reports macos_major from the running OS (27 on 27)",
    'p["macos_major"] = ProcessInfo.processInfo.operatingSystemVersion.majorVersion' in main)
arm("the build runs the OS gate test and compiles OSGate into the app",
    "tests/os_gate/main.swift" in build and 'Sources/OSGate.swift "$HASHES"' in build)
arm("nothing a 2.x user sees mentions another driver or macOS 27 (the page, the app's and setup's refusals)",
    "macOS 27" not in appjs and "27 driver" not in (ROOT / "Sources/OSGate.swift").read_text()
    and "27 driver" not in setup and "[15, 26].includes(m.major)" in appjs)
arm("on any other macOS a driver release is never offered, and the bundled package is never downloaded",
    '"newer": driverOK && (have.isEmpty' in main and "let driverOK = OSGate.driverInstallAllowed(major: OSGate.currentMajor)" in main
    and main.index("guard OSGate.driverInstallAllowed", main.index("    func download() {")) < main.index("startDownload(name: Package.name"))

# 3. the first-login report on 27
harness_src = (ROOT / "tools/test_reached_desktop.py").read_text()
stubs = harness_src[harness_src.index("harness = r'''") + len("harness = r'''"):harness_src.index("// (a) no consent")]
checks = r'''
let up = "+-o NVRM  <class NVRM, id 0x1, registered>\n    \"nvrm-autogo\" = \"up\"\n"
let bad = "+-o NVRM  <class NVRM, id 0x1, registered>\n    \"nvrm-autogo\" = \"go(2) failed\"\n"
print("l_up=" + ReachedDesktop.macos27DisplayLine(ioreg: up, heads: "1\n", starts: "%01"))
print("l_bad=" + ReachedDesktop.macos27DisplayLine(ioreg: bad, heads: "0", starts: "%02"))
print("l_none=" + ReachedDesktop.macos27DisplayLine(ioreg: "", heads: "", starts: ""))
let base = "1401 reached the desktop\n\nMetal device: yes (NVMTL)\nNVIDIA driver loaded (com.nullmoth): yes\n"
print("s_up=" + ReachedDesktop.failureSigns(base + ReachedDesktop.macos27DisplayLine(ioreg: up, heads: "1", starts: "") + "\n").joined(separator: "|"))
print("s_bad=" + ReachedDesktop.failureSigns(base + ReachedDesktop.macos27DisplayLine(ioreg: bad, heads: "0", starts: "") + "\n").joined(separator: "|"))
print("files=" + ReachedDesktop.driverFiles.joined(separator: "|"))
'''
with tempfile.TemporaryDirectory() as home:
    d = pathlib.Path(home)
    (d / "main.swift").write_text(stubs + checks)
    c = subprocess.run(["xcrun", "swiftc", "-Onone", str(ROOT / "Sources/ReachedDesktop.swift"), str(d / "main.swift"),
                        "-o", str(d / "t")], capture_output=True, text=True, timeout=600)
    out = subprocess.run([str(d / "t")], capture_output=True, text=True, timeout=60,
                         env={"HOME": str(d), "PATH": "/usr/bin:/bin"}).stdout if c.returncode == 0 else c.stderr
vals = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
arm("first-login report on 27: a working bring-up reads autogo up, its heads and the guard",
    vals.get("l_up") == "macOS 27 display: autogo up, heads 1, nv-starts %01", out)
arm("  a failed one reads go(2) failed with 0 heads",
    vals.get("l_bad") == "macOS 27 display: autogo go(2) failed, heads 0, nv-starts %02", out)
arm("  no NVRM at all reads absent, not up", vals.get("l_none", "").startswith("macOS 27 display: autogo absent"), out)
arm("  go(2) failed is a failure sign (it attaches the logs); up is not",
    vals.get("s_bad") == "display go(2) failed" and vals.get("s_up") == "", out)
arm("  the macOS 27 collector files ride along with a failure report",
    all(f in vals.get("files", "") for f in ("macos27-state.txt", "macos27-bringup-logs.txt")), out)
rd = (ROOT / "Sources/ReachedDesktop.swift").read_text()
arm("  the line is added only on macOS 27 and later",
    "if ProcessInfo.processInfo.operatingSystemVersion.majorVersion >= 27 { s += macos27DisplayLine()" in rd)

old_setup = subprocess.run(["git", "-C", str(ROOT), "show", "6474c03:mac/Resources/nullmoth-setup.sh"], capture_output=True, text=True)
old_main = subprocess.run(["git", "-C", str(ROOT), "show", "6474c03:mac/Sources/main.swift"], capture_output=True, text=True)
arm("negative control: before this change (6474c03) neither setup nor run() refuses an install by macOS version",
    old_setup.returncode == 0 and old_main.returncode == 0 and "driver_os_ok" not in old_setup.stdout
    and "OSGate" not in old_main.stdout, old_setup.stderr + old_main.stderr)

print(f"{fails} failed")
sys.exit(1 if fails else 0)
