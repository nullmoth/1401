import Foundation
for mode in ["dry", "install", "remove"] { assert(AppActions.directRunMode(mode) == mode) }
assert(AppActions.directRunMode(nil) == "dry")
for mode in ["tahoe", "prepare", "update", "finish", "cancel", "usbmap", "verbose", "INSTALL", ""] {
    assert(AppActions.directRunMode(mode) == nil)
}
assert(AppActions.directRunMode(1) == nil)
assert(AppActions.directRunMode(["mode": "prepare"]) == nil)
print("Direct app run messages cannot invoke removed preparation or internal CLI operations.")
