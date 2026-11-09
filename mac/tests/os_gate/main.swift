import Foundation
// The 2.x app never installs the driver on macOS 27: the driver it carries is for 15 and 26, and 27 has its own.
// Support (Send logs, the first-login report, the app's own update) stays available on every macOS.
var failed = 0
func check(_ ok: Bool, _ what: String) { if ok { print("ok   " + what) } else { failed += 1; print("FAIL " + what) } }
check(OSGate.driverInstallAllowed(major: 15) && OSGate.driverInstallAllowed(major: 26), "macOS 15 and 26 may install the driver")
for major in [14, 27, 28] {
    check(!OSGate.driverInstallAllowed(major: major), "macOS \(major) may not install the driver")
    for mode in ["install", "tahoe", "dry"] {
        check(OSGate.refusal(mode: mode, major: major) != nil, "setup mode \(mode) is refused on macOS \(major)")
    }
}
for mode in ["install", "tahoe", "dry"] {
    check(OSGate.refusal(mode: mode, major: 26) == nil, "setup mode \(mode) still runs on macOS 26")
}
for mode in ["remove", "usbmap", "verbose", "tahoecancel"] {
    check(OSGate.refusal(mode: mode, major: 27) == nil, "setup mode \(mode) (no driver install) is not refused on macOS 27")
}
check(OSGate.refusal(major: 27).contains("macOS 15") && OSGate.refusal(major: 27).contains("runs macOS 27")
      && !OSGate.refusal(major: 27).contains("27 driver"),
      "the refusal names the macOS this driver is for and the one this Mac runs, and offers nothing else")
print("\(failed) failed"); exit(failed == 0 ? 0 : 1)
