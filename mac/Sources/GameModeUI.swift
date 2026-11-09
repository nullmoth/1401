import Foundation

// The window side of Game Mode: the card in the Tools tab turns it on and off (GameMode.swift builds the root command).
extension App {
    func gmStatusEvent(_ extra: [String: Any] = [:]) {
        let s = GameModeService.status()
        var e: [String: Any] = ["installed": s.installed, "running": s.running]
        for (k, v) in extra { e[k] = v }
        DispatchQueue.main.async { self.send("gm", e) }
    }

    func gmAction(_ b: [String: Any]) {
        let op = b["op"] as? String ?? "status"
        guard op == "on" || op == "off" else { return gmStatusEvent() }
        guard let res = Bundle.main.resourceURL, let cmd = GameModeService.command(op == "on" ? "install" : "remove", resources: res) else {
            return gmStatusEvent(["why": "Game Mode could not be prepared."])
        }
        DispatchQueue.global(qos: .userInitiated).async {
            let r = Privileged.run(cmd, timeout: 2 * 60)
            if r.cancelled { return self.gmStatusEvent() }
            let ok = r.error == nil && r.output.contains(op == "on" ? "installed" : "removed")
            let why = ok ? nil : (r.error ?? String(r.output.suffix(300)))
            self.gmStatusEvent(why.map { ["why": redact($0)] } ?? [:])
        }
    }
}
