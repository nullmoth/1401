// Copyright (c) 2026 NullMoth Systems.
// Checks an OpenCore config against efi_rules.json, the same rule file the Windows builder applies (p1401/efi_rules.py).
// Both checkers are tested against the same cases (mac/tests/efi_rules/vectors.json), so a config gets the same issues
// here as in 1401 for Windows. A rule this file cannot read throws instead of passing.
import Foundation

enum EfiRulesError: Error, CustomStringConvertible {
    case schema(String), unknownMatch(String), unknownExpectation(String), noFix(String)
    var description: String {
        switch self {
        case .schema(let s): return "unknown rule file schema \(s)"
        case .unknownMatch(let s): return "unknown match key \(s)"
        case .unknownExpectation(let s): return "unknown expectation \(s)"
        case .noFix(let s): return "no fix for \(s)"
        }
    }
}

struct EfiIssue {
    let id: String, title: String, what: String, steps: [String], restart: Bool
    let failed: [[String: Any]]
    var json: [String: Any] { ["id": id, "title": title, "what": what, "steps": steps, "restart": restart] }
}

enum EfiRules {
    static let boot = "7C436110-AB2A-4BBB-A880-FE41995C9F82"

    static func load(_ url: URL) throws -> [String: Any] {
        let data = try Data(contentsOf: url)
        guard let rules = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              rules["schema"] as? String == "nullmoth-efi-rules/1" else {
            throw EfiRulesError.schema(url.lastPathComponent)
        }
        return rules
    }

    /// A deep mutable copy, so check() and fix() never change what they were given.
    static func mutableCopy(_ cfg: [String: Any]) throws -> NSMutableDictionary {
        let data = try PropertyListSerialization.data(fromPropertyList: cfg, format: .binary, options: 0)
        let copy = try PropertyListSerialization.propertyList(from: data, options: .mutableContainersAndLeaves, format: nil)
        return copy as? NSMutableDictionary ?? NSMutableDictionary()
    }

    // MARK: facts

    static func darwin(_ v: String) -> [Int] {
        let parts = v.split(separator: ".").map { Int($0) ?? 0 }
        return (parts + [0, 0, 0]).prefix(3).map { $0 }
    }

    static func matches(_ match: [String: Any], _ facts: [String: Any]) throws -> Bool {
        let classes = Set(facts["cpu_class"] as? [String] ?? [])
        let known = Set(facts["fact"] as? [String] ?? [])
        for (key, want) in match {
            switch key {
            case "macos_min":
                guard let mac = facts["macos"] as? String, !mac.isEmpty,
                      !darwin(mac).lexicographicallyPrecedes(darwin(want as? String ?? "")) else { return false }
            case "cpu_class":
                if classes.isDisjoint(with: want as? [String] ?? []) { return false }
            case "cpu_class_not":
                if !classes.isDisjoint(with: want as? [String] ?? []) { return false }
            case "chipset_not_in":
                if (want as? [String] ?? []).contains(facts["chipset"] as? String ?? "") { return false }
            case "fact":
                if !Set(want as? [String] ?? []).isSubset(of: known) { return false }
            case "fact_absent":
                if !known.isDisjoint(with: want as? [String] ?? []) { return false }
            case "cpu_vendor", "laptop", "amd_dgpu", "intel_igpu":
                guard let have = facts[key] as? NSObject, !(have is NSNull), have.isEqual(want) else { return false }
            default:
                throw EfiRulesError.unknownMatch(key)
            }
        }
        return true
    }

    /// The CPU families the rules match on, from the brand string alone (a Mac has no codename). The same tests as
    /// p1401/policy.py and efi_rules.py with an empty codename; checked against every brand string in
    /// tests/efi_rules/cpu_names.txt.
    static func cpuClasses(vendor: String, name: String) -> [String] {
        func has(_ pattern: String, _ caseless: Bool = false) -> Bool {
            name.range(of: pattern, options: caseless ? [.regularExpression, .caseInsensitive] : .regularExpression) != nil
        }
        var c: [String] = []
        if vendor == "AMD" && has(#"Ryzen AI\b|Ryzen [3579] (?:[79]\d\d0(?:X3D|X|F)?|8\d00[FG])\b|Ryzen [3579] [78]\d[45]\d(?:HX3D|HX|HS|H|U)\b"#, true) {
            c.append("zen45")
        }
        if vendor == "Intel" {
            if has(#"Core\(TM\) Ultra|1[234]th Gen.*Core\(TM\)"#, true) { c.append("intel_hybrid") }
            if name.contains("Core(TM) Ultra") { c.append("core_ultra") }
            if has(#"Core\(TM\) Ultra [3579] 2\d\d(?:K|KF|F|T|H|HX|U)?(?: Plus)?\b(?!V)"#) { c.append("arrow_lake") }
        }
        return c.sorted()
    }

    /// Facts read from OpenCore's own log of this boot: which ACPI tables the firmware handed it. Without a log nothing
    /// is known, and no fact is added (a rule that needs one then applies, which is the safe direction).
    static func logFacts(_ log: String?) -> [String] {
        guard let log = log, log.contains("OCA: Found") else { return [] }
        return log.contains("Detected table DMAR") ? [] : ["firmware_no_dmar"]
    }

    // MARK: reading the config

    static func isBool(_ n: NSNumber) -> Bool { CFGetTypeID(n) == CFBooleanGetTypeID() }

    static func truthy(_ v: Any?) -> Bool {
        switch v {
        case nil, is NSNull: return false
        case let n as NSNumber: return n.boolValue
        case let s as String: return !s.isEmpty
        case let a as NSArray: return a.count > 0
        case let d as NSDictionary: return d.count > 0
        default: return true
        }
    }

    static func get(_ cfg: NSDictionary, _ path: String) -> Any? {
        var node: Any = cfg
        for part in path.split(separator: ".") {
            guard let d = node as? NSDictionary, let next = d[String(part)] else { return nil }
            node = next
        }
        return node
    }

    static func set(_ cfg: NSMutableDictionary, _ path: String, _ value: Any) {
        let parts = path.split(separator: ".").map(String.init)
        var node = cfg
        for part in parts.dropLast() {
            if let next = node[part] as? NSMutableDictionary { node = next } else {
                let next = NSMutableDictionary(); node[part] = next; node = next
            }
        }
        node[parts.last!] = value
    }

    static func list(_ cfg: NSDictionary, _ path: String) -> [NSMutableDictionary] {
        (get(cfg, path) as? NSArray)?.compactMap { $0 as? NSMutableDictionary } ?? []
    }

    static func kextName(_ k: NSDictionary) -> String {
        String((k["BundlePath"] as? String ?? "").split(separator: "/", omittingEmptySubsequences: false).last ?? "")
    }

    static func args(_ cfg: NSDictionary) -> [String] {
        (get(cfg, "NVRAM.Add.\(boot).boot-args") as? String ?? "").split(whereSeparator: { $0 == " " || $0 == "\t" || $0 == "\n" }).map(String.init)
    }

    static func setArgs(_ cfg: NSMutableDictionary, _ a: [String]) { set(cfg, "NVRAM.Add.\(boot).boot-args", a.joined(separator: " ")) }

    static func same(_ have: Any?, _ want: Any) -> Bool {
        switch want {
        case let w as NSNumber:
            guard let h = have as? NSNumber, isBool(h) == isBool(w) else { return false }
            return h == w
        case let w as String: return (have as? String) == w
        default: return false
        }
    }

    // MARK: expectations

    static func holds(_ cfg: NSMutableDictionary, _ p: [String: Any]) throws -> Bool {
        if let any = p["any"] as? [[String: Any]] { return try any.contains { try holds(cfg, $0) } }
        if let path = p["path"] as? String {
            let v = get(cfg, path) ?? p["default"]
            if let eq = p["eq"] { return v != nil && same(v, eq) }
            if let ne = p["ne"] { return !same(v, ne) }
            if let bits = p["bits"] as? Int {
                guard let n = v as? NSNumber, !isBool(n) else { return false }
                return n.intValue & bits == bits
            }
        }
        if let name = p["kext"] as? String, let enabled = p["enabled"] as? Bool {
            let ks = list(cfg, "Kernel.Add").filter { kextName($0) == name }
            return ks.contains { truthy($0["Enabled"]) == enabled } || (!enabled && ks.isEmpty)
        }
        if let name = p["kext_listed"] as? String { return list(cfg, "Kernel.Add").contains { kextName($0) == name } }
        if let a = p["boot_arg"] as? String, let present = p["present"] as? Bool { return args(cfg).contains(a) == present }
        if let pre = p["boot_arg_prefix"] as? String, let present = p["present"] as? Bool {
            return args(cfg).contains { $0.hasPrefix(pre) } == present
        }
        if let item = p["boot_arg_item"] as? [String], item.count == 2 {
            return args(cfg).contains { $0.hasPrefix(item[0] + "=") && $0.dropFirst(item[0].count + 1).split(separator: ",").contains(Substring(item[1])) }
        }
        if let lacks = p["list_lacks"] as? [String], lacks.count == 2 {
            return !((get(cfg, lacks[0]) as? NSArray)?.contains(lacks[1]) ?? false)
        }
        if let sig = p["acpi_delete"] as? String {
            return list(cfg, "ACPI.Delete").contains { ($0["TableSignature"] as? Data) == Data(sig.utf8) && truthy($0["Enabled"]) }
        }
        if let id = p["kernel_block"] as? String, let enabled = p["enabled"] as? Bool {
            return list(cfg, "Kernel.Block").contains { $0["Identifier"] as? String == id && truthy($0["Enabled"]) == enabled }
        }
        if let path = p["driver"] as? String, let loaded = p["loaded"] as? Bool {
            let on = list(cfg, "UEFI.Drivers").contains { $0["Path"] as? String == path && truthy($0["Enabled"] ?? true) }
            return on == loaded
        }
        if let name = p["check"] as? String { return try structural(name, cfg, fix: false) == 0 }
        throw EfiRulesError.unknownExpectation("\(p)")
    }

    static func apply(_ cfg: NSMutableDictionary, _ p: [String: Any]) throws {
        if let path = p["path"] as? String {
            if let eq = p["eq"] { set(cfg, path, eq); return }
            if p["ne"] != nil, let fix = p["fix"] { set(cfg, path, fix); return }
            if let bits = p["bits"] as? Int {
                let v = (get(cfg, path) ?? p["default"] ?? 0) as? NSNumber
                set(cfg, path, NSNumber(value: (v?.intValue ?? 0) | bits)); return
            }
        }
        if let name = p["kext"] as? String, let enabled = p["enabled"] as? Bool {
            for k in list(cfg, "Kernel.Add") where kextName(k) == name { k["Enabled"] = enabled }
            return
        }
        if let a = p["boot_arg"] as? String, let present = p["present"] as? Bool {
            let rest = args(cfg).filter { $0 != a }
            setArgs(cfg, present ? rest + [a] : rest); return
        }
        if let pre = p["boot_arg_prefix"] as? String { setArgs(cfg, args(cfg).filter { !$0.hasPrefix(pre) }); return }
        if let item = p["boot_arg_item"] as? [String], item.count == 2 {
            let a = args(cfg)
            let old = a.first { $0.hasPrefix(item[0] + "=") }
            let vals = (old.map { $0.dropFirst(item[0].count + 1).split(separator: ",").map(String.init) } ?? []).filter { !$0.isEmpty } + [item[1]]
            setArgs(cfg, a.filter { $0 != old } + [item[0] + "=" + vals.joined(separator: ",")]); return
        }
        if let lacks = p["list_lacks"] as? [String], lacks.count == 2 {
            (get(cfg, lacks[0]) as? NSMutableArray)?.remove(lacks[1]); return
        }
        if let sig = p["acpi_delete"] as? String {
            append(cfg, "ACPI.Delete", ["All": true, "Comment": "Drop \(sig)", "Enabled": true, "OemTableId": Data(count: 8),
                                        "TableLength": 0, "TableSignature": Data(sig.utf8)]); return
        }
        if let id = p["kernel_block"] as? String {
            append(cfg, "Kernel.Block", ["Arch": "x86_64", "Comment": "Block \(id)", "Enabled": true, "Identifier": id,
                                         "MaxKernel": "", "MinKernel": p["min_kernel"] as? String ?? "", "Strategy": "Exclude"]); return
        }
        if let name = p["check"] as? String { _ = try structural(name, cfg, fix: true); return }
        throw EfiRulesError.noFix("\(p)")
    }

    static func append(_ cfg: NSMutableDictionary, _ path: String, _ entry: [String: Any]) {
        if let a = get(cfg, path) as? NSMutableArray { a.add(NSMutableDictionary(dictionary: entry)); return }
        set(cfg, path, NSMutableArray(object: NSMutableDictionary(dictionary: entry)))
    }

    /// The structural checks: how many problems they found (and fixed, with fix).
    static func structural(_ name: String, _ cfg: NSMutableDictionary, fix: Bool) throws -> Int {
        switch name {
        case "no-duplicate-add":
            var found = 0
            for (section, key) in [("ACPI", "Path"), ("Kernel", "BundlePath")] {
                guard let entries = get(cfg, "\(section).Add") as? NSMutableArray else { continue }
                var seen = Set<String>(), kept: [Any] = []
                for e in entries {
                    if let k = (e as? NSDictionary)?[key] as? String, !k.isEmpty, seen.contains(k) { found += 1; continue }
                    if let k = (e as? NSDictionary)?[key] as? String { seen.insert(k) }
                    kept.append(e)
                }
                if fix && kept.count != entries.count { entries.setArray(kept) }
            }
            return found
        case "mmio-whitelist-off":
            let on = list(cfg, "Booter.MmioWhitelist").filter { truthy($0["Enabled"]) }
            if fix { on.forEach { $0["Enabled"] = false } }
            return on.count
        case "replace-within-mask":
            var bad = 0
            for pt in list(cfg, "Kernel.Patch") {
                guard let rep = pt["Replace"] as? Data, let msk = pt["ReplaceMask"] as? Data, !msk.isEmpty, rep.count == msk.count else { continue }
                let clean = Data(zip(rep, msk).map { $0 & $1 })
                if clean != rep { bad += 1; if fix { pt["Replace"] = clean } }
            }
            return bad
        default:
            throw EfiRulesError.unknownExpectation("check \(name)")
        }
    }

    // MARK: the two calls the app makes

    /// One issue per rule that applies to this machine and that the config does not meet. Rules run in file order on a
    /// working copy that takes each earlier fix, as the Python checker does.
    static func check(_ cfg: [String: Any], facts: [String: Any], scope: String, rules: [String: Any]) throws -> [EfiIssue] {
        let work = try mutableCopy(cfg)
        var issues: [EfiIssue] = []
        for r in rules["rules"] as? [[String: Any]] ?? [] {
            guard (r["scope"] as? [String] ?? []).contains(scope), try matches(r["match"] as? [String: Any] ?? [:], facts),
                  try (r["when"] as? [[String: Any]] ?? []).allSatisfy({ try holds(work, $0) }) else { continue }
            let failed = try (r["expect"] as? [[String: Any]] ?? []).filter { try !holds(work, $0) }
            guard !failed.isEmpty else { continue }
            issues.append(EfiIssue(id: r["id"] as? String ?? "", title: r["title"] as? String ?? "", what: r["what"] as? String ?? "",
                                   steps: r["steps"] as? [String] ?? [], restart: r["restart"] as? Bool ?? true, failed: failed))
            for e in failed { try apply(work, e) }
        }
        return issues
    }

    /// A fixed copy of cfg; the input is never changed.
    static func fix(_ cfg: [String: Any], _ issues: [EfiIssue]) throws -> NSMutableDictionary {
        let out = try mutableCopy(cfg)
        for issue in issues { for e in issue.failed { try apply(out, e) } }
        return out
    }
}
