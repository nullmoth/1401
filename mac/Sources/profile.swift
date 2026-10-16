import Foundation
import IOKit

/// Live GPU, CPU, platform and macOS properties select per-system rules.
/// Unbound mounted board/chipset profiles are retained only as diagnostic evidence.
enum Profile {
    /// Registry properties may have been injected by EFI; preserve their origin.
    /// They describe the current PCI service and do not bind an attached scan.
    static func displayIdentity(vendor: UInt32, device: UInt32,
                                subsystemVendor: UInt32?, subsystemDevice: UInt32?,
                                path: String) -> [String: Any] {
        var value: [String: Any] = ["vendor": String(format: "%04X", vendor & 0xffff),
                                    "device": String(format: "%04X", device & 0xffff),
                                    "identity_source": "live_registry"]
        if let v = subsystemVendor { value["subsystem_vendor"] = String(format: "%04X", v & 0xffff) }
        if let d = subsystemDevice { value["subsystem_device"] = String(format: "%04X", d & 0xffff) }
        if !path.isEmpty { value["registry_path"] = path }
        return value
    }

    /// A missing or unconfigured battery service is not evidence of a desktop chassis.
    static func attachChassisEvidence(servicePresent: Bool, batteryInstalled: Bool?, to p: inout [String: Any]) {
        p["battery_service_present"] = servicePresent
        p["battery_service_source"] = "AppleSmartBattery registry service"
        p["chassis_identity_origin"] = "kernel-visible service; firmware or driver properties may be injected"
        p.removeValue(forKey: "laptop")
        if servicePresent && batteryInstalled == true {
            p["laptop"] = true
            p["chassis"] = "laptop"
            p["chassis_status"] = "battery service reports installed battery"
        } else {
            p["chassis"] = "unknown"
            p["chassis_status"] = "no validated battery or physical firmware platform-role evidence"
        }
        if let batteryInstalled { p["battery_installed_reported"] = batteryInstalled }
    }

    /// NVIDIA's device-ID ranges per generation (GSP-capable cards only: Turing and later).
    static func arch(_ dev: String) -> String {
        guard let v = Int(dev, radix: 16) else { return "unknown" }
        switch v {
        case 0x1E00...0x21FF: return "turing"
        case 0x2200...0x25FF: return v >= 0x2300 && v < 0x2400 ? "hopper" : "ampere"
        case 0x2600...0x28FF: return "ada"
        case 0x2900...0x2FFF: return "blackwell"
        default: return "unknown"
        }
    }

    /// Does `profile` satisfy every key in `match`? Unknown keys never match (a rule must not apply by accident).
    static func matches(_ match: [String: Any], _ p: [String: Any]) -> Bool {
        for (k, want) in match {
            switch k {
            case "arch", "cpu_vendor", "gpu_id", "chipset":
                guard let list = want as? [String], let have = p[k] as? String, list.contains(where: { $0.caseInsensitiveCompare(have) == .orderedSame }) else { return false }
            case "laptop", "egpu":
                guard let w = want as? Bool, let have = p[k] as? Bool, w == have else { return false }
            case "macos_major":
                guard let list = want as? [Int], let have = p[k] as? Int, list.contains(have) else { return false }
            default:
                return false
            }
        }
        return true
    }

    /// The rules from `rules` (the parsed nullmoth-rules.json) that apply to `p`, and the knobs they set.
    static func select(_ rules: [String: Any], _ p: [String: Any]) -> (ids: [String], conf: [String: String]) {
        var ids: [String] = [], conf: [String: String] = [:]
        for r in (rules["rules"] as? [[String: Any]]) ?? [] {
            guard let id = r["id"] as? String, matches(r["match"] as? [String: Any] ?? [:], p) else { continue }
            ids.append(id)
            for (k, v) in (r["conf"] as? [String: String]) ?? [:]
            where k.range(of: #"^(NVMTL|NVK|NVRM)_[A-Z0-9_]+$"#, options: .regularExpression) != nil
               && v.range(of: #"^[A-Za-z0-9._-]{0,64}$"#, options: .regularExpression) != nil { conf[k] = v }
        }
        return (ids, conf)
    }

    /// Attached profiles have no binding to this boot configuration. Keep them
    /// as diagnostic evidence; their board/chipset must not select live rules.
    static func attachWindowsDiagnostics(_ candidates: [[String: Any]], to p: inout [String: Any]) {
        guard !candidates.isEmpty else { return }
        p["windows_candidates"] = candidates
        p["windows_profile_status"] = "unverified"
    }

    /// True when a Thunderbolt bridge sits between the root complex and the NVIDIA card (an eGPU).
    static func nvidiaBehindThunderbolt() -> Bool {
        var it: io_iterator_t = 0
        guard IOServiceGetMatchingServices(kIOMainPortDefault, IOServiceMatching("IOPCIDevice"), &it) == KERN_SUCCESS else { return false }
        defer { IOObjectRelease(it) }
        var found = false
        while case let dev = IOIteratorNext(it), dev != 0 {
            defer { IOObjectRelease(dev) }
            guard let v = IORegistryEntryCreateCFProperty(dev, "vendor-id" as CFString, kCFAllocatorDefault, 0)?.takeRetainedValue() as? Data,
                  v.count >= 2, v[0] == 0xDE, v[1] == 0x10,
                  let c = IORegistryEntryCreateCFProperty(dev, "class-code" as CFString, kCFAllocatorDefault, 0)?.takeRetainedValue() as? Data,
                  c.count >= 3, c[2] == 0x03 else { continue }
            var cur = dev; IOObjectRetain(cur)
            for _ in 0..<16 {
                var parent: io_registry_entry_t = 0
                guard IORegistryEntryGetParentEntry(cur, kIOServicePlane, &parent) == KERN_SUCCESS else { break }
                IOObjectRelease(cur); cur = parent
                var name = [CChar](repeating: 0, count: 128)
                IOObjectGetClass(cur, &name)
                let cls = String(cString: name)
                if cls.localizedCaseInsensitiveContains("Thunderbolt") { found = true; break }
                if cls == "IOPCIBridge" || cls.hasSuffix("PlatformExpert") { continue }
            }
            IOObjectRelease(cur)
            if found { break }
        }
        return found
    }
}
