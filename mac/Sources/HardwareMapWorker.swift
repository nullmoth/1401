// Copyright (c) 2026 NullMoth Systems.
import Foundation
import Darwin

enum HardwareMapWorker {
    static func unavailable(_ reason: String) -> [String: Any] {
        ["schema": "nullmoth-hardware-map/1", "status": "unavailable", "source": "bounded local hardware collector",
         "reason": reason, "qualification": "not assessed"]
    }

    static let outputLimit = 2 * 1024 * 1024

    static func validMap(_ map: [String: Any]) -> Bool {
        guard map["schema"] as? String == "nullmoth-hardware-map/1",
              let status = map["status"] as? String,
              ["observed", "partial", "unavailable"].contains(status) else { return false }
        if let nodes = map["nodes"] {
            guard let list = nodes as? [[String: Any]], list.count <= 2048 else { return false }
        } else if status != "unavailable" { return false }
        return true
    }

    // Exact child-only protocol; the combined baseline and final output retains the byte cap.
    static func emitCheckpoint(_ map: [String: Any], phase: String, bytesWritten: inout Int) -> Bool {
        guard CommandLine.arguments == [CommandLine.arguments[0], "--hardware-map"],
              ["baseline", "final"].contains(phase), validMap(map),
              bytesWritten >= 0, bytesWritten <= outputLimit,
              (phase == "baseline") == (bytesWritten == 0) else { return false }
        var record = map
        record["collector_checkpoint"] = phase
        guard var data = try? JSONSerialization.data(withJSONObject: record, options: [.sortedKeys]),
              data.count < outputLimit - bytesWritten else { return false }
        data.append(0x0a)
        do { try FileHandle.standardOutput.write(contentsOf: data) }
        catch { return false }
        bytesWritten += data.count
        return true
    }

    static func select(_ data: Data, completed: Bool, failure: String?, exceededLimit: Bool = false) -> [String: Any] {
        guard data.count <= outputLimit + 1 else { return unavailable("collector output exceeded its limit; other logs retained") }
        // Accept the legacy one-map format only after a successful process exit within the byte cap.
        if completed, !exceededLimit,
           let legacy = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
           legacy["collector_checkpoint"] == nil, validMap(legacy) { return legacy }
        let lines = data.split(separator: 0x0a, omittingEmptySubsequences: false)
        guard lines.count >= 2,
              let baseline = (try? JSONSerialization.jsonObject(with: Data(lines[0]))) as? [String: Any],
              validMap(baseline), baseline["collector_checkpoint"] as? String == "baseline",
              baseline["peripheral_facts"] == nil else {
            return unavailable("collector baseline checkpoint invalid; other logs retained")
        }
        func retained(_ reason: String) -> [String: Any] {
            var map = baseline
            map.removeValue(forKey: "collector_checkpoint")
            if map["status"] as? String != "unavailable" { map["status"] = "partial" }
            map["collector_outcome"] = reason
            map["peripheral_facts"] = ["status": "unavailable", "source": "bounded native metadata child", "reason": reason]
            return map
        }
        // Only two complete protocol records are accepted. Never parse arbitrary trailing output.
        if !completed { return retained(failure ?? "collector did not complete normally") }
        if exceededLimit { return retained("optional metadata output exceeded byte limit; completed map retained") }
        if lines.count == 2 {
            return retained(failure ?? (lines[1].isEmpty ? "optional metadata final checkpoint missing" : "optional metadata final checkpoint incomplete"))
        }
        guard lines.count == 3, lines[2].isEmpty,
              let final = (try? JSONSerialization.jsonObject(with: Data(lines[1]))) as? [String: Any],
              validMap(final), final["collector_checkpoint"] as? String == "final" else {
            return retained("optional metadata final checkpoint invalid; completed map retained")
        }
        var baselineFields = baseline
        baselineFields.removeValue(forKey: "collector_checkpoint")
        var finalFields = final
        finalFields.removeValue(forKey: "collector_checkpoint")
        finalFields.removeValue(forKey: "peripheral_facts")
        guard final["peripheral_facts"] is [String: Any],
              let baselineBytes = try? JSONSerialization.data(withJSONObject: baselineFields, options: [.sortedKeys]),
              let finalBytes = try? JSONSerialization.data(withJSONObject: finalFields, options: [.sortedKeys]),
              baselineBytes == finalBytes else {
            return retained("optional metadata final checkpoint changed completed map; baseline retained")
        }
        var map = final
        map.removeValue(forKey: "collector_checkpoint")
        return map
    }

    static func run(executable: URL, arguments: [String] = ["--hardware-map"],
                    timeout: Double = 5, maximumBytes: Int = 2 * 1024 * 1024) -> [String: Any] {
        let fm = FileManager.default
        let directory = fm.temporaryDirectory.appendingPathComponent("1401-map-" + UUID().uuidString, isDirectory: true)
        do { try fm.createDirectory(at: directory, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700]) }
        catch { return unavailable("collector output directory unavailable") }
        defer { try? fm.removeItem(at: directory) }
        let output = directory.appendingPathComponent("output.json")
        guard fm.createFile(atPath: output.path, contents: nil, attributes: [.posixPermissions: 0o600]),
              let file = try? FileHandle(forWritingTo: output) else { return unavailable("collector output unavailable") }
        defer { try? file.close() }
        let child = Process()
        child.executableURL = executable; child.arguments = arguments
        child.standardOutput = file; child.standardError = FileHandle.nullDevice
        child.standardInput = FileHandle.nullDevice
        let exited = DispatchSemaphore(value: 0)
        child.terminationHandler = { _ in exited.signal() }
        do { try child.run() } catch { return unavailable("collector could not start") }
        var failure: String?
        if exited.wait(timeout: .now() + min(max(timeout, 0.05), 8)) == .timedOut {
            if child.isRunning { kill(child.processIdentifier, SIGKILL) }
            guard exited.wait(timeout: .now() + 0.5) == .success else {
                return unavailable("collector did not reap within its bound; other logs retained")
            }
            failure = "optional metadata collector timed out; completed map retained"
        } else if child.terminationReason != .exit || child.terminationStatus != 0 {
            failure = "optional metadata collector failed; completed map retained"
        }
        let limit = min(max(maximumBytes, 1), outputLimit)
        guard let read = try? FileHandle(forReadingFrom: output) else { return unavailable("collector output unreadable") }
        defer { try? read.close() }
        guard let data = try? read.read(upToCount: limit + 1) else {
            return unavailable("collector output unreadable; other logs retained")
        }
        let exceeded = data.count > limit
        return select(Data(data.prefix(limit)), completed: failure == nil, failure: failure, exceededLimit: exceeded)
    }
}
