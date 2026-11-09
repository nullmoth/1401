// 1401
// Copyright (c) 2026 NullMoth Systems. SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

import Foundation

/// The driver package for an action that runs as root is chosen HERE, from the packages the app itself found: the first one
/// that hashes to the SHA-256 compiled into the app. The page's `pkg` field is not read for these actions, and the SHA-256
/// handed to setup is the compiled-in pin, never a hash taken from the chosen file, so setup compares the file to the pin.
enum PackagePin {
    static func choose(candidates: [String], pinnedSha: String, hash: (String) -> String?) -> (path: String, sha: String)? {
        guard !pinnedSha.isEmpty else { return nil }
        for path in candidates where hash(path)?.lowercased() == pinnedSha.lowercased() { return (path, pinnedSha) }
        return nil
    }
}
