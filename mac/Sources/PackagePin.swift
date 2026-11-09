// 1401
// Copyright (c) 2026 NullMoth Systems. SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

import Foundation

/// The driver package for an action that runs as root. The page may only NAME a package; it never supplies the integrity
/// check. The path must be one the app itself found (its own candidate list), and the SHA-256 handed to setup is the one
/// compiled into the app, so setup compares the file to that pin and not to itself. A file that does not hash to the pin
/// is refused here, before the password prompt.
enum PackagePin {
    static func resolve(requested: String, candidates: [String], pinnedSha: String, hash: (String) -> String?) -> (path: String, sha: String)? {
        guard !requested.isEmpty, !pinnedSha.isEmpty else { return nil }
        let wanted = URL(fileURLWithPath: requested).resolvingSymlinksInPath().path
        guard let path = candidates.first(where: { URL(fileURLWithPath: $0).resolvingSymlinksInPath().path == wanted }) else { return nil }
        guard hash(path)?.lowercased() == pinnedSha.lowercased() else { return nil }
        return (path, pinnedSha)
    }
}
