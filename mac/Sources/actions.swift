import Foundation

/// Direct web messages may request only the visible driver operations.
enum AppActions {
    static func directRunMode(_ value: Any?) -> String? {
        guard let value else { return "dry" }
        guard let mode = value as? String, ["dry", "install", "remove"].contains(mode) else { return nil }
        return mode
    }
}
