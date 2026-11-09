// 1401
// Copyright (c) 2026 NullMoth Systems. SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

import Foundation
import AppKit
import UniformTypeIdentifiers
import CryptoKit

// ARM apps (opt-in): translates apps built only for Apple silicon so they run on this Intel Mac. Turning it on
// downloads NullMoth's translator package (signed manifest -> SHA-256 -> release signature, the same chain as the test
// program in TesterLane.swift) and installs it under /Library/NullMoth/arm as root. Translation itself runs as the
// user, through the package's own nm-arm command, and writes a new copy into ~/Applications/NullMoth ARM; the original
// app is never changed. Turning it off runs the package's uninstaller, which removes the translator and this user's
// translated copies. The NVIDIA driver does not depend on any of it.
enum ArmApps {
    static let manifestURL = URL(string: "https://nullmothsystems.com/download/arm/manifest.json")!
    static let root = "/Library/NullMoth/arm"
    static let cli = root + "/bin/nm-arm"
    static let uninstaller = root + "/uninstall.sh"
    static let installedMarker = "NULLMOTH_ARM_INSTALLED"
    static let removedMarker = "NULLMOTH_ARM_REMOVED"
    static var outputDir: URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Applications/NullMoth ARM")
    }
    static var logDir: URL { logs.appendingPathComponent("arm") }

    struct Build { let version: String, name: String, url: URL, sha256: String, sig: URL }

    /// Present means on: the state lives in the installed package itself, so a removal by any route reads as off.
    static var isInstalled: Bool { FileManager.default.isExecutableFile(atPath: cli) }

    /// Only nullmoth-arm-<version>.tar.gz is accepted as a package name; it becomes a path in Application Support.
    static func validPackageName(_ n: String) -> Bool {
        n.range(of: #"^nullmoth-arm-[A-Za-z0-9._-]+\.tar\.gz$"#, options: .regularExpression) != nil && !n.contains("..")
    }

    /// A lowercase 64-digit hex SHA-256; it is pasted into a root shell line, so nothing else may pass.
    static func validSha(_ s: String) -> Bool { s.range(of: #"^[0-9a-f]{64}$"#, options: .regularExpression) != nil }

    static func latest() -> Build? {
        guard let d = syncGet(manifestURL, timeout: 30),
              let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
              let v = j["version"] as? String, let n = j["name"] as? String, let sha = (j["sha256"] as? String)?.lowercased(),
              let u = (j["url"] as? String).flatMap(URL.init(string:)), u.scheme == "https",
              let s = (j["sig"] as? String).flatMap(URL.init(string:)), s.scheme == "https",
              validSha(sha), validPackageName(n), manifestNamesMatch(version: v, name: n, url: u) else { return nil }
        return Build(version: v, name: n, url: u, sha256: sha, sig: s)
    }

    /// The package name is exactly nullmoth-arm-<the manifest's version>.tar.gz and the download link ends in that name,
    /// so a signed package of another NullMoth product, or another version, cannot stand in for this one.
    static func manifestNamesMatch(version: String, name: String, url: URL) -> Bool {
        version.range(of: #"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"#, options: .regularExpression) != nil
            && name == "nullmoth-arm-\(version).tar.gz" && url.lastPathComponent == name
    }

    /// Gets the package (the copy already in Application Support, or a fresh download) into memory ONCE, checks the
    /// SHA-256 and the release signature on that same buffer, and only then writes that buffer to disk. Hashing and
    /// verifying the file in two separate reads let another program running as this user swap it between the two.
    /// The returned digest is the one root re-checks on its private copy, so root installs only verified bytes.
    static func fetch(_ b: Build) -> (path: String?, sha256: String?, why: String?) {
        let dst = support.appendingPathComponent(b.name)
        let hex = { (d: Data) in SHA256.hash(data: d).map { String(format: "%02x", $0) }.joined() }
        var data = (try? Data(contentsOf: dst)) ?? Data()
        if data.isEmpty || hex(data) != b.sha256 {
            guard let d = syncGet(b.url, timeout: 1800) else { return (nil, nil, "the ARM translator package did not download") }
            data = d
        }
        let digest = hex(data)
        guard digest == b.sha256 else {
            try? FileManager.default.removeItem(at: dst); return (nil, nil, "the ARM translator package does not match its SHA-256") }
        guard let sig = syncGet(ReleaseSignature.boundURL(sig: b.sig), timeout: 30), let text = String(data: sig, encoding: .utf8),
              ReleaseSignature.verifyBound(data: data, product: "nullmoth-arm", version: b.version, signatureBase64: text) else {
            try? FileManager.default.removeItem(at: dst)
            return (nil, nil, "the ARM translator package is not signed by NullMoth, so it was not installed")
        }
        let installed = ((try? String(contentsOfFile: "/Library/NullMoth/arm/VERSION", encoding: .utf8)) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !ReleaseSignature.isDowngrade(b.version, installed: installed) else {
            return (nil, nil, "this ARM translator package is older than the installed one, so it was not installed")
        }
        do {
            try FileManager.default.createDirectory(at: support, withIntermediateDirectories: true)
            try data.write(to: dst, options: .atomic)
        } catch { return (nil, nil, error.localizedDescription) }
        return (dst.path, digest, nil)
    }

    /// The root shell line that installs a checked package. The download sits in a folder this user owns, so another
    /// program running as this user could swap it after the app checked it. Root therefore copies it into a fresh
    /// root-only folder first and checks the SHA-256 again on that copy; only that copy is unpacked and run.
    /// Privileged.run does not return the exit status, so success is the marker line and nothing else.
    static func installCommand(package: String, sha: String) -> String? {
        guard validSha(sha) else { return nil }
        let q = { (s: String) in "'" + s.replacingOccurrences(of: "'", with: "'\\''") + "'" }
        return "umask 077; d=$(/usr/bin/mktemp -d /private/var/root/nullmoth-arm.XXXXXXXX) || { echo 'STOP: no private folder'; exit 1; }; "
            + "trap '/bin/rm -rf \"$d\"' EXIT; /bin/chmod 700 \"$d\" || exit 1; "
            + "/bin/cp -X \(q(package)) \"$d/p.tar.gz\" || { echo 'STOP: could not copy the package'; exit 1; }; "
            + "h=$(/usr/bin/shasum -a 256 \"$d/p.tar.gz\" | /usr/bin/awk '{print $1}'); "
            + "[ \"$h\" = \(sha) ] || { echo 'STOP: the package changed after it was checked'; exit 1; }; "
            + "/bin/mkdir \"$d/x\" && /usr/bin/tar -xzf \"$d/p.tar.gz\" -C \"$d/x\" || { echo 'STOP: the package did not unpack'; exit 1; }; "
            + "[ -f \"$d/x/pkgroot/install.sh\" ] || { echo 'STOP: the package has no installer'; exit 1; }; "
            // the installer's exit codes: 3 checksum mismatch, 4 its compiler cannot run on this Mac, 5 copy failed.
            // umask 077 above is for the private copy only. The installer runs with the normal 022: under 077 it created
            // /Library/NullMoth readable by root alone on a Mac that had no driver yet, so nm-arm could not be reached by
            // the user (2.7; users were passing round `sudo chmod 711 /Library/NullMoth`). The chmod after it repairs a
            // folder an earlier install left that way, so pressing Turn on again fixes such a Mac.
            + "(umask 022; /bin/bash \"$d/x/pkgroot/install.sh\"); rc=$?; "
            + "[ $rc = 0 ] && /bin/chmod 755 /Library/NullMoth /Library/NullMoth/arm; "
            + "case $rc in 0) echo \(installedMarker);; 3) echo 'STOP: the package failed its own checksum';; "
            + "4) echo 'STOP: the translator cannot run on this Mac';; 5) echo 'STOP: the files could not be copied';; "
            + "*) echo \"STOP: the installer exited $rc\";; esac"
    }

    /// A short-name only (it is passed to the uninstaller as root and names whose translated copies are removed).
    static func validUser(_ u: String) -> Bool { u.range(of: #"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,254}$"#, options: .regularExpression) != nil }

    /// The root shell line that removes the package and this user's translated apps. The uninstaller runs only when root
    /// owns it and nobody else can write it: /Library/NullMoth is outside the app bundle, so it gets its own check.
    static func uninstallCommand(user: String) -> String? {
        guard validUser(user) else { return nil }
        return "u=\(uninstaller); if [ ! -e \"$u\" ]; then echo \(removedMarker); exit 0; fi; "
            + "o=$(/usr/bin/stat -f %u \"$u\") m=$(/usr/bin/stat -f %Lp \"$u\") || exit 1; "
            + "[ \"$o\" = 0 ] || { echo 'STOP: the uninstaller is not owned by root'; exit 1; }; "
            + "case \"$m\" in *[2367]?|*[2367]) echo 'STOP: the uninstaller can be changed by other users'; exit 1;; esac; "
            + "/bin/bash \"$u\" --user '\(user)' && echo \(removedMarker)"   // uninstall.sh takes --user NAME
    }

    /// Runs nm-arm as this user with a time limit and returns its JSON output (or why there is none).
    static func runCLI(_ args: [String], seconds: Double) -> (json: Any?, why: String?) {
        guard isInstalled else { return (nil, "the ARM translator is not installed") }
        let r = App.runBounded(URL(fileURLWithPath: cli), args, seconds: seconds)
        if r.timedOut { return (nil, "nm-arm \(args.first ?? "") did not answer within \(Int(seconds)) seconds") }
        guard let j = try? JSONSerialization.jsonObject(with: r.out, options: [.fragmentsAllowed]) else {
            let text = String(decoding: r.out.prefix(400), as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
            return (nil, "nm-arm \(args.first ?? "") exited \(r.status)" + (text.isEmpty ? "" : ": " + text))
        }
        return (j, r.status == 0 ? nil : "nm-arm \(args.first ?? "") exited \(r.status)")
    }

    static func check() -> [String: Any] {
        let r = runCLI(["check"], seconds: 60)
        guard var j = r.json as? [String: Any] else { return ["ok": false, "why": r.why ?? "nm-arm check returned nothing"] }
        if j["ok"] as? Bool != true, (j["why"] as? String ?? "").isEmpty { j["why"] = r.why ?? "this Mac did not pass the check" }
        return j
    }

    /// Translated apps, as {name, path}. Only paths inside ~/Applications/NullMoth ARM are kept, since the page may
    /// open them.
    static func list() -> (apps: [[String: String]], why: String?) {
        let r = runCLI(["list"], seconds: 30)
        guard let out = parseList(r.json) else { return ([], r.why ?? "nm-arm list did not return a list") }
        return (out, r.why)
    }

    /// nm-arm list prints {"apps": [...], "output_dir": ...}; each app has "path" (older builds: "output"). An entry
    /// whose path is outside ~/Applications/NullMoth ARM is dropped.
    static func parseList(_ json: Any?) -> [[String: String]]? {
        guard let arr = ((json as? [String: Any])?["apps"] as? [Any]) ?? (json as? [Any]) else { return nil }
        var out: [[String: String]] = []
        for e in arr {
            let o = e as? [String: Any]
            guard let name = (o?["name"] as? String) ?? (o?["app"] as? String) ?? (e as? String), validAppName(name) else { continue }
            let path = (o?["path"] as? String) ?? (o?["output"] as? String) ?? outputDir.appendingPathComponent(name + ".app").path
            guard inOutputDir(path) else { continue }
            out.append(["name": name, "path": path])
        }
        return out
    }

    /// An iPhone or iPad app (.ipa) turned into a Mac Catalyst app bundle in a fresh temporary folder, by the bundled
    /// nullmoth-ipa2mac.py (exit 0 done, 2 refused with a sentence on stderr). The sentence is shown to the user as is.
    static func wrapIpa(_ ipa: URL) -> (app: URL?, why: String?) {
        let script = Bundle.main.resourcePath.map { $0 + "/nullmoth-ipa2mac.py" } ?? ""
        guard FileManager.default.isExecutableFile(atPath: script) else { return (nil, "the converter is missing from the app") }
        let out = NSTemporaryDirectory() + "nullmoth-ipa-" + UUID().uuidString
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        p.arguments = ["-I", script, ipa.path, out]
        let o = Pipe(), e = Pipe()
        p.standardOutput = o; p.standardError = e
        do { try p.run() } catch { return (nil, "python3 could not start: \(error.localizedDescription)") }
        let text = String(data: o.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        let err = String(data: e.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        p.waitUntilExit()
        guard p.terminationStatus == 0, let line = text.split(separator: "\n").last else {
            let msg = err.trimmingCharacters(in: .whitespacesAndNewlines)
            return (nil, msg.isEmpty ? "the converter stopped (\(p.terminationStatus))" : redact(String(msg.suffix(400))))
        }
        return (URL(fileURLWithPath: String(line)), nil)
    }

    static func validAppName(_ n: String) -> Bool {
        !n.isEmpty && n.count < 256 && !n.contains("/") && n != "." && n != ".." && !n.hasPrefix("-")
    }

    static func inOutputDir(_ path: String) -> Bool {
        let base = outputDir.standardizedFileURL.resolvingSymlinksInPath().path + "/"
        let p = URL(fileURLWithPath: path).standardizedFileURL.resolvingSymlinksInPath().path
        return p.hasPrefix(base) && p.hasSuffix(".app")
    }

    static func remove(_ name: String) -> String? {
        guard validAppName(name) else { return "that is not a translated app's name" }
        let r = App.runBounded(URL(fileURLWithPath: cli), ["remove", name], seconds: 120)
        if r.timedOut { return "nm-arm remove did not finish within 2 minutes" }
        // stdout is one line: {"ok":true,"removed":[...]} or {"ok":false,"why":"..."}
        let j = (try? JSONSerialization.jsonObject(with: r.out)) as? [String: Any]
        if r.status != 0 || j?["ok"] as? Bool == false {
            if let why = j?["why"] as? String, !why.isEmpty { return "could not remove \(name): \(why)" }
            let text = String(decoding: r.out.prefix(400), as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
            return "could not remove \(name) (nm-arm exited \(r.status))" + (text.isEmpty ? "" : ": " + text)
        }
        return nil
    }

    // Homebrew on this Intel Mac (nm-arm brew in the translator package): the ARM Homebrew in /opt/homebrew runs
    // Homebrew's Apple-silicon bottles translated, the Intel one in /usr/local runs natively, side by side as on a Mac
    // with Apple silicon. The only step that needs root is creating the two prefixes' folders for this user, the same
    // folders Homebrew's own installer creates with sudo; everything else (download, Ruby, translation) runs as the user,
    // because Homebrew refuses to run as root.
    static let brewDirsMarker = "NULLMOTH_BREW_DIRS_READY"
    /// Kept equal to PREFIX_DIRS in the package's nm_arm_brew.py (Homebrew's install.sh "directories").
    static let brewPrefixDirs = ["bin", "etc", "include", "lib", "sbin", "share", "opt", "var", "Frameworks",
        "etc/bash_completion.d", "lib/pkgconfig", "share/aclocal", "share/doc", "share/info", "share/locale", "share/man",
        "share/man/man1", "share/man/man2", "share/man/man3", "share/man/man4", "share/man/man5", "share/man/man6",
        "share/man/man7", "share/man/man8", "share/zsh", "share/zsh/site-functions", "share/fish",
        "share/fish/vendor_completions.d", "var/homebrew", "var/homebrew/linked", "Cellar", "Caskroom"]

    static func validBrewChoice(pick: String, primary: String) -> Bool {
        ["both", "arm", "intel"].contains(pick) && ["arm", "intel"].contains(primary)
    }

    /// The root shell line that creates the Homebrew folders and gives them to `user` (group admin when the user is in
    /// it). Never recursive; /usr/local itself stays root's; a symlinked prefix, or an /opt/homebrew that belongs to
    /// another account, stops it. Success is the marker line and nothing else.
    /// Safe against the user's own processes racing it (the same script as nm-arm's root_script): root creates and
    /// chowns a folder only while its parent is still root-owned, so nothing in it can be swapped for a link; it hands
    /// ownership over deepest first with chown -h, the prefix last; folders under a parent the user already owns are
    /// made AS the user. The old line chowned the prefix first, then raced a link swap on every folder below it.
    static func brewRootCommand(user: String, arm: Bool, intel: Bool) -> String? {
        guard validUser(user), arm || intel else { return nil }
        var c = "set -eu; u='\(user)'; g=admin; /usr/bin/id -Gn \"$u\" | /usr/bin/grep -qw admin || g=$(/usr/bin/id -gn \"$u\"); "
            + "rootdir() { [ -d \"$1\" ] && [ ! -L \"$1\" ] && [ \"$(/usr/bin/stat -f %Su \"$1\")\" = root ]; }; "
            // every folder on the path, not only the parent: chown -h protects the last component only
            + "rootchain() { p=$1; while [ \"$p\" != / ] && [ \"$p\" != . ]; do rootdir \"$p\" || return 1; p=$(/usr/bin/dirname \"$p\"); done; }; "
        for (on, prefix) in [(arm, "/opt/homebrew"), (intel, "/usr/local")] where on {
            var dirs = brewPrefixDirs.map { prefix + "/" + $0 }
            if prefix == "/usr/local" { dirs.append("/usr/local/Homebrew") }
            // parents before children (a stable sort on depth)
            dirs = dirs.enumerated().sorted { a, b in
                let da = a.element.filter { $0 == "/" }.count, db = b.element.filter { $0 == "/" }.count
                return da != db ? da < db : a.offset < b.offset
            }.map { $0.element }
            let top = (prefix as NSString).deletingLastPathComponent
            c += "[ -L \(prefix) ] && { echo 'STOP: \(prefix) is a symbolic link'; exit 1; }; "
                + "[ -d \(top) ] || /bin/mkdir \(top); "
                + "rootdir \(top) || { echo 'STOP: \(top) does not belong to root'; exit 1; }; "
                + "[ -e \(prefix) ] || /bin/mkdir \(prefix); "
                + "[ -d \(prefix) ] && [ ! -L \(prefix) ] || { echo 'STOP: \(prefix) is not a folder'; exit 1; }; "
            if prefix == "/opt/homebrew" {
                c += "o=$(/usr/bin/stat -f %Su /opt/homebrew); [ \"$o\" = root ] || [ \"$o\" = \"$u\" ] || "
                    + "{ echo \"STOP: /opt/homebrew belongs to $o\"; exit 1; }; "
            }
            c += "todo=''; for d in " + dirs.joined(separator: " ") + "; do "
                + "rootchain \"$(/usr/bin/dirname \"$d\")\" || continue; "
                + "if [ -L \"$d\" ]; then echo \"STOP: $d is a symbolic link\"; exit 1; fi; "
                + "if [ -e \"$d\" ] && [ ! -d \"$d\" ]; then echo \"STOP: $d is not a folder\"; exit 1; fi; "
                + "[ -d \"$d\" ] || /bin/mkdir \"$d\"; "
                + "if rootdir \"$d\"; then todo=\"$d $todo\"; fi; done; "
                + "for d in $todo; do rootchain \"$(/usr/bin/dirname \"$d\")\" || { echo \"STOP: a folder above $d changed\"; exit 1; }; "
                + "/bin/chmod -h ug=rwx \"$d\"; /usr/sbin/chown -h \"$u:$g\" \"$d\"; done; "
            if prefix == "/opt/homebrew" {
                c += "if rootdir /opt/homebrew; then /bin/chmod -h 755 /opt/homebrew; /usr/sbin/chown -h \"$u:$g\" /opt/homebrew; fi; "
            }
            c += "/usr/bin/sudo -u \"$u\" /bin/mkdir -p " + dirs.joined(separator: " ") + "; "
        }
        return c + "echo \(brewDirsMarker)"
    }

    /// nm-arm brew setup, as the user, after the folders exist (--no-sudo: it stops with exit 6 rather than prompt).
    static func brewSetupArguments(pick: String, primary: String) -> [String]? {
        guard validBrewChoice(pick: pick, primary: primary) else { return nil }
        return ["brew", "setup"] + (pick == "intel" ? [] : ["--arm"]) + (pick == "arm" ? [] : ["--intel"])
            + ["--primary", primary, "--no-sudo"]
    }

    /// {"arm": {"installed", ...}, "intel": {"installed", ...}} from nm-arm brew status, or why there is none.
    static func brewStatus() -> [String: Any] {
        let r = runCLI(["brew", "status"], seconds: 30)
        return brewStatusResult(json: r.json, why: r.why)
    }

    static func brewStatusResult(json: Any?, why: String?) -> [String: Any] {
        let r = (json: json, why: why)
        if let j = r.json as? [String: Any] { return j }
        // An engine from before Homebrew support answers the unknown command with a usage error (exit 2) and no JSON.
        // The app and the translator update separately (app 2.7.2 beside engine 2.7.0), so say that instead of the code.
        if let why = r.why, why.hasSuffix("brew exited 2") || why.contains("brew exited 2:") {
            return ["why": "The installed ARM translator is older than this app and has no Homebrew setup. Turn ARM apps off and on again to install the matching translator.",
                    "outdated": true]
        }
        return ["why": r.why ?? "nm-arm brew status returned nothing"]
    }

    /// One progress line from nm-arm translate: {"stage","pct","msg"}. Anything else is passed on as a message, so
    /// nothing the translator prints is lost.
    static func parseProgress(_ line: String) -> [String: Any]? {
        let t = line.trimmingCharacters(in: .whitespacesAndNewlines)
        if t.isEmpty { return nil }
        guard let j = try? JSONSerialization.jsonObject(with: Data(t.utf8)) as? [String: Any] else { return ["stage": "", "msg": t] }
        var out: [String: Any] = ["stage": j["stage"] as? String ?? "", "msg": j["msg"] as? String ?? ""]
        if let p = j["pct"] as? Double { out["pct"] = max(0, min(100, p)) }
        return out
    }

    /// Everything a pipe holds right now: reads without blocking until it is empty (EAGAIN) or closed (EOF).
    static func drainNonBlocking(_ fd: Int32) -> (data: Data, eof: Bool) {
        let flags = fcntl(fd, F_GETFL)
        if flags >= 0 && flags & O_NONBLOCK == 0 { _ = fcntl(fd, F_SETFL, flags | O_NONBLOCK) }
        var out = Data()
        var buf = [UInt8](repeating: 0, count: 1 << 16)
        while true {
            let n = buf.withUnsafeMutableBytes { read(fd, $0.baseAddress, $0.count) }
            if n > 0 { out.append(contentsOf: buf[0..<n]); continue }
            if n < 0 && errno == EINTR { continue }
            // 0: closed; -1 EAGAIN: empty while an orphan holds it open; any other error: nothing more to read
            return (out, n == 0 || (n < 0 && errno != EAGAIN))
        }
    }

    /// Every descendant of `pid`, deepest last; read before any of them is signalled so an orphaned child is not missed.
    static func descendants(of pid: Int32) -> [Int32] {
        var out: [Int32] = [], queue = [pid]
        while let p = queue.popLast(), out.count < 512 {
            let kids = sh("/usr/bin/pgrep", ["-P", String(p)]).split(whereSeparator: \.isNewline).compactMap { Int32($0) }
            out += kids; queue += kids
        }
        return out
    }

    /// One translation at a time, as this user. Stop() ends the whole process tree (the translator starts compilers).
    final class Job {
        let process = Process()
        private(set) var cancelled = false
        private let lock = NSLock()
        private var pending = Data()
        private var outSource: DispatchSourceRead?

        init(arguments: [String], executable: String = ArmApps.cli) {
            process.executableURL = URL(fileURLWithPath: executable)
            process.arguments = arguments
            process.standardInput = FileHandle.nullDevice
        }

        convenience init(app: URL, executable: String = ArmApps.cli) {
            self.init(arguments: ["translate", app.path], executable: executable)
        }

        /// Starts the translator; `line` gets each parsed progress line, `done` gets the exit status once.
        func start(line: @escaping ([String: Any]) -> Void, done: @escaping (Int32, Bool, String) -> Void) -> String? {
            let out = Pipe(), err = Pipe()
            process.standardOutput = out; process.standardError = err
            var errTail = Data()
            let errLock = NSLock()
            err.fileHandleForReading.readabilityHandler = { h in
                let d = h.availableData
                errLock.lock(); errTail.append(d); if errTail.count > 4096 { errTail = errTail.suffix(4096) }; errLock.unlock()
            }
            // stdout is read by a dispatch source on one serial queue, and the exit's final read runs on that same
            // queue, so no chunk can arrive after the end has been reported and lines stay in order. The final read
            // does not wait for end-of-file: a child the translator left behind can hold the pipe open, so it takes
            // what the pipe holds (non-blocking, until EAGAIN or EOF). WAS: a readabilityHandler cleared at exit while
            // its last call could still be running, then a blocking readDataToEndOfFile bounded by a 3 s wait whose
            // result was thrown away on timeout - with the last progress lines in it (test_arm_apps "jobmany").
            let q = DispatchQueue(label: "nullmoth.arm.job.stdout")
            let fd = out.fileHandleForReading.fileDescriptor
            let consume: (Data) -> Void = { [weak self] d in
                guard let self, !d.isEmpty else { return }
                self.lock.lock(); self.pending.append(d)
                var lines: [String] = []
                while let nl = self.pending.firstIndex(of: 0x0A) {
                    lines.append(String(decoding: self.pending[self.pending.startIndex..<nl], as: UTF8.self))
                    self.pending.removeSubrange(self.pending.startIndex...nl)
                }
                self.lock.unlock()
                for l in lines { if let p = ArmApps.parseProgress(l) { line(p) } }
            }
            let src = DispatchSource.makeReadSource(fileDescriptor: fd, queue: q)
            src.setEventHandler {
                let r = ArmApps.drainNonBlocking(fd)
                consume(r.data)
                if r.eof { src.cancel() }
            }
            src.resume()
            outSource = src
            process.terminationHandler = { [weak self] p in
                q.async {
                    consume(ArmApps.drainNonBlocking(fd).data)
                    src.cancel()
                    _ = out   // the pipe lives until its last read
                    if let self {
                        self.lock.lock(); let tail = String(decoding: self.pending, as: UTF8.self); self.pending.removeAll(); self.lock.unlock()
                        for l in tail.split(whereSeparator: \.isNewline) { if let pr = ArmApps.parseProgress(String(l)) { line(pr) } }
                    }
                    err.fileHandleForReading.readabilityHandler = nil
                    errLock.lock(); let e = String(decoding: errTail, as: UTF8.self); errLock.unlock()
                    done(p.terminationStatus, self?.cancelled ?? false, e.trimmingCharacters(in: .whitespacesAndNewlines))
                }
            }
            do { try process.run() } catch { return "could not start the translator: \(error.localizedDescription)" }
            return nil
        }

        func stop() {
            cancelled = true
            guard process.isRunning else { return }
            let pid = process.processIdentifier
            let tree = ArmApps.descendants(of: pid)
            kill(pid, SIGTERM); for c in tree { kill(c, SIGTERM) }
            // whatever ignored SIGTERM gets SIGKILL, read again from the live tree so a reused pid is never hit
            DispatchQueue.global().asyncAfter(deadline: .now() + 5) { [process] in
                guard process.isRunning else { return }
                for c in ArmApps.descendants(of: pid) { kill(c, SIGKILL) }
                kill(pid, SIGKILL)
            }
        }
    }
}

// The page's "ARM apps (opt-in)" card. Everything slow runs off the main thread; every outcome reaches the page as an
// "arm" event, so nothing fails silently. ArmApps.job is only touched on the main thread.
extension ArmApps {
    static var job: Job?
    static var autoChecked = false   // the Windows request is looked at once per app launch (main thread)
}

// The decision record: who last turned ARM apps on or off, or why a request from 1401 for Windows was skipped. Having
// one is what makes that request fire only once, and it is how a user who turned ARM apps off stays off.
extension ArmApps {
    static let decisionFile = support.appendingPathComponent("arm.json")
    static let windowsSource = "1401-windows"
    static let installedProfile = "/Library/NullMoth/system-profile.json"

    static func decision() -> [String: Any]? {
        guard let d = try? Data(contentsOf: decisionFile),
              let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any], j["on"] is Bool else { return nil }
        return j
    }

    static func saveDecision(on: Bool, source: String, skipped: String? = nil) {
        var j: [String: Any] = ["on": on, "source": source, "time": ISO8601DateFormatter().string(from: Date())]
        if let skipped { j["skipped"] = skipped }
        try? FileManager.default.createDirectory(at: support, withIntermediateDirectories: true)
        if let d = try? JSONSerialization.data(withJSONObject: j, options: [.prettyPrinted, .sortedKeys]) {
            try? d.write(to: decisionFile, options: .atomic)
        }
    }

    /// True only for opt_in.arm_apps that is the JSON literal true in one of the Windows profiles (a record's
    /// windows_candidates, or a stick's profile itself). 1, "true" or a missing key are not a request.
    static func windowsRequest(_ records: [[String: Any]]) -> Bool {
        let isTrue = { (v: Any?) -> Bool in
            guard let n = v as? NSNumber else { return false }
            return CFGetTypeID(n) == CFBooleanGetTypeID() && n.boolValue
        }
        for r in records {
            for c in [r] + ((r["windows_candidates"] as? [[String: Any]]) ?? []) {
                if isTrue((c["opt_in"] as? [String: Any])?["arm_apps"]) { return true }
            }
        }
        return false
    }

    /// The banner event for the page, or nil when there is nothing to show.
    static func banner(request: Bool, decision: [String: Any]?, driverInstalled: Bool, cpuFeatures: String) -> [String: Any]? {
        guard shouldHonourRequest(request: request, decision: decision, driverInstalled: driverInstalled) else { return nil }
        if let why = cpuGate(features: cpuFeatures) {
            return ["kind": "request", "canRun": false, "text": "1401 for Windows set up ARM apps for this Mac, but \(why)."]
        }
        return ["kind": "request", "canRun": true,
                "text": "1401 for Windows set up ARM apps for this Mac. Press Turn on to finish (your password is needed once)."]
    }

    /// Whether to act on the request: there is one, the NVIDIA driver was installed (the request only rides a driver
    /// install), and nobody has decided yet. A recorded decision, on or off, from the user or an earlier request, wins.
    static func shouldHonourRequest(request: Bool, decision: [String: Any]?, driverInstalled: Bool) -> Bool {
        request && driverInstalled && decision == nil
    }

    /// The CPU floor the translator needs: AES, PCLMULQDQ, SSE4.2 and POPCNT, the same minimum the package's own check
    /// uses. nm-arm check ships inside the package, so this runs before anything is offered. Features only, never the
    /// vendor: an AMD processor with these flags passes exactly as an Intel one does.
    /// Some AMD systems leave these sysctl keys empty; the package then reads CPUID itself, so an empty answer is not a
    /// refusal here, and nm-arm check decides after the install. PCLMUL is spelled PCLMULQDQ by macOS; both count.
    static func cpuGate(features: String) -> String? {
        var have = Set(features.uppercased().split(whereSeparator: { $0 == " " || $0 == "\t" || $0 == "\n" }).map(String.init))
        if have.isEmpty { return nil }
        if have.contains("PCLMUL") { have.insert("PCLMULQDQ") }
        let missing = ["AES", "PCLMULQDQ", "SSE4.2", "POPCNT"].filter { !have.contains($0) }
        return missing.isEmpty ? nil : "this processor lacks \(missing.joined(separator: ", ")), which translated apps need"
    }

    /// The three feature lists, or "" when any of them is blank: the package then reads CPUID itself, and so this
    /// pre-check steps aside rather than refuse on a partial answer.
    static func cpuFeatures() -> String {
        let parts = ["machdep.cpu.features", "machdep.cpu.leaf7_features", "machdep.cpu.extfeatures"].map { sysctl($0) }
        return parts.contains { $0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty } ? "" : parts.joined(separator: " ")
    }
}

extension App {
    func armStatus(_ extra: [String: Any] = [:]) {
        DispatchQueue.global(qos: .userInitiated).async {
            var s: [String: Any] = ["kind": "status", "installed": ArmApps.isInstalled]
            if ArmApps.isInstalled {
                s["check"] = ArmApps.check()
                let l = ArmApps.list(); s["apps"] = l.apps
                if let why = l.why { s["listWhy"] = why }
                s["brew"] = ArmApps.brewStatus()
            }
            for (k, v) in extra { s[k] = v }
            DispatchQueue.main.async { s["translating"] = ArmApps.job != nil; self.send("arm", s) }
        }
    }

    func armFail(_ why: String) { DispatchQueue.main.async { self.send("arm", ["kind": "error", "why": why]) } }
    func armBusy(_ text: String) { DispatchQueue.main.async { self.send("arm", ["kind": "busy", "text": text]) } }

    func armAction(_ b: [String: Any]) {
        switch b["op"] as? String ?? "" {
        case "status": armStatus(); armWindowsRequest()
        case "check": armBusy("Checking this Mac..."); armStatus()
        case "on": armTurnOn(source: b["from"] as? String == "windows" ? ArmApps.windowsSource : "user")
        case "notNow":
            // the banner's "Not now": a decision, so it does not come back; the card's own Turn on still works
            if ArmApps.decision() == nil { ArmApps.saveDecision(on: false, source: ArmApps.windowsSource, skipped: "not now") }
            armStatus()
        case "off": armTurnOff()
        case "clt":
            // Apple's own installer window; no password is needed to ask for it
            let p = Process(); p.executableURL = URL(fileURLWithPath: "/usr/bin/xcode-select"); p.arguments = ["--install"]
            p.standardOutput = FileHandle.nullDevice; p.standardError = FileHandle.nullDevice
            do { try p.run(); armBusy("macOS is asking to install the Command Line Tools. When that finishes, press Check this Mac.") }
            catch { armFail("Could not ask macOS for the Command Line Tools: \(error.localizedDescription)") }
        case "translate": armTranslate()
        case "brew": armBrew(pick: b["pick"] as? String ?? "", primary: b["primary"] as? String ?? "")
        case "cancel": ArmApps.job?.stop()
        case "open":
            guard let path = b["path"] as? String, ArmApps.inOutputDir(path) else { return armFail("That app is not in the NullMoth ARM folder.") }
            if !NSWorkspace.shared.open(URL(fileURLWithPath: path)) { armFail("macOS could not open \(URL(fileURLWithPath: path).lastPathComponent).") }
        case "remove":
            guard let name = b["name"] as? String, ArmApps.validAppName(name) else { return armFail("That is not a translated app.") }
            guard ArmApps.job == nil else { return armFail("Wait for the translation to finish, or cancel it, first.") }
            armBusy("Removing \(name)...")
            DispatchQueue.global(qos: .userInitiated).async {
                if let why = ArmApps.remove(name) { self.armFail(why) }
                self.armStatus()
            }
        default: break
        }
    }

    /// Turn on, from the card's button (source "user") or from the 1401 for Windows banner's button: the same verified
    /// path either way, and only ever after the user pressed it. From the banner, a failure installs nothing and is
    /// recorded as off with its reason, so the banner does not come back; a failed press of the card's own button records
    /// nothing, so the user can simply try again.
    func armTurnOn(source: String = "user") {
        let auto = source != "user"
        let lead = auto ? "1401 for Windows asked for ARM apps. " : ""
        armBusy(lead + "Reading the ARM translator package list...")
        DispatchQueue.global(qos: .userInitiated).async {
            let fail = { (why: String) in
                if auto { ArmApps.saveDecision(on: false, source: source, skipped: why) }
                self.armFail((auto ? "ARM apps (asked for in 1401 for Windows): not set up - " : "") + why)
            }
            if auto, let why = ArmApps.cpuGate(features: ArmApps.cpuFeatures()) { return fail("Not installed: \(why).") }
            guard let b = ArmApps.latest() else { return fail("Could not read the ARM translator package list from nullmothsystems.com.") }
            self.armBusy(lead + "Downloading the ARM translator \(b.version) and checking its signature...")
            let got = ArmApps.fetch(b)
            guard let path = got.path, let digest = got.sha256 else { return fail("Not installed: \(got.why ?? "the package could not be checked").") }
            guard let cmd = ArmApps.installCommand(package: path, sha: digest) else { return fail("Not installed: the package list is malformed.") }
            self.armBusy(lead + "Waiting for your Mac password (a macOS window asks for it) to install the ARM translator...")
            DispatchQueue.main.async { NSApp.activate(ignoringOtherApps: true) }
            let r = Privileged.run(cmd, timeout: 20 * 60)
            if r.cancelled { return fail("Not installed: the password prompt was cancelled.") }
            guard r.output.contains(ArmApps.installedMarker), ArmApps.isInstalled else {
                let tail = r.output.split(whereSeparator: \.isNewline).suffix(6).joined(separator: "\n")
                return fail("The ARM translator did not install. " + redact(r.error ?? "") + (tail.isEmpty ? "" : "\n" + redact(tail)))
            }
            ArmApps.saveDecision(on: true, source: source)
            self.armStatus(["note": lead + "On: the ARM translator \(b.version) is installed."])
        }
    }

    /// A 1401 for Windows request, shown once: at the first app launch after a driver install, when the profile setup
    /// saved under /Library/NullMoth asks for ARM apps and nothing is decided yet, the page opens the ARM card with a
    /// banner. Nothing is installed until the user presses Turn on there; Turn on, Turn off and "Not now" all record a
    /// decision, which hides the banner for good. A CPU that cannot run translated apps gets the reason, not the button.
    func armWindowsRequest() {
        guard !ArmApps.autoChecked else { return }
        ArmApps.autoChecked = true
        DispatchQueue.global(qos: .userInitiated).async {
            var records: [[String: Any]] = []
            if let d = try? Data(contentsOf: URL(fileURLWithPath: ArmApps.installedProfile)),
               let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] { records.append(j) }
            guard let banner = ArmApps.banner(request: ArmApps.windowsRequest(records), decision: ArmApps.decision(),
                                              driverInstalled: !App.recordedDriverVersion().isEmpty,
                                              cpuFeatures: ArmApps.cpuFeatures()) else { return }
            DispatchQueue.main.async { self.send("arm", banner) }
        }
    }

    func armTurnOff() {
        let a = NSAlert()
        a.messageText = "Turn off ARM apps?"
        a.informativeText = "This removes the ARM translator and every app it translated for you (the copies in Applications > NullMoth ARM). Your original apps and the NullMoth driver are not touched. An ARM Homebrew in /opt/homebrew stops working until ARM apps is turned on again; an Intel Homebrew in /usr/local is not affected. macOS asks for your password."
        a.addButton(withTitle: "Turn off"); a.addButton(withTitle: "Cancel")
        guard a.runModal() == .alertFirstButtonReturn else { return armStatus() }
        ArmApps.job?.stop()
        guard let cmd = ArmApps.uninstallCommand(user: NSUserName()) else { return armFail("Your account name cannot be passed to the uninstaller.") }
        armBusy("Waiting for your Mac password (a macOS window asks for it) to remove the ARM translator...")
        DispatchQueue.global(qos: .userInitiated).async {
            let r = Privileged.run(cmd, timeout: 10 * 60)
            if r.cancelled { return self.armFail("Still on: the password prompt was cancelled.") }
            guard r.output.contains(ArmApps.removedMarker), !ArmApps.isInstalled else {
                let tail = r.output.split(whereSeparator: \.isNewline).suffix(6).joined(separator: "\n")
                return self.armFail("The ARM translator was not fully removed. " + redact(r.error ?? "") + (tail.isEmpty ? "" : "\n" + redact(tail)))
            }
            // the downloaded package is no longer needed either
            let fm = FileManager.default
            for f in (try? fm.contentsOfDirectory(atPath: support.path)) ?? [] where ArmApps.validPackageName(f) {
                try? fm.removeItem(at: support.appendingPathComponent(f))
            }
            ArmApps.saveDecision(on: false, source: "user")
            self.armStatus(["note": "Off: the ARM translator and its translated apps are removed."])
        }
    }

    func armTranslate() {
        guard ArmApps.job == nil else { return armFail("A translation is already running.") }
        guard ArmApps.isInstalled else { return armFail("Turn ARM apps on first.") }
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.applicationBundle] + (UTType("com.apple.itunes.ipa").map { [$0] } ?? [])
        panel.directoryURL = URL(fileURLWithPath: "/Applications")
        panel.prompt = "Translate"
        panel.message = "Pick an app built for Apple silicon, or an iPhone or iPad app (.ipa) you built yourself. Your original stays as it is; the copy goes to Applications > NullMoth ARM."
        guard panel.runModal() == .OK, let picked = panel.url else { return armStatus() }
        let name = picked.deletingPathExtension().lastPathComponent
        armBusy("Checking this Mac before translating \(name)...")
        DispatchQueue.global(qos: .userInitiated).async {
            let c = ArmApps.check()
            guard c["ok"] as? Bool == true else {
                return self.armFail("Not translated: \(c["why"] as? String ?? "this Mac did not pass the check").")
            }
            var app = picked
            if picked.pathExtension.lowercased() == "ipa" {
                self.armBusy("Preparing \(name) as a Mac app...")
                let made = ArmApps.wrapIpa(picked)
                guard let wrapped = made.app else { return self.armFail("Not translated: \(made.why ?? "the iPhone app could not be prepared").") }
                app = wrapped
            }
            DispatchQueue.main.async {
                guard ArmApps.job == nil else { return self.armFail("A translation is already running.") }
                self.armRunJob(ArmApps.Job(app: app), name: name, what: "app")
            }
        }
    }

    /// Runs one nm-arm job as this user (main thread): progress lines reach the page, then one "done" event. `what`
    /// tells the page which success sentence to show ("app": a translated app, "brew": Homebrew).
    func armRunJob(_ job: ArmApps.Job, name: String, what: String) {
        ArmApps.job = job
        var last: [String: Any] = [:]
        let why = job.start(line: { p in
            DispatchQueue.main.async { last = p; var e = p; e["kind"] = "progress"; e["app"] = name; self.send("arm", e) }
        }, done: { status, cancelled, stderr in
            DispatchQueue.main.async {
                if ArmApps.job === job { ArmApps.job = nil }
                if cancelled {
                    let why = what == "brew" ? "Cancelled. What was already set up stays; Set up Homebrew again continues from there."
                                             : "Cancelled. Nothing was added."
                    self.send("arm", ["kind": "done", "ok": false, "app": name, "what": what, "why": why])
                } else if status == 0 && (last["stage"] as? String ?? "") != "error" {
                    self.send("arm", ["kind": "done", "ok": true, "app": name, "what": what, "msg": last["msg"] as? String ?? ""])
                } else {
                    let msg = (last["stage"] as? String) == "error" ? (last["msg"] as? String ?? "") : ""
                    let detail = !msg.isEmpty ? msg : (stderr.isEmpty ? "nm-arm exited \(status)" : String(stderr.suffix(600)))
                    self.send("arm", ["kind": "done", "ok": false, "app": name, "what": what, "why": redact(detail)])
                }
                self.armStatus()
            }
        })
        if let why { ArmApps.job = nil; self.armFail(why) }
        else { self.send("arm", ["kind": "progress", "app": name, "stage": "start", "pct": 0, "msg": "Starting..."]) }
    }

    /// Set up Homebrew: the ARM one (/opt/homebrew, translated), the Intel one (/usr/local, native), or both. One
    /// password prompt creates the folders; the rest runs as the user with progress in the card.
    func armBrew(pick: String, primary: String) {
        guard ArmApps.job == nil else { return armFail("Wait for the translation to finish, or cancel it, first.") }
        guard ArmApps.isInstalled else { return armFail("Turn ARM apps on first: Homebrew is set up by the ARM translator.") }
        guard let args = ArmApps.brewSetupArguments(pick: pick, primary: primary) else { return armFail("That is not a Homebrew choice.") }
        let wantArm = pick != "intel", wantIntel = pick != "arm"
        let a = NSAlert()
        a.messageText = "Set up Homebrew?"
        a.informativeText = (wantArm ? "ARM Homebrew goes in /opt/homebrew and installs Homebrew's Apple-silicon packages, translated for this Mac (the first install of a big package can take a while). " : "")
            + (wantIntel ? "Intel Homebrew goes in /usr/local and runs natively; Homebrew no longer publishes Intel packages for most formulae, so it usually builds them from source. " : "")
            + "In Terminal, brew is the \(primary == "arm" ? "ARM" : "Intel") one; abrew is always ARM and ibrew always Intel. macOS asks for your password once, to create the folders."
        a.addButton(withTitle: "Set up"); a.addButton(withTitle: "Cancel")
        guard a.runModal() == .alertFirstButtonReturn else { return armStatus() }
        armBusy("Checking this Mac before setting up Homebrew...")
        DispatchQueue.global(qos: .userInitiated).async {
            if wantArm {
                let c = ArmApps.check()
                guard c["ok"] as? Bool == true else {
                    return self.armFail("ARM Homebrew needs a Mac that passes the check: \(c["why"] as? String ?? "this Mac did not pass").")
                }
            }
            guard let cmd = ArmApps.brewRootCommand(user: NSUserName(), arm: wantArm, intel: wantIntel) else {
                return self.armFail("Your account name cannot be passed to the folder step.")
            }
            self.armBusy("Waiting for your Mac password (a macOS window asks for it) to create the Homebrew folders...")
            DispatchQueue.main.async { NSApp.activate(ignoringOtherApps: true) }
            let r = Privileged.run(cmd, timeout: 5 * 60)
            if r.cancelled { return self.armFail("Homebrew was not set up: the password prompt was cancelled.") }
            guard r.output.contains(ArmApps.brewDirsMarker) else {
                let tail = r.output.split(whereSeparator: \.isNewline).suffix(6).joined(separator: "\n")
                return self.armFail("The Homebrew folders could not be created. " + redact(r.error ?? "") + (tail.isEmpty ? "" : "\n" + redact(tail)))
            }
            DispatchQueue.main.async {
                guard ArmApps.job == nil else { return self.armFail("A translation is already running.") }
                self.armRunJob(ArmApps.Job(arguments: args), name: "Homebrew", what: "brew")
            }
        }
    }
}
