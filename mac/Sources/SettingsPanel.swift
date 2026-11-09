import AppKit
import WebKit

/// The "Driver settings" window: the display, performance and GPU facts a Windows control panel shows, over the same catalogue
/// and rules as tools/nullmoth_settings.py (DriverSettings.swift). The page only asks; this file decides. Nothing is written
/// until the user has read the exact change in a native confirmation that the page cannot answer for them, and the write itself
/// is one root command built by DriverSettings.command.
final class SettingsPanel: NSObject, WKScriptMessageHandler {
    static var shared: SettingsPanel?
    private var window: NSWindow?
    private var web: WKWebView?
    private let catalog: DriverSettings.Catalog

    /// Opens the window (or brings it forward). Returns false when the catalogue could not be read.
    @discardableResult static func show() -> Bool {
        if let s = shared { s.window?.makeKeyAndOrderFront(nil); return true }
        guard let res = Bundle.main.resourceURL, let d = try? Data(contentsOf: res.appendingPathComponent("settings_catalog.json")),
              let cat = DriverSettings.load(d) else { return false }
        let s = SettingsPanel(cat); shared = s; s.open(res)
        return true
    }

    private init(_ c: DriverSettings.Catalog) { catalog = c }

    private func open(_ res: URL) {
        let cfg = WKWebViewConfiguration(); cfg.userContentController.add(self, name: "nmset")
        let w = WKWebView(frame: .zero, configuration: cfg)
        let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 760, height: 720), styleMask: [.titled, .closable, .miniaturizable, .resizable],
                           backing: .buffered, defer: false)
        win.title = "Driver settings"; win.contentView = w; win.isReleasedWhenClosed = false; win.center()
        win.minSize = NSSize(width: 560, height: 480)
        w.loadFileURL(res.appendingPathComponent("settings.html"), allowingReadAccessTo: res)
        win.makeKeyAndOrderFront(nil)
        window = win; web = w
        NotificationCenter.default.addObserver(forName: NSWindow.willCloseNotification, object: win, queue: .main) { _ in SettingsPanel.shared = nil }
    }

    // MARK: reading the machine
    private func bootArgs() -> String {
        let p = Process(); p.executableURL = URL(fileURLWithPath: "/usr/sbin/nvram"); p.arguments = ["boot-args"]
        let pipe = Pipe(); p.standardOutput = pipe; p.standardError = FileHandle.nullDevice
        guard (try? p.run()) != nil else { return "" }
        let out = String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self); p.waitUntilExit()
        guard let tab = out.firstIndex(of: "\t") else { return "" }
        return out[out.index(after: tab)...].trimmingCharacters(in: .whitespacesAndNewlines)
    }
    private func confText() -> String { (try? String(contentsOfFile: catalog.confPath, encoding: .utf8)) ?? "" }

    private func current(_ s: DriverSettings.Setting, _ ba: String, _ conf: String) -> String {
        (s.where_ == "bootarg" ? DriverSettings.bootargsGet(ba, s.key) : DriverSettings.confGet(catalog, conf, s.key)) ?? "default"
    }

    private func loadPayload(gpus: [GpuFacts.Gpu]) -> [String: Any] {
        let ba = bootArgs(), conf = confText()
        let list: [[String: Any]] = catalog.settings.map { s in
            var d: [String: Any] = ["id": s.id, "group": s.group, "title": s.title, "help": s.help, "kind": s.kind, "effect": s.effect,
                                    "where": s.where_, "current": current(s, ba, conf)]
            if let v = s.values { d["valueMap"] = v }
            if let r = s.range { d["range"] = [r.0, r.1] }
            return d
        }
        let cards: [[String: Any]] = gpus.map { g in
            ["line": GpuFacts.describe(g), "facts": g.nvrm, "external": g.external]
        }
        return ["settings": list, "gpus": cards, "displays": NSScreen.screens.map { $0.localizedName }, "bootArgsSafe": DriverSettings.bootargsSafe(ba)]
    }

    private func reply(_ event: String, _ data: Any) {
        guard let j = try? JSONSerialization.data(withJSONObject: ["event": event, "data": data]), let s = String(data: j, encoding: .utf8) else { return }
        DispatchQueue.main.async { self.web?.evaluateJavaScript("NMS.on(\(s))") }
    }

    private func describe(_ s: DriverSettings.Setting, _ change: DriverSettings.Change, value: String) -> String {
        switch change {
        case .bootArgs(let line):
            return "\(s.title)\n\nSet to: \(value)\n\nThis changes the Mac's boot arguments to:\n\(line.isEmpty ? "(none)" : line)\n\nIt takes effect after you restart."
        case .conf:
            return "\(s.title)\n\nSet to: \(value)\n\nThis writes \(s.key) into the \"my settings\" block of \(catalog.confPath), which updates keep.\n\nIt takes effect after: \(s.effect)."
        }
    }

    // MARK: messages from the page
    func userContentController(_ c: WKUserContentController, didReceive m: WKScriptMessage) {
        guard let b = m.body as? [String: Any], let act = b["act"] as? String else { return }
        switch act {
        case "load":
            DispatchQueue.global().async { let g = GpuFacts.read(); self.reply("load", self.loadPayload(gpus: g)) }
        case "apply":
            guard let id = b["id"] as? String, let value = b["value"] as? String, let s = catalog.find(id) else { return }
            let ba = bootArgs(), conf = confText()
            let change: DriverSettings.Change
            do { change = try DriverSettings.plan(catalog, s, value, bootArgs: ba, conf: conf) }
            catch DriverSettings.Bad.refused(let why) { reply("result", ["id": id, "ok": false, "message": why]); return }
            catch { reply("result", ["id": id, "ok": false, "message": "\(error)"]); return }
            let a = NSAlert(); a.messageText = "Change this setting?"; a.informativeText = describe(s, change, value: value)
            a.addButton(withTitle: "Change"); a.addButton(withTitle: "Cancel")
            guard a.runModal() == .alertFirstButtonReturn else { reply("result", ["id": id, "ok": false, "message": "Cancelled. Nothing was changed."]); return }
            let cmd = DriverSettings.command(catalog, change), cat = catalog
            DispatchQueue.global().async {
                let r = Privileged.run(cmd, timeout: 120)
                if let e = r.error { self.reply("result", ["id": id, "ok": false, "message": e]); return }
                // read it back: report what is on the machine, not what we meant to write
                let now = self.current(s, self.bootArgs(), self.confText())
                let expect = (try? DriverSettings.normalize(cat, s, value)) ?? nil
                self.reply("result", ["id": id, "ok": now == (expect ?? "default"),
                                      "message": now == (expect ?? "default") ? "Changed. It takes effect after: \(s.where_ == "bootarg" ? "you restart" : s.effect)." : "The change did not stick (now \(now)).",
                                      "current": now])
            }
        default: break
        }
    }
}
