import Foundation

// Privileged.run reports that the command has started, while it is still running (admin: false needs no password).
var failures = 0
func arm(_ name: String, _ ok: Bool, _ detail: String = "") {
    print((ok ? "  ok   " : "  FAIL ") + name + (detail.isEmpty ? "" : "   [\(detail)]"))
    if !ok { failures += 1 }
}

let lock = NSLock()
var startedAt: Date? = nil
let begun = Date()
let r = Privileged.run("/bin/sleep 3; echo finished", timeout: 30, admin: false, started: {
    lock.lock(); startedAt = Date(); lock.unlock()
})
let ended = Date()
lock.lock(); let s = startedAt; lock.unlock()
arm("the started call comes while the command is still running", s != nil && s! < ended.addingTimeInterval(-1.5),
    s.map { String(format: "started %.2fs, ended %.2fs", $0.timeIntervalSince(begun), ended.timeIntervalSince(begun)) } ?? "never called")
arm("the command's output still comes back", r.output.contains("finished") && r.error == nil, r.output)

var calls = 0
let q = Privileged.run("echo quick", timeout: 30, admin: false, started: { lock.lock(); calls += 1; lock.unlock() })
Thread.sleep(forTimeInterval: 1)
lock.lock(); let n = calls; lock.unlock()
arm("a command that finishes at once calls started at most once", n <= 1 && q.output.contains("quick"), "calls=\(n)")

let none = Privileged.run("echo plain", timeout: 30, admin: false)
arm("no callback is fine", none.output.contains("plain") && none.error == nil)
if failures > 0 { exit(1) }
