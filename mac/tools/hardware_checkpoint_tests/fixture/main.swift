// Copyright (c) 2026 NullMoth Systems.
import Foundation
import Darwin
let mode = URL(fileURLWithPath: CommandLine.arguments[0]).lastPathComponent
let base: [String: Any] = ["schema": "nullmoth-hardware-map/1", "status": "observed", "nodes": [["kind": "pci", "id": "n0"]], "cpu": ["status": "observed", "cores": 8]]
func write(_ data: Data) { try! FileHandle.standardOutput.write(contentsOf: data) }
func row(_ map: [String: Any], newline: Bool = true) -> Data {
    var data = try! JSONSerialization.data(withJSONObject: map, options: [.sortedKeys]); if newline { data.append(10) }; return data
}
if mode == "legacy" { write(row(base)); exit(0) }
if mode == "invalid-baseline" { write(Data("unrelated text\n".utf8)); exit(0) }
if mode == "unavailable-overnodes" {
    var bad = base; bad["status"] = "unavailable"; bad["nodes"] = Array(repeating: ["kind": "pci"], count: 2049)
    bad["collector_checkpoint"] = "baseline"; write(row(bad)); exit(0)
}
var bytes = 0
precondition(HardwareMapWorker.emitCheckpoint(base, phase: "baseline", bytesWritten: &bytes))
var final = base; final["peripheral_facts"] = ["status": "observed", "audio": []]
if mode == "timeout" || mode == "signal" {
    try! String(getpid()).write(toFile: CommandLine.arguments[0] + ".pid", atomically: true, encoding: .utf8)
    if mode == "signal" { kill(getpid(), SIGKILL) }
    usleep(10_000_000); exit(0)
}
if mode == "failure" { exit(86) }
if mode == "malformed" { write(Data("{bad}\n".utf8)); exit(0) }
if mode == "truncated" { final["collector_checkpoint"] = "final"; write(row(final, newline: false)); exit(86) }
if mode == "truncated-success" { final["collector_checkpoint"] = "final"; write(row(final, newline: false)); exit(0) }
if mode == "overflow" { write(Data(repeating: 120, count: HardwareMapWorker.outputLimit)); exit(0) }
if mode == "small-cap" { final["padding"] = String(repeating: "x", count: 1000) }
if mode == "changed-baseline" { final["nodes"] = [] }
if mode == "missing-baseline-field" { final.removeValue(forKey: "cpu") }
if mode == "wrong-phase" { final["collector_checkpoint"] = "baseline"; write(row(final)); exit(0) }
if mode == "overnodes-final" { final["status"] = "unavailable"; final["nodes"] = Array(repeating: ["kind": "pci"], count: 2049) }
if mode == "missing-final" { exit(0) }
if mode == "emitter-cap" {
    final["peripheral_facts"] = ["payload": String(repeating: "x", count: HardwareMapWorker.outputLimit)]
    precondition(!HardwareMapWorker.emitCheckpoint(final, phase: "final", bytesWritten: &bytes)); exit(75)
}
if mode == "normal" || mode == "third-record" || mode == "empty-extra" {
    precondition(HardwareMapWorker.emitCheckpoint(final, phase: "final", bytesWritten: &bytes))
} else { final["collector_checkpoint"] = "final"; write(row(final)) }
if mode == "third-record" { write(row(final)) }
if mode == "empty-extra" { write(Data([10])) }
if mode == "final-then-failure" { exit(86) }
if mode == "final-then-timeout" || mode == "final-then-signal" {
    try! String(getpid()).write(toFile: CommandLine.arguments[0] + ".pid", atomically: true, encoding: .utf8)
    if mode == "final-then-signal" { kill(getpid(), SIGKILL) }
    usleep(10_000_000)
}
exit(0)
