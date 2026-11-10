// 1401
// Copyright (c) 2026 NullMoth Systems. SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

import Foundation

/// The "Experimental features" the page may switch on. Only these ids exist: the page sends the whole list that should be on and
/// anything else is dropped here, before setup (which checks again). The fetch-copy switch that affects WindowServer is not,
/// and must never be, in this list.
enum Experimental {
    static let ids: [String] = ["kbl", "kblhid", "tgp", "igpuproxy", "xvt", "hybrid20", "rtd3", "aspm", "gameprio", "hwrt", "curves", "tile", "icb"]

    /// setup's --experimental value for what the page sent, or nil when it sent something that is not a list of known ids.
    static func argument(_ sent: Any?) -> String? {
        guard let list = sent as? [Any] else { return nil }
        var chosen: [String] = []
        for item in list {
            guard let id = item as? String, ids.contains(id) else { return nil }
            if !chosen.contains(id) { chosen.append(id) }
        }
        if chosen.contains("kblhid") && !chosen.contains("kbl") { return nil }
        return chosen.isEmpty ? "none" : ids.filter { chosen.contains($0) }.joined(separator: ",")
    }

    /// The ids that are on, from setup's record (lines ON=<id>).
    static func on(record: String) -> [String] {
        record.split(separator: "\n").compactMap { $0.hasPrefix("ON=") ? String($0.dropFirst(3)) : nil }.filter { ids.contains($0) }
    }
}
