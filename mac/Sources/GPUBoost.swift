// 1401
// Copyright (c) 2026 NullMoth Systems. SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

import Foundation

/// GPU boost daemon facts, read without a password: the same files the package's boost_daemon.sh status looks at.
enum GPUBoost {
    static let plist = "/Library/LaunchDaemons/com.nullmoth.nvmtl-boost.plist"
    static let conf = "/Library/NullMoth/gpuboost"

    /// The program the job runs: the first ProgramArguments entry of its LaunchDaemon plist. Read from there so the status
    /// follows the package wherever it puts the binary (it is under a root-owned folder, not /usr/local, which users can write).
    static func program(plistData: Data) -> String? {
        guard let d = try? PropertyListSerialization.propertyList(from: plistData, options: [], format: nil) as? [String: Any],
              let args = d["ProgramArguments"] as? [String], let first = args.first, first.hasPrefix("/") else { return nil }
        return first
    }
    /// Every component of the path is a real directory (or the file itself), owned by root and not writable by group or others;
    /// boost_daemon.sh makes the same checks and says "installed, but its path is not trusted" when they fail.
    static func trusted(_ path: String, attributes: (String) -> (owner: Int, mode: Int, isLink: Bool)? = { p in
        guard let a = try? FileManager.default.attributesOfItem(atPath: p) else { return nil }
        return ((a[.ownerAccountID] as? NSNumber)?.intValue ?? -1, (a[.posixPermissions] as? NSNumber)?.intValue ?? 0777,
                (a[.type] as? FileAttributeType) == .typeSymbolicLink) }) -> Bool {
        guard path.hasPrefix("/") else { return false }
        var current = ""
        for part in path.split(separator: "/") {
            current += "/" + part
            guard let a = attributes(current), a.owner == 0, !a.isLink, a.mode & 0o022 == 0 else { return false }
        }
        return true
    }
    static func installed() -> Bool {
        guard let data = FileManager.default.contents(atPath: plist), let exe = program(plistData: data) else { return false }
        return FileManager.default.isExecutableFile(atPath: exe)
    }
    /// The program the job runs, when the job is installed.
    static func installedProgram() -> String? {
        guard let data = FileManager.default.contents(atPath: plist), let exe = program(plistData: data),
              FileManager.default.isExecutableFile(atPath: exe) else { return nil }
        return exe
    }
    static func setting() -> String? {
        (try? String(contentsOfFile: conf, encoding: .utf8))?.trimmingCharacters(in: .whitespacesAndNewlines)
    }
    /// The words the page shows. The daemon holds the boost only while the setting reads gpuboost=1.
    static func describe(installed: Bool, setting: String?, trusted: Bool = true) -> String {
        guard installed else { return "Not installed. Nothing is running." }
        guard trusted else { return "Installed, but its path is not trusted (a folder on the way is not root-owned, or others can write it), so it is not used. Remove the job and turn it on again." }
        switch setting {
        case "gpuboost=1": return "On: the daemon holds the GPU at its maximum boost."
        case "gpuboost=0": return "Installed, switched off."
        case .some(let s): return "Installed; the setting reads \"\(s.prefix(40))\", which the daemon does not accept, so it holds nothing."
        case .none: return "Installed, but there is no setting file; the daemon holds nothing."
        }
    }
}
