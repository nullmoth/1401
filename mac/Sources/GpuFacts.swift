import Foundation

/// The NVIDIA GPUs the Mac sees, from the I/O Registry: generation, the PCIe link negotiated against what the card supports,
/// whether it sits behind Thunderbolt, which driver parts are attached, and the facts the kext publishes on the card (BAR1,
/// Resizable BAR, Above 4G, link power). A port of tools/nvmtl_gpus.py; tests/gpufacts proves the same cases.
enum GpuFacts {
    struct Link: Equatable {
        var verdict: String            // ok, degraded, idle-or-low, unknown
        var speed = 0.0, maxSpeed = 0.0
        var width = 0, maxWidth = 0
    }
    struct Gpu: Equatable {
        var deviceID: String, generation: String, bus: String
        var link: Link
        var external: Bool
        var driver: [String]
        var nvrm: [String: String]     // nvrm-bar1-mb, nvrm-rebar, nvrm-above-4g, nvrm-aspm ...
    }

    static let generations: [(Int, Int, String)] = [(0x2900, 0x2fff, "Blackwell"), (0x2600, 0x28ff, "Ada"), (0x2200, 0x25ff, "Ampere"),
                                                    (0x2000, 0x20ff, "Ampere"), (0x2180, 0x21ff, "Turing"), (0x1e00, 0x1fff, "Turing")]
    static let speed: [Int: Double] = [1: 2.5, 2: 5, 3: 8, 4: 16, 5: 32, 6: 64]
    static let tunnel = ["Thunderbolt", "USB4"]
    static let driverParts = ["NVRM", "NVAccel", "NVRMFB"]
    static let factKeys = ["nvrm-bar1-mb", "nvrm-bar1-firmware-mb", "nvrm-rebar-max-mb", "nvrm-rebar", "nvrm-above-4g", "nvrm-aspm"]

    static func generation(_ dev: Int) -> String {
        for (lo, hi, n) in generations where lo <= dev && dev <= hi { return n }
        return dev < 0x1e00 ? "older than Turing (not supported)" : "unknown"
    }

    static func decodeLink(status: Int?, caps: Int?) -> Link {
        guard let st = status, let cp = caps, let cs = speed[st & 0xf], let ms = speed[cp & 0xf] else { return Link(verdict: "unknown") }
        let cw = (st >> 4) & 0x3f, mw = (cp >> 4) & 0x3f
        guard cw > 0 && mw > 0 else { return Link(verdict: "unknown") }
        let v = cw < mw ? "degraded" : (cs < ms ? "idle-or-low" : "ok")
        return Link(verdict: v, speed: cs, maxSpeed: ms, width: cw, maxWidth: mw)
    }

    /// A 16/32-bit register property: a number, or little-endian data.
    static func word(_ v: Any?) -> Int? {
        if let n = v as? Int { return n }
        if let d = v as? Data, !d.isEmpty { return d.prefix(4).enumerated().reduce(0) { $0 | (Int($1.element) << (8 * $1.offset)) } }
        return nil
    }

    static func gpus(_ tree: Any) -> [Gpu] {
        var out: [Gpu] = []
        func kids(_ n: [String: Any]) -> [[String: Any]] { n["IORegistryEntryChildren"] as? [[String: Any]] ?? [] }
        func descendantClasses(_ n: [String: Any]) -> [String] { kids(n).flatMap { [$0["IOObjectClass"] as? String ?? ""] + descendantClasses($0) } }
        func walk(_ n: [String: Any], _ chain: [String]) {
            let cls = n["IOObjectClass"] as? String ?? ""
            if word(n["vendor-id"]) == 0x10de, let dev = word(n["device-id"]), let code = word(n["class-code"]), code >> 16 == 0x03 {
                let below = descendantClasses(n)
                var facts: [String: String] = [:]
                for k in factKeys { if let i = n[k] as? Int { facts[k] = String(i) } else if let s = n[k] as? String { facts[k] = s } else if let d = n[k] as? Data, let i = word(d) { facts[k] = String(i) } }
                out.append(Gpu(deviceID: String(format: "%04X", dev), generation: generation(dev), bus: n["pcidebug"] as? String ?? "",
                               link: decodeLink(status: word(n["IOPCIExpressLinkStatus"]), caps: word(n["IOPCIExpressLinkCapabilities"])),
                               external: chain.contains { c in tunnel.contains { c.contains($0) } },
                               driver: driverParts.filter { p in below.contains { $0.hasPrefix(p) } }, nvrm: facts))
            }
            for c in kids(n) { walk(c, chain + [cls]) }
        }
        if let roots = tree as? [[String: Any]] { roots.forEach { walk($0, []) } } else if let r = tree as? [String: Any] { walk(r, []) }
        return out
    }

    /// One line a person can read. A narrower link is called out; a lower speed at full width is explained, not alarmed.
    static func describe(_ g: Gpu) -> String {
        var link: String
        switch g.link.verdict {
        case "unknown": link = "PCIe link unreadable"
        case "degraded": link = "PCIe \(trim(g.link.speed)) GT/s x\(g.link.width), LOW: the card supports x\(g.link.maxWidth)"
        case "idle-or-low": link = "PCIe \(trim(g.link.speed)) GT/s x\(g.link.width) (the card supports \(trim(g.link.maxSpeed)) GT/s; links step down at idle)"
        default: link = "PCIe \(trim(g.link.speed)) GT/s x\(g.link.width)"
        }
        return "\(g.deviceID) \(g.generation): \(link)" + (g.external ? ", external (Thunderbolt)" : "") + ", driver: " + (g.driver.isEmpty ? "not attached" : g.driver.joined(separator: ", "))
    }
    private static func trim(_ d: Double) -> String { d == d.rounded() ? String(Int(d)) : String(d) }

    /// The live registry. Slow (a few MB of plist): call it off the main thread.
    static func read() -> [Gpu] {
        let p = Process(); p.executableURL = URL(fileURLWithPath: "/usr/sbin/ioreg"); p.arguments = ["-a", "-l", "-p", "IOService"]
        let pipe = Pipe(); p.standardOutput = pipe; p.standardError = FileHandle.nullDevice
        guard (try? p.run()) != nil else { return [] }
        let data = pipe.fileHandleForReading.readDataToEndOfFile(); p.waitUntilExit()
        guard let tree = try? PropertyListSerialization.propertyList(from: data, options: [], format: nil) else { return [] }
        return gpus(tree)
    }
}
