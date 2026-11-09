// 1401
// Copyright (c) 2026 NullMoth Systems. SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

import Foundation

/// An EFI choice of the form "config:<path>" is a config.plist the user picked (setup --config). Only an absolute path to
/// an existing plain file named *.plist on one line is accepted; setup checks that it is a real OpenCore config before it
/// changes anything. Any other choice (a partition id, "auto") is not a config choice.
enum ConfigChoice {
    static func path(_ s: String) -> String? {
        guard s.hasPrefix("config:") else { return nil }
        let p = String(s.dropFirst(7))
        guard p.hasPrefix("/"), p.hasSuffix(".plist"), !p.contains("\n") else { return nil }
        var isDir: ObjCBool = false
        guard FileManager.default.fileExists(atPath: p, isDirectory: &isDir), !isDir.boolValue else { return nil }
        return p
    }
}
