import Foundation

/// NullMoth's own Game Mode: a root daemon that turns it on while a game is in front and full screen, and a menu-bar indicator.
/// Installed and removed by the bundled nullmoth-gamemode-service.sh, run as root through Privileged.bundleScript so the script
/// and the two files it copies are checked against the hashes compiled into the app.
enum GameModeService {
    static let script = "nullmoth-gamemode-service.sh"
    static let policy = "nullmoth-gamemode-policy.py"
    static let indicator = "nullmoth-gamemode-indicator"
    static let daemonPlist = "/Library/LaunchDaemons/com.nullmoth.gamemode.plist"

    /// The root shell line for "install" or "remove".
    static func command(_ op: String, resources: URL, table: [String: String] = BundleHashes.table) -> String? {
        guard op == "install" || op == "remove" else { return nil }
        let args = op == "install" ? [op, resources.appendingPathComponent(policy).path, resources.appendingPathComponent(indicator).path] : [op]
        return Privileged.bundleScript(resources.appendingPathComponent(script).path, args, table: table)
    }

    /// Reads the script's own `status` line: "installed , running" and its three relatives.
    static func parse(_ text: String) -> (installed: Bool, running: Bool) {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return (t.hasPrefix("installed"), t.hasSuffix("running"))
    }

    /// What is installed and running now, without a password: the daemon's plist is world-readable and `launchctl print` of a
    /// system service needs no privilege.
    static func status() -> (installed: Bool, running: Bool) {
        let installed = FileManager.default.fileExists(atPath: daemonPlist)
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        p.arguments = ["print", "system/com.nullmoth.gamemode"]
        p.standardOutput = FileHandle.nullDevice; p.standardError = FileHandle.nullDevice
        do { try p.run(); p.waitUntilExit() } catch { return (installed, false) }
        return (installed, p.terminationStatus == 0)
    }
}
