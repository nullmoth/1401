import Foundation

var failures = 0
func arm(_ name: String, _ ok: Bool) { print((ok ? "  ok   " : "  FAIL ") + name); if !ok { failures += 1 } }

let dir = NSTemporaryDirectory() + "cfgchoice-\(getpid())"
try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
let good = dir + "/config.plist"
FileManager.default.createFile(atPath: good, contents: Data("x".utf8))
let notPlist = dir + "/config.txt"
FileManager.default.createFile(atPath: notPlist, contents: Data("x".utf8))
let folder = dir + "/folder.plist"
try? FileManager.default.createDirectory(atPath: folder, withIntermediateDirectories: true)

arm("a picked plain .plist file is accepted", ConfigChoice.path("config:" + good) == good)
arm("a partition id and auto are not config choices", ConfigChoice.path("disk0s1") == nil && ConfigChoice.path("auto") == nil && ConfigChoice.path("") == nil)
arm("a missing file, a non-plist, a folder and a relative path are refused",
    ConfigChoice.path("config:" + dir + "/none.plist") == nil && ConfigChoice.path("config:" + notPlist) == nil
    && ConfigChoice.path("config:" + folder) == nil && ConfigChoice.path("config:config.plist") == nil)
arm("a path with a newline is refused", ConfigChoice.path("config:" + good + "\n--remove") == nil)
try? FileManager.default.removeItem(atPath: dir)
if failures > 0 { exit(1) }
