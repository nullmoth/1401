// 1401
// Copyright (c) 2026 NullMoth Systems. SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

import Foundation

// Which macOS this app may install the driver on: 15 and 26 only. On any other macOS every driver install, driver
// download, driver update offer and Tahoe step is refused here, in setup (driver_os_ok), and by the kexts themselves;
// Send logs, the first-login report and the app's own updates are unaffected.
enum OSGate {
    static let driverMajors: Set<Int> = [15, 26]

    static var currentMajor: Int { ProcessInfo.processInfo.operatingSystemVersion.majorVersion }

    static func driverInstallAllowed(major: Int) -> Bool { driverMajors.contains(major) }

    /// The setup modes that install, update or prepare the driver; each is refused outside driverMajors.
    static let installModes: Set<String> = ["dry", "install", "tahoe"]

    /// Why this setup mode may not run on this macOS, or nil when it may.
    static func refusal(mode: String, major: Int) -> String? {
        guard installModes.contains(mode), !driverInstallAllowed(major: major) else { return nil }
        return refusal(major: major)
    }

    static func refusal(major: Int) -> String {
        "The driver is built for macOS 15 Sequoia and macOS 26 Tahoe; this Mac runs macOS \(major)."
    }
}
