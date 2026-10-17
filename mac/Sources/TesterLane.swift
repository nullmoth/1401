// 1401
// Copyright (c) 2026 NullMoth Systems. SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

import Foundation
import CryptoKit

// The AMD/Intel test program. A tester gets the newest signed test build of the AMD/Intel driver, and after every
// restart 1401 sends what that start did: the driver's kernel messages from the previous start and this one, any
// kernel panic since the last report, and which GPUs and builds were in play. The GPU drivers are brought up on
// testers' machines, and a start that panics or hangs is exactly when
// nobody opens 1401 to press Send logs, so the report has to happen on its own. It only runs while the user has
// joined, as their own login item; leaving removes it.
enum Tester {
    static let manifestURL = URL(string: "https://nullmothsystems.com/download/test/amd-intel/manifest.json")!
    static let stateFile = support.appendingPathComponent("tester.json")
    static let agentLabel = "com.nullmoth.tester"
    static var agentFile: URL {
        FileManager.default.urls(for: .libraryDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("LaunchAgents/\(agentLabel).plist")
    }

    struct Build { let version: String, name: String, url: URL, sha256: String, sig: URL }

    static var isOn: Bool { (state()["on"] as? Bool) ?? false }

    static func state() -> [String: Any] {
        (try? JSONSerialization.jsonObject(with: Data(contentsOf: stateFile))) as? [String: Any] ?? [:]
    }

    static func save(_ s: [String: Any]) {
        try? FileManager.default.createDirectory(at: support, withIntermediateDirectories: true)
        if let d = try? JSONSerialization.data(withJSONObject: s, options: [.prettyPrinted, .sortedKeys]) {
            try? d.write(to: stateFile, options: .atomic)
        }
    }

    /// The newest test build the site lists. The manifest only says where to look; the package itself must carry a
    /// detached Ed25519 signature from the release key (ReleaseSignature), checked after download.
    static func latest() -> Build? {
        guard let d = syncGet(manifestURL, timeout: 30),
              let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
              let v = j["version"] as? String, let n = j["name"] as? String, let sha = j["sha256"] as? String,
              let u = (j["url"] as? String).flatMap(URL.init(string:)), u.scheme == "https",
              let s = (j["sig"] as? String).flatMap(URL.init(string:)), s.scheme == "https",
              sha.count == 64, !n.contains("/") else { return nil }
        return Build(version: v, name: n, url: u, sha256: sha, sig: s)
    }

    /// Downloads a test build into Application Support (or reuses the copy there) and returns its path only when both
    /// its SHA-256 and the release signature over its bytes check out. The reason it was refused otherwise.
    static func fetch(_ b: Build) -> (path: String?, why: String?) {
        let dst = support.appendingPathComponent(b.name)
        if sha256(dst) != b.sha256 {
            guard let data = syncGet(b.url, timeout: 900) else { return (nil, "the test build did not download") }
            do {
                try FileManager.default.createDirectory(at: support, withIntermediateDirectories: true)
                try data.write(to: dst, options: .atomic)
            } catch { return (nil, error.localizedDescription) }
            guard sha256(dst) == b.sha256 else {
                try? FileManager.default.removeItem(at: dst); return (nil, "the test build does not match its SHA-256") }
        }
        guard let sig = syncGet(b.sig, timeout: 30), let text = String(data: sig, encoding: .utf8),
              ReleaseSignature.verify(zip: dst, signatureBase64: text) else {
            try? FileManager.default.removeItem(at: dst)
            return (nil, "the test build is not signed by NullMoth, so it was not used")
        }
        return (dst.path, nil)
    }

    /// Joins or leaves. Joining writes the login item that runs `1401 --tester-report` once per login; it is refused
    /// when 1401 sits where another user could replace it (the item would run that user's program in your login).
    static func set(on: Bool) -> String? {
        let fm = FileManager.default
        if !on {
            _ = sh("/bin/launchctl", ["bootout", "gui/\(getuid())", agentFile.path])
            try? fm.removeItem(at: agentFile)
            var s = state(); s["on"] = false; save(s)
            return nil
        }
        let exe = Bundle.main.executableURL!.resolvingSymlinksInPath()
        var dir = exe.deletingLastPathComponent()
        while dir.path != "/" {
            if let a = try? fm.attributesOfItem(atPath: dir.path), let p = a[.posixPermissions] as? Int, p & 0o002 != 0 {
                return "1401 is in a folder other users can change (\(dir.path)); move it into Applications first"
            }
            dir = dir.deletingLastPathComponent()
        }
        let plist: [String: Any] = ["Label": agentLabel, "ProgramArguments": [exe.path, "--tester-report"],
                                    "RunAtLoad": true, "ProcessType": "Background", "LowPriorityIO": true]
        do {
            try fm.createDirectory(at: agentFile.deletingLastPathComponent(), withIntermediateDirectories: true)
            let d = try PropertyListSerialization.data(fromPropertyList: plist, format: .xml, options: 0)
            try d.write(to: agentFile, options: .atomic)
        } catch { return "could not write the login item: \(error.localizedDescription)" }
        var s = state(); s["on"] = true; s["joined"] = ISO8601DateFormatter().string(from: Date()); save(s)
        return nil
    }

    /// One report per start: what the AMD/Intel driver did since the last report. Exits at once when not joined or
    /// when this start was already reported.
    static func report() -> Int32 {
        guard isOn else { return 0 }
        let boot = sh("/usr/sbin/sysctl", ["-n", "kern.bootsessionuuid"]).trimmingCharacters(in: .whitespacesAndNewlines)
        var s = state()
        if boot.isEmpty || s["lastBoot"] as? String == boot { return 0 }
        let fmt = DateFormatter(); fmt.dateFormat = "yyyy-MM-dd HH:mm:ss"; fmt.locale = Locale(identifier: "en_US_POSIX")
        // since the last report; a first report reaches back one day
        let since = (s["lastReport"] as? String).flatMap { ISO8601DateFormatter().date(from: $0) } ?? Date(timeIntervalSinceNow: -86400)
        var files: [(String, Data)] = []
        func add(_ name: String, _ text: String, cap: Int = 3 << 20) {
            let d = Data(text.utf8); files.append((name, d.count > cap ? d.suffix(cap) : d))
        }
        // the driver's kernel messages, previous start and this one (the boot guard parks a driver whose attach never
        // returned, so after a panic this start shows the park and the previous one shows how far it got)
        let pred = "process == \"kernel\" AND (sender BEGINSWITH \"NMX\" OR eventMessage CONTAINS \"NullMoth xkpi\" OR "
            + "eventMessage CONTAINS \"NullMoth GPU\" OR eventMessage CONTAINS[c] \"amdgpu\" OR eventMessage CONTAINS \"[drm]\" OR "
            + "eventMessage CONTAINS \"i915\" OR eventMessage CONTAINS \"xe \" OR eventMessage CONTAINS \"Boot args\")"
        add("tester-kernel-log.txt", sh("/usr/bin/log", ["show", "--style", "compact", "--start", fmt.string(from: since), "--predicate", pred]))
        // panics since the last report (kernel panics and WindowServer stops)
        let reports = URL(fileURLWithPath: "/Library/Logs/DiagnosticReports")
        for f in (try? FileManager.default.contentsOfDirectory(at: reports, includingPropertiesForKeys: [.contentModificationDateKey])) ?? [] {
            let n = f.lastPathComponent
            guard n.hasSuffix(".panic") || (n.hasPrefix("WindowServer") && n.hasSuffix(".ips")) else { continue }
            guard let m = try? f.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate, m > since,
                  let t = try? String(contentsOf: f, encoding: .utf8) else { continue }
            add("tester-" + n + ".txt", t)
        }
        // what was in play: macOS, every display-class PCI device, boot arguments, the AMD/Intel kexts and the guard
        var sum = "macOS \(sh("/usr/bin/sw_vers", ["-productVersion"]).trimmingCharacters(in: .whitespacesAndNewlines))"
            + " (\(sh("/usr/bin/sw_vers", ["-buildVersion"]).trimmingCharacters(in: .whitespacesAndNewlines)))\n"
        sum += "test build: \(s["build"] as? String ?? "?")\n"
        let args = sh("/usr/sbin/nvram", ["boot-args"]).trimmingCharacters(in: .whitespacesAndNewlines)
        sum += "boot-args: \(args)\n"
        // turning the test driver on removes -wegnoigpu; one added back by hand hides the Intel GPU from macOS again,
        // and the driver then never sees it
        let words = Set(args.split(whereSeparator: { $0 == " " || $0 == "\t" }).map(String.init))
        if words.contains("nmxintel=1") && words.contains("-wegnoigpu") {
            sum += "note: -wegnoigpu is set, so the Intel GPU is switched off and the test driver cannot see it\n"
        }
        sum += "guards: \(sh("/usr/sbin/nvram", ["-p"]).split(separator: "\n").filter { $0.contains("nullmoth") }.joined(separator: "; "))\n\n"
        sum += sh("/usr/sbin/ioreg", ["-r", "-c", "IOPCIDevice", "-l", "-w0"]).split(separator: "\n", omittingEmptySubsequences: false)
            .filter { $0.contains("+-o") || $0.contains("\"vendor-id\"") || $0.contains("\"device-id\"") || $0.contains("\"class-code\"")
                || $0.contains("nmxgpu") || $0.contains("nullmoth-gpu") }.joined(separator: "\n")
        sum += "\n\n" + sh("/usr/bin/kmutil", ["showloaded", "--list-only"]).split(separator: "\n").filter { $0.contains("com.nullmoth") }.joined(separator: "\n")
        add("tester-summary.txt", sum)
        let batch = newUploadBatch()
        var sent = 0
        for (name, raw) in files {
            var bytes = raw; bytes.removeAll { $0 == 0 }
            let body = Data(redact(String(decoding: bytes, as: UTF8.self)).utf8)
            let sha = SHA256.hash(data: body).map { String(format: "%02x", $0) }.joined()
            var req = URLRequest(url: URL(string: "https://nullmothsystems.com/api/upload")!, timeoutInterval: 60)
            req.httpMethod = "POST"; req.httpBody = body
            req.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
            req.setValue(name.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? "log.txt", forHTTPHeaderField: "X-File-Name")
            let notes = "1401 Mac \(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?") tester amd-intel \(s["build"] as? String ?? "?") (sent after a restart)"
            let meta = try! JSONSerialization.data(withJSONObject: ["consent": true, "notes": notes, "batch": batch])
            req.setValue(meta.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_")
                .replacingOccurrences(of: "=", with: ""), forHTTPHeaderField: "X-Meta")
            req.setValue(sha, forHTTPHeaderField: "X-Content-SHA256")
            let done = DispatchSemaphore(value: 0); let result = ReportUploadResult()
            let task = URLSession.shared.dataTask(with: req) { d, r, e in result.finish(data: d, response: r, error: e, sha256: sha); done.signal() }
            task.resume()
            let timedOut = done.wait(timeout: .now() + 90) == .timedOut
            if timedOut { task.cancel() }
            if result.take(timedOut: timedOut).0 != nil { sent += 1 }
        }
        // a start counts as reported only when something reached the site; otherwise the next login tries again
        if sent > 0 {
            s["lastBoot"] = boot; s["lastReport"] = ISO8601DateFormatter().string(from: Date()); s["lastBatch"] = batch; save(s)
        }
        print("tester report: \(sent) of \(files.count) sent")
        return sent > 0 ? 0 : 1
    }
}
