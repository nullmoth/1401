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
    static func installed() -> Bool {
        guard let data = FileManager.default.contents(atPath: plist), let exe = program(plistData: data) else { return false }
        return FileManager.default.isExecutableFile(atPath: exe)
    }
    static func setting() -> String? {
        (try? String(contentsOfFile: conf, encoding: .utf8))?.trimmingCharacters(in: .whitespacesAndNewlines)
    }
    /// The words the page shows. The daemon holds the boost only while the setting reads gpuboost=1.
    static func describe(installed: Bool, setting: String?) -> String {
        guard installed else { return "Not installed. Nothing is running." }
        switch setting {
        case "gpuboost=1": return "On: the daemon holds the GPU at its maximum boost."
        case "gpuboost=0": return "Installed, switched off."
        case .some(let s): return "Installed; the setting reads \"\(s.prefix(40))\", which the daemon does not accept, so it holds nothing."
        case .none: return "Installed, but there is no setting file; the daemon holds nothing."
        }
    }
}
