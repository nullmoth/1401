// The Game Mode menu-bar indicator. Runs as a per-user agent, shows a game controller in the menu bar while NullMoth's Game Mode
// is on, and nothing otherwise. It reads the same state the policy daemon publishes: the notify key
// com.nullmoth.gamemode.active (1 on, 0 off) and, at start-up, the root-owned file /Library/NullMoth/gamemode-active.
import AppKit
import Foundation
import notify

final class Indicator: NSObject {
    private let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
    private var token: Int32 = 0

    func start() {
        NSApp.setActivationPolicy(.accessory)
        if let button = item.button {
            button.image = NSImage(systemSymbolName: "gamecontroller.fill", accessibilityDescription: "Game Mode is on")
            button.toolTip = "Game Mode is on"
        }
        let menu = NSMenu()
        menu.addItem(withTitle: "Game Mode is on", action: nil, keyEquivalent: "")
        item.menu = menu
        show(FileManager.default.fileExists(atPath: "/Library/NullMoth/gamemode-active"))
        notify_register_dispatch("com.nullmoth.gamemode.active", &token, DispatchQueue.main) { [weak self] t in
            var state: UInt64 = 0
            notify_get_state(t, &state)
            self?.show(state == 1)
        }
    }

    private func show(_ on: Bool) { item.isVisible = on }
}

let app = NSApplication.shared
let indicator = Indicator()
indicator.start()
app.run()
