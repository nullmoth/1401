// 1401
// Copyright (c) 2026 NullMoth Systems. SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

import Foundation
import CryptoKit
import IOKit
import Metal

// A one-time confirmation that the Mac reached its desktop after a 1401 install. Today nothing tells us whether an
// install actually booted through to a logged-in desktop: a machine that fails silently and one that works both go
// quiet, so a working install is indistinguishable from a dead one. When the user agrees during setup, the first login
// after the install sends one small, redacted summary of what reached the desktop, then takes itself back out. It is
// opt-in, runs at most once per install, and removes its own login item after it sends (or after a few failed tries),
// so nothing is left running - the 2.2 driver carries no other background job. It rides the same login-item mechanism,
// redaction and upload as the AMD/Intel test report (TesterLane).
enum ReachedDesktop {
    static let stateFile = support.appendingPathComponent("reached-desktop.json")
    static let agentLabel = "com.nullmoth.reacheddesktop"
    // The login item that sends it. Only a few starts are tried before it gives up, so a machine that can never reach
    // the site does not keep a dead item forever.
    static let maxTries = 5
    static var agentFile: URL {
        FileManager.default.urls(for: .libraryDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("LaunchAgents/\(agentLabel).plist")
    }

    static func state() -> [String: Any] {
        (try? JSONSerialization.jsonObject(with: Data(contentsOf: stateFile))) as? [String: Any] ?? [:]
    }

    static func save(_ s: [String: Any]) {
        try? FileManager.default.createDirectory(at: support, withIntermediateDirectories: true)
        if let d = try? JSONSerialization.data(withJSONObject: s, options: [.prettyPrinted, .sortedKeys]) {
            try? d.write(to: stateFile, options: .atomic)
        }
    }

    /// Arms or disarms the one-time report after an install. With consent it writes the login item that runs
    /// `1401 --reached-desktop` once at the next login; without consent it installs nothing and clears anything a
    /// previous install left, so the honest default (the user did not agree) leaves no item and sends nothing.
    /// Returns the reason it could not arm, or nil.
    @discardableResult
    static func arm(consent: Bool) -> String? {
        let fm = FileManager.default
        if !consent { remove(); return nil }
        // The item runs this exact copy of 1401 at login; refuse it when 1401 sits where another user could replace it
        // (the item would then run that user's program in this login session), the same guard the test program uses.
        guard let exe = Bundle.main.executableURL?.resolvingSymlinksInPath() else { return "1401's own path is unknown" }
        var dir = exe.deletingLastPathComponent()
        while dir.path != "/" {
            if let a = try? fm.attributesOfItem(atPath: dir.path), let p = a[.posixPermissions] as? Int, p & 0o002 != 0 {
                return "1401 is in a folder other users can change (\(dir.path)); move it into Applications first"
            }
            dir = dir.deletingLastPathComponent()
        }
        let plist: [String: Any] = ["Label": agentLabel, "ProgramArguments": [exe.path, "--reached-desktop"],
                                    "RunAtLoad": true, "ProcessType": "Background", "LowPriorityIO": true]
        do {
            try fm.createDirectory(at: agentFile.deletingLastPathComponent(), withIntermediateDirectories: true)
            let d = try PropertyListSerialization.data(fromPropertyList: plist, format: .xml, options: 0)
            try d.write(to: agentFile, options: .atomic)
        } catch { return "could not write the login item: \(error.localizedDescription)" }
        save(["consent": true, "tries": 0, "armed": ISO8601DateFormatter().string(from: Date())])
        return nil
    }

    /// Takes the login item back out and forgets its state, so nothing of it is left running or on disk.
    static func remove() {
        _ = sh("/bin/launchctl", ["bootout", "gui/\(getuid())", agentFile.path])
        try? FileManager.default.removeItem(at: agentFile)
        try? FileManager.default.removeItem(at: stateFile)
    }

    /// What reached the desktop: the macOS build, the Mac's model and CPU, every display-class PCI device, whether
    /// Metal and the NVIDIA driver came up, 1401's version and OpenCore's. Identities are stripped by `redact` before
    /// it leaves, exactly as Send logs does. The notes begin with a fixed tag so the catalog can find these uploads.
    static func summary() -> String {
        let os = sh("/usr/bin/sw_vers", ["-productVersion"]).trimmingCharacters(in: .whitespacesAndNewlines)
        let build = sh("/usr/bin/sw_vers", ["-buildVersion"]).trimmingCharacters(in: .whitespacesAndNewlines)
        let model = sysctl("hw.model")
        let cpu = sysctl("machdep.cpu.brand_string")
        let gpus = pciDisplays().map { "\($0["vendor"] ?? "?"):\($0["device"] ?? "?") \($0["model"] as? String ?? "")".trimmingCharacters(in: .whitespaces) }
        let metal = MTLCreateSystemDefaultDevice()
        let loaded = sh("/usr/bin/kmutil", ["showloaded", "--list-only"]).split(separator: "\n").contains { $0.contains("com.nullmoth") }
        let oc = sh("/usr/sbin/nvram", ["4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102:opencore-version"])
            .split(separator: "\t").last.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) } ?? "unknown"
        let app = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?"
        var s = "1401 reached the desktop\n\n"
        s += "macOS \(os) (\(build))\n"
        s += "model: \(model)\n"
        s += "cpu: \(cpu)\n"
        s += "display PCI: \(gpus.isEmpty ? "(none reported)" : gpus.joined(separator: "; "))\n"
        s += "Metal device: \(metal.map { "yes (\($0.name))" } ?? "no")\n"
        s += "NVIDIA driver loaded (com.nullmoth): \(loaded ? "yes" : "no")\n"
        s += "1401 Mac \(app)\n"
        s += "OpenCore: \(oc)\n"
        return s
    }

    /// Sends the one-time confirmation. Does nothing unless the user agreed and it has not already been sent. On a
    /// success it removes its own login item; on a failed send it counts the try and gives up (also removing the item)
    /// after a few starts, so a machine that can never reach the site is not left running it start after start.
    static func report() -> Int32 {
        var s = state()
        guard (s["consent"] as? Bool) == true, (s["sent"] as? Bool) != true else { return 0 }
        let body = Data(redact(summary()).utf8)
        let sha = SHA256.hash(data: body).map { String(format: "%02x", $0) }.joined()
        var req = URLRequest(url: URL(string: "https://nullmothsystems.com/api/upload")!, timeoutInterval: 60)
        req.httpMethod = "POST"; req.httpBody = body
        req.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        req.setValue("reached-desktop.txt", forHTTPHeaderField: "X-File-Name")
        // the fixed "reached desktop" tag leads the notes so the catalog classifies these as a success, not a Mac log
        let notes = "reached desktop; 1401 Mac \(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?") (first login after install)"
        let meta = try! JSONSerialization.data(withJSONObject: ["consent": true, "notes": notes, "batch": newUploadBatch()])
        req.setValue(meta.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: ""), forHTTPHeaderField: "X-Meta")
        req.setValue(sha, forHTTPHeaderField: "X-Content-SHA256")
        let done = DispatchSemaphore(value: 0); let result = ReportUploadResult()
        let task = URLSession.shared.dataTask(with: req) { d, r, e in result.finish(data: d, response: r, error: e, sha256: sha); done.signal() }
        task.resume()
        let timedOut = done.wait(timeout: .now() + 90) == .timedOut
        if timedOut { task.cancel() }
        return advance(sent: result.take(timedOut: timedOut).0 != nil)
    }

    /// The outcome of one send attempt. On a success it takes the login item back out and leaves nothing behind; on a
    /// failure it counts the try and, once a few starts have failed, gives up and takes the item out too, so a machine
    /// that can never reach the site is not left running it login after login. Kept apart from the transport so the
    /// once-and-remove and the bounded-retry behaviour can be exercised without the network.
    @discardableResult
    static func advance(sent: Bool) -> Int32 {
        if sent {
            remove()
            print("reached-desktop report: sent")
            return 0
        }
        let tries = (state()["tries"] as? Int ?? 0) + 1
        if tries >= maxTries {
            remove()
            print("reached-desktop report: gave up after \(tries) tries")
            return 1
        }
        var s = state(); s["tries"] = tries; save(s)
        print("reached-desktop report: not sent (try \(tries) of \(maxTries))")
        return 1
    }
}
