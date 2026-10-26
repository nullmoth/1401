// Copyright (c) 2026 NullMoth Systems.
// The app's EFI check: the facts the rules match on, read from this Mac, checked against the config this Mac starts
// from. nullmoth-setup.sh --efi-read finds that config the same way an install does (OpenCore's boot path, else the
// config that sets this Mac's serial, else the only OpenCore partition) and copies it out without changing anything.
import AppKit
import Foundation
import IOKit

enum EfiCheck {
    /// The facts efi_rules.json matches on, from this Mac. The board chipset is not visible from macOS, so rules keyed
    /// on it read it as unknown, the same as the Windows checker does with a scan that has none.
    static func liveFacts(log: String?) -> [String: Any] {
        let raw = sysctl("machdep.cpu.vendor")
        let vendor = raw == "GenuineIntel" ? "Intel" : raw == "AuthenticAMD" ? "AMD" : ""
        let name = sysctl("machdep.cpu.brand_string")
        let gpus = pciDisplays()
        // A battery means a laptop; so does a MacBook model when the battery driver is not loaded.
        let batteries = services("AppleSmartBattery")
        batteries.forEach { IOObjectRelease($0) }
        // An AMD APU's own graphics also count here: from macOS an integrated AMD GPU and a card look the same, and
        // the one rule that reads this (WhateverGreen on macOS 26) applies to both.
        return ["macos": sysctl("kern.osrelease"), "cpu_vendor": vendor, "cpu_name": name,
                "cpu_class": EfiRules.cpuClasses(vendor: vendor, name: name), "chipset": "",
                "laptop": !batteries.isEmpty || sysctl("hw.model").hasPrefix("MacBook"),
                "amd_dgpu": gpus.contains { $0["vendor"] as? String == "1002" },
                "intel_igpu": gpus.contains { $0["vendor"] as? String == "8086" },
                "fact": EfiRules.logFacts(log)]
    }

    /// Checks what setup --efi-read left in `folder`: config.plist, scope, partition and (when OpenCore wrote one)
    /// opencore.txt.
    static func check(folder: URL, rules: URL) -> [String: Any] {
        let read = { (name: String) in try? String(contentsOf: folder.appendingPathComponent(name), encoding: .utf8) }
        guard let data = try? Data(contentsOf: folder.appendingPathComponent("config.plist")),
              let cfg = try? PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any] else {
            return ["ok": false, "why": "The OpenCore config could not be read."]
        }
        // OpenCore's log is ASCII with a NUL-padded tail; a lenient decode keeps every table line.
        let log = (try? Data(contentsOf: folder.appendingPathComponent("opencore.txt"))).map { String(decoding: $0, as: Unicode.ASCII.self) }
        // The EFI that started this Mac is booting an installed macOS, even when it lives on the 1401 stick: the stick's
        // installer-only rules (which the Mac setup deliberately undoes, such as NVRM Delete boot-args) do not apply.
        // 10-26 a Mac started from its stick was told to remove the boot-args entry setup had added on purpose.
        let scope = "installed"
        let facts = liveFacts(log: log)
        do {
            let issues = try EfiRules.check(cfg, facts: facts, scope: scope, rules: EfiRules.load(rules))
            return ["ok": true, "scope": scope, "partition": read("partition")?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "",
                    "boot_log": log != nil, "facts": facts, "issues": issues.map(\.json)]
        } catch {
            return ["ok": false, "why": "The EFI rules could not be read: \(error)"]
        }
    }

    /// Tools > Mount EFI: setup proves which EFI partition this Mac started from (as --efi-read does), and the same root
    /// shell mounts it, so there is one password prompt; Finder then opens it for the user.
    static func mount() -> [String: Any] {
        let fm = FileManager.default, res = Bundle.main.resourceURL!
        let dir = fm.temporaryDirectory.appendingPathComponent("1401-efi-" + UUID().uuidString)
        do { try fm.createDirectory(at: dir, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700]) }
        catch { return ["ok": false, "why": "Could not make a temporary folder: \(error.localizedDescription)"] }
        defer { try? fm.removeItem(at: dir) }
        let q = { (s: String) in "'" + s.replacingOccurrences(of: "'", with: "'\\''") + "'" }
        let cmd = Privileged.bundleScript(res.appendingPathComponent("nullmoth-setup.sh").path, ["--efi-read", dir.path])
            + " && /usr/sbin/diskutil mount \"$(/bin/cat " + q(dir.appendingPathComponent("partition").path) + ")\""
        let r = Privileged.run(cmd, timeout: 5 * 60)
        if r.cancelled { return ["ok": false, "cancelled": true] }
        let part = (try? String(contentsOf: dir.appendingPathComponent("partition"), encoding: .utf8))?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard r.error == nil, !part.isEmpty, part.range(of: #"^disk[0-9]+s[0-9]+$"#, options: .regularExpression) != nil else {
            let stop = r.output.split(separator: "\n").first { $0.hasPrefix("STOP ") }.map { String($0.dropFirst(5)) }
            return ["ok": false, "why": stop ?? r.error ?? "The EFI partition could not be found."]
        }
        let info = sh("/usr/sbin/diskutil", ["info", part])
        let where_ = info.split(separator: "\n").first { $0.contains("Mount Point:") }
            .map { $0.split(separator: ":", maxSplits: 1).last.map { $0.trimmingCharacters(in: .whitespaces) } ?? "" } ?? ""
        guard !where_.isEmpty else { return ["ok": false, "why": "macOS did not mount \(part)."] }
        DispatchQueue.main.async { NSWorkspace.shared.open(URL(fileURLWithPath: where_)) }
        return ["ok": true, "partition": part, "where": where_]
    }

    /// The window's "Check my EFI": reads the config through setup (one administrator prompt), then checks it.
    static func run(efi: String) -> [String: Any] {
        let fm = FileManager.default, res = Bundle.main.resourceURL!
        let dir = fm.temporaryDirectory.appendingPathComponent("1401-efi-" + UUID().uuidString)
        do { try fm.createDirectory(at: dir, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700]) }
        catch { return ["ok": false, "why": "Could not make a temporary folder: \(error.localizedDescription)"] }
        defer { try? fm.removeItem(at: dir) }
        var args = ["--efi-read", dir.path]
        if efi != "auto", !efi.isEmpty { args += ["--efi", efi] }
        let r = Privileged.run(Privileged.bundleScript(res.appendingPathComponent("nullmoth-setup.sh").path, args), timeout: 5 * 60)
        if r.cancelled { return ["ok": false, "cancelled": true] }
        guard r.error == nil, r.output.contains("RESULT ok") else {
            let stop = r.output.split(separator: "\n").first { $0.hasPrefix("STOP ") }.map { String($0.dropFirst(5)) }
            return ["ok": false, "why": stop ?? r.error ?? "Reading the EFI did not finish.",
                    "candidates": r.output.split(separator: "\n").filter { $0.hasPrefix("NOTE candidate ") }.map { String($0.dropFirst(15)) }]
        }
        return check(folder: dir, rules: res.appendingPathComponent("efi_rules.json"))
    }
}
