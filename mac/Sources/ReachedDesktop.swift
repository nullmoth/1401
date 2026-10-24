// 1401
// Copyright (c) 2026 NullMoth Systems. SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

import Foundation
import CoreGraphics
import CryptoKit
import IOKit
import Metal

// A one-time confirmation that the Mac reached its desktop after a 1401 install. Today nothing tells us whether an
// install actually booted through to a logged-in desktop: a machine that fails silently and one that works both go
// quiet, so a working install is indistinguishable from a dead one. When the user agrees during setup, the first login
// after the install sends one small, redacted summary of what reached the desktop, then takes itself back out. It is
// opt-in, runs at most once per install, and removes its own login item after it sends (or after a few failed tries),
// so nothing is left running - the 2.2 driver carries no other background job. It rides the same login-item mechanism,
// redaction and upload as the AMD/Intel test report (TesterLane).
enum ReachedDesktop {
    static let stateFile = support.appendingPathComponent("reached-desktop.json")
    static let agentLabel = "com.nullmoth.reacheddesktop"
    // The login item that sends it. Only a few starts are tried before it gives up, so a machine that can never reach
    // the site does not keep a dead item forever.
    static let maxTries = 5
    static var agentFile: URL {
        FileManager.default.urls(for: .libraryDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("LaunchAgents/\(agentLabel).plist")
    }

    static func state() -> [String: Any] {
        (try? JSONSerialization.jsonObject(with: Data(contentsOf: stateFile))) as? [String: Any] ?? [:]
    }

    static func save(_ s: [String: Any]) {
        try? FileManager.default.createDirectory(at: support, withIntermediateDirectories: true)
        if let d = try? JSONSerialization.data(withJSONObject: s, options: [.prettyPrinted, .sortedKeys]) {
            try? d.write(to: stateFile, options: .atomic)
        }
    }

    /// Arms or disarms the one-time report after an install. With consent it writes the login item that runs
    /// `1401 --reached-desktop` once at the next login; without consent it installs nothing and clears anything a
    /// previous install left, so the honest default (the user did not agree) leaves no item and sends nothing.
    /// Returns the reason it could not arm, or nil.
    @discardableResult
    static func arm(consent: Bool) -> String? {
        let fm = FileManager.default
        if !consent { remove(); return nil }
        // The item runs this exact copy of 1401 at login; refuse it when 1401 sits where another user could replace it
        // (the item would then run that user's program in this login session), the same guard the test program uses.
        guard let exe = Bundle.main.executableURL?.resolvingSymlinksInPath() else { return "1401's own path is unknown" }
        var dir = exe.deletingLastPathComponent()
        while dir.path != "/" {
            if let a = try? fm.attributesOfItem(atPath: dir.path), let p = a[.posixPermissions] as? Int, p & 0o002 != 0 {
                return "1401 is in a folder other users can change (\(dir.path)); move it into Applications first"
            }
            dir = dir.deletingLastPathComponent()
        }
        let plist: [String: Any] = ["Label": agentLabel, "ProgramArguments": [exe.path, "--reached-desktop"],
                                    "RunAtLoad": true, "ProcessType": "Background", "LowPriorityIO": true]
        do {
            try fm.createDirectory(at: agentFile.deletingLastPathComponent(), withIntermediateDirectories: true)
            let d = try PropertyListSerialization.data(fromPropertyList: plist, format: .xml, options: 0)
            try d.write(to: agentFile, options: .atomic)
        } catch { return "could not write the login item: \(error.localizedDescription)" }
        save(["consent": true, "tries": 0, "armed": ISO8601DateFormatter().string(from: Date())])
        return nil
    }

    /// Takes the login item back out and forgets its state, so nothing of it is left running or on disk.
    static func remove() {
        _ = sh("/bin/launchctl", ["bootout", "gui/\(getuid())", agentFile.path])
        try? FileManager.default.removeItem(at: agentFile)
        try? FileManager.default.removeItem(at: stateFile)
    }

    /// What reached the desktop: the macOS build, the Mac's model and CPU, every display-class PCI device, whether
    /// Metal and the NVIDIA driver came up, 1401's version and OpenCore's, each display's mode, and the SHA-256 of
    /// every installed driver binary. Identities are stripped by `redact` before it leaves, exactly as Send logs does.
    /// The notes begin with a fixed tag so the catalog can find these uploads.
    static func summary() -> String {
        let os = sh("/usr/bin/sw_vers", ["-productVersion"]).trimmingCharacters(in: .whitespacesAndNewlines)
        let build = sh("/usr/bin/sw_vers", ["-buildVersion"]).trimmingCharacters(in: .whitespacesAndNewlines)
        let model = sysctl("hw.model")
        let cpu = sysctl("machdep.cpu.brand_string")
        let gpus = pciDisplays().map { "\($0["vendor"] ?? "?"):\($0["device"] ?? "?") \($0["model"] as? String ?? "")".trimmingCharacters(in: .whitespaces) }
        let metal = MTLCreateSystemDefaultDevice()
        let loaded = sh("/usr/bin/kmutil", ["showloaded", "--list-only"]).split(separator: "\n").contains { $0.contains("com.nullmoth") }
        let oc = sh("/usr/sbin/nvram", ["4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102:opencore-version"])
            .split(separator: "\t").last.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) } ?? "unknown"
        let app = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?"
        var s = "1401 reached the desktop\n\n"
        s += "macOS \(os) (\(build))\n"
        s += "model: \(model)\n"
        s += "cpu: \(cpu)\n"
        s += "display PCI: \(gpus.isEmpty ? "(none reported)" : gpus.joined(separator: "; "))\n"
        s += "Metal device: \(metal.map { "yes (\($0.name))" } ?? "no")\n"
        s += "NVIDIA driver loaded (com.nullmoth): \(loaded ? "yes" : "no")\n"
        s += "1401 Mac \(app)\n"
        s += "OpenCore: \(oc)\n"
        s += "display modes: \(displayModes())\n"
        for line in installedComponents() { s += line + "\n" }
        for line in loadedKextLines() { s += line + "\n" }
        s += "boot guard: " + bootGuardLine() + "\n"
        for line in featureLines() { s += line + "\n" }
        s += audioHardwareLine() + "\n"
        return s
    }

    /// Whether each part of the machine came up, one line per part: audio output, Wi-Fi, Bluetooth, the network the
    /// default route uses, keyboards / pointers / touchpads, a battery, and every non-Apple kext the kernel loaded. A
    /// first login that reached the desktop says nothing today about a silent speaker or a dead trackpad; these lines
    /// are what tells a working community driver from one that loaded and did nothing. Facts only: no network names,
    /// no addresses, no paired-device list, and no names of virtual or aggregate audio devices (users name those).
    static func featureLines() -> [String] {
        let profiler = sh("/usr/sbin/system_profiler", ["-json", "-detailLevel", "mini", "SPAudioDataType",
                                                        "SPBluetoothDataType", "SPAirPortDataType", "SPNetworkDataType",
                                                        "SPPowerDataType"])
        let hid = sh("/usr/sbin/ioreg", ["-r", "-c", "IOHIDDevice", "-d", "1", "-a"])
        let loaded = sh("/usr/bin/kmutil", ["showloaded", "--list-only"])
        let route = sh("/sbin/route", ["-n", "get", "default"])
        return featureLines(profiler: profiler, hid: hid, showloaded: loaded, defaultRoute: route)
    }

    static func featureLines(profiler: String, hid: String, showloaded: String, defaultRoute: String) -> [String] {
        var lines: [String] = []
        let sp = (try? JSONSerialization.jsonObject(with: Data(profiler.utf8))) as? [String: Any]
        func section(_ name: String) -> [[String: Any]]? { sp?[name] as? [[String: Any]] }

        if let audio = section("SPAudioDataType") {
            let items = audio.flatMap { ($0["_items"] as? [[String: Any]]) ?? [] }
            let outputs = items.filter { $0["coreaudio_device_output"] != nil
                && ($0["coreaudio_device_transport"] as? String) != "coreaudio_device_type_virtual"
                && ($0["coreaudio_device_transport"] as? String) != "coreaudio_device_type_aggregate" }
            let names = outputs.compactMap { ($0["_name"] as? String).map { String($0.prefix(40)) } }
            let hasDefault = items.contains { ($0["coreaudio_default_audio_output_device"] as? String) == "spaudio_yes" }
            lines.append(outputs.isEmpty ? "audio: NO output device"
                         : "audio: \(outputs.count) output device(s): \(Array(Set(names)).sorted().joined(separator: "; "))"
                           + (hasDefault ? "" : " (no default output)"))
        } else { lines.append("audio: unknown") }

        if let air = section("SPAirPortDataType") {
            let ifs = air.flatMap { ($0["spairport_airport_interfaces"] as? [[String: Any]]) ?? [] }
                .filter { $0["spairport_wireless_card_type"] != nil }
            lines.append(ifs.isEmpty ? "wifi: no Wi-Fi interface" : "wifi: " + ifs.map { i -> String in
                let status = ((i["spairport_status_information"] as? String) ?? "unknown").replacingOccurrences(of: "spairport_status_", with: "")
                let card = ((i["spairport_wireless_card_type"] as? String) ?? "").replacingOccurrences(of: "spairport_wireless_card_type_", with: "")
                return "\(status) (\(card))"
            }.joined(separator: "; "))
        } else { lines.append("wifi: unknown") }

        if let bt = section("SPBluetoothDataType") {
            let c = bt.compactMap { $0["controller_properties"] as? [String: Any] }.first
            if let c = c {
                let state = ((c["controller_state"] as? String) ?? "unknown").replacingOccurrences(of: "attrib_", with: "")
                lines.append("bluetooth: \(state) (\(c["controller_chipset"] as? String ?? "?"), \(c["controller_transport"] as? String ?? "?"))")
            } else { lines.append("bluetooth: NO controller") }
        } else { lines.append("bluetooth: unknown") }

        if let net = section("SPNetworkDataType") {
            let iface = defaultRoute.split(separator: "\n").compactMap { l -> String? in
                let t = l.trimmingCharacters(in: .whitespaces)
                return t.hasPrefix("interface:") ? String(t.dropFirst("interface:".count)).trimmingCharacters(in: .whitespaces) : nil
            }.first
            let kind = net.first { ($0["interface"] as? String) == iface }
                .map { (($0["hardware"] as? String) ?? ($0["type"] as? String) ?? "?") == "AirPort" ? "Wi-Fi" : (($0["hardware"] as? String) ?? ($0["type"] as? String) ?? "?") }
            let ethernet = net.filter { ($0["hardware"] as? String) == "Ethernet" && ($0["interface"] as? String)?.hasPrefix("en") == true }.count
            lines.append("network: default route via \(iface == nil ? "none" : (kind ?? "other")); \(ethernet) Ethernet interface(s)")
        } else { lines.append("network: unknown") }

        if let data = hid.data(using: .utf8), !hid.isEmpty,
           let devs = (try? PropertyListSerialization.propertyList(from: data, format: nil)) as? [[String: Any]] {
            func usage(_ d: [String: Any]) -> (Int, Int) { ((d["PrimaryUsagePage"] as? Int) ?? 0, (d["PrimaryUsage"] as? Int) ?? 0) }
            let keyboards = devs.filter { usage($0) == (1, 6) }.count
            let pointers = devs.filter { usage($0) == (1, 2) }.count
            let touchpads = devs.filter { usage($0) == (13, 5) }.count
            let transports = Dictionary(grouping: devs.compactMap { $0["Transport"] as? String }, by: { $0 }).mapValues { $0.count }
            lines.append("input: \(keyboards) keyboard(s), \(pointers) pointer(s), \(touchpads) touchpad(s)"
                         + (transports.isEmpty ? "" : " (" + transports.keys.sorted().map { "\($0) \(transports[$0]!)" }.joined(separator: ", ") + ")"))
        } else { lines.append("input: unknown") }

        if let power = section("SPPowerDataType") {
            lines.append("battery: " + (power.contains { $0["sppower_battery_charge_info"] != nil } ? "present" : "none"))
        } else { lines.append("battery: unknown") }

        // "... com.vendor.Name (1.2.3) UUID ..." per loaded kext; Apple's own are left out
        var third: [String] = []
        for line in showloaded.split(separator: "\n") {
            let words = line.split(separator: " ")
            for (i, w) in words.enumerated() where w.contains(".") && i + 1 < words.count && words[i + 1].hasPrefix("(") {
                if !w.hasPrefix("com.apple.") { third.append("\(w) \(words[i + 1])") }
                break
            }
        }
        lines.append("third-party kexts loaded: " + (third.isEmpty ? (showloaded.isEmpty ? "unknown" : "none") : third.sorted().joined(separator: ", ")))
        return lines
    }

    /// The audio hardware behind the "audio:" line: each HD-audio controller's PCI ID with the layout-id the boot setup
    /// gave it, and the codecs macOS attached to it. 2.5.3's reports showed one desktop in five with no output device
    /// and nothing that told a missing codec driver from a wrong layout-id or a codec AppleALC does not know.
    static func audioHardwareLine() -> String {
        audioHardwareLine(pci: sh("/usr/sbin/ioreg", ["-r", "-c", "IOPCIDevice", "-d", "1", "-a"]),
                          codecs: sh("/usr/sbin/ioreg", ["-r", "-c", "IOHDACodecDevice", "-d", "1", "-a"]))
    }

    static func audioHardwareLine(pci: String, codecs: String) -> String {
        func plist(_ s: String) -> [[String: Any]]? {
            guard !s.isEmpty, let d = s.data(using: .utf8) else { return nil }
            return (try? PropertyListSerialization.propertyList(from: d, format: nil)) as? [[String: Any]]
        }
        // PCI properties are little-endian data; layout-id may also arrive as a number from a device property
        func le(_ v: Any?) -> UInt32? {
            if let n = v as? Int { return UInt32(truncatingIfNeeded: n) }
            guard let d = v as? Data, !d.isEmpty else { return nil }
            return d.prefix(4).enumerated().reduce(UInt32(0)) { $0 | UInt32($1.element) << (8 * UInt32($1.offset)) }
        }
        guard let devs = plist(pci) else { return "audio hardware: unknown" }
        let hda = devs.filter { (le($0["class-code"]) ?? 0) >> 8 == 0x0403 }
        let ctl = hda.map { d -> String in
            let id = String(format: "%04X:%04X", le(d["vendor-id"]) ?? 0, le(d["device-id"]) ?? 0)
            return id + (le(d["layout-id"]).map { " (layout-id \($0))" } ?? " (no layout-id)")
        }
        let cod = (plist(codecs) ?? []).compactMap { le($0["IOHDACodecVendorID"]) }
            .map { String(format: "%04X:%04X", $0 >> 16, $0 & 0xffff) }
        return "audio hardware: " + (ctl.isEmpty ? "no HD-audio controller" : "HDA " + ctl.joined(separator: ", "))
            + "; codecs " + (cod.isEmpty ? "none attached" : Array(Set(cod)).sorted().joined(separator: ", "))
    }

    /// The boot guard's counters and the boot arguments, so a "driver loaded: no" says whether the driver switched
    /// itself off after starts that never lit a display, or was never asked to load (-nvoff, nv_disable).
    static func bootGuardLine() -> String {
        func nv(_ name: String) -> String {
            let out = sh("/usr/sbin/nvram", [name])
            let value = out.split(separator: "\t").dropFirst().joined(separator: "\t").trimmingCharacters(in: .whitespacesAndNewlines)
            return value.isEmpty ? "(unset)" : value
        }
        return "nv-starts \(nv("nullmoth-nv-starts")), nv-ok \(nv("nullmoth-nv-ok")), boot-args \(nv("boot-args"))"
    }

    /// What the kernel actually loaded, next to what is installed on disk. A kernel collection built by an earlier
    /// install can still hold the previous kext while the files on disk are the new ones; a machine then reports the
    /// new version while running the old driver. The report names both versions and says STALE when they differ.
    static let kextNames = ["NVRM", "NVRMFB", "NVAccel", "NVRMAGDC"]
    static func loadedKextLines() -> [String] {
        let shown = sh("/usr/bin/kmutil", ["showloaded", "--list-only"])
        return loadedKextLines(showloaded: shown) { name in
            let plist = "/Library/Extensions/\(name).kext/Contents/Info.plist"
            return (NSDictionary(contentsOfFile: plist)?["CFBundleVersion"] as? String)
        }
    }
    /// `kmutil showloaded --list-only` prints one line per kext: "... com.nullmoth.NVRM (2.3.4) <uuid> ...".
    static func loadedKextLines(showloaded: String, installedVersion: (String) -> String?) -> [String] {
        return kextNames.map { name in
            let id = "com.nullmoth.\(name) ("
            let loaded = showloaded.split(separator: "\n").lazy.compactMap { line -> String? in
                guard let open = line.range(of: id), let close = line[open.upperBound...].firstIndex(of: ")") else { return nil }
                return String(line[open.upperBound..<close])
            }.first
            let installed = installedVersion(name)
            var l = "loaded \(name): \(loaded ?? "(not loaded)")"
            if let i = installed { l += ", installed \(i)" }
            if let lv = loaded, let i = installed, lv != i { l += " STALE (the kernel runs a different build than the one on disk)" }
            return l
        }
    }

    /// The installed driver binaries by name, as the release gate counts them: a "reached desktop" on a macOS major is
    /// a boot receipt only for the exact kernel binaries that ran, so each line carries the SHA-256 of the installed
    /// file (or says it is not there), and the recorded driver version rides along. One line per component.
    static let components: [(String, String)] = [
        ("NVRM", "/Library/Extensions/NVRM.kext/Contents/MacOS/NVRM"),
        ("NVAccel", "/Library/Extensions/NVAccel.kext/Contents/MacOS/NVAccel"),
        ("NVRMFB", "/Library/Extensions/NVRMFB.kext/Contents/MacOS/NVRMFB"),
        ("NVRMAGDC", "/Library/Extensions/NVRMAGDC.kext/Contents/MacOS/NVRMAGDC"),
        ("NVMTLDriver", "/Library/GPUBundles/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver"),
    ]
    static func installedComponents() -> [String] {
        var lines = components.map { name, path in "installed \(name): \(sha256(URL(fileURLWithPath: path)) ?? "(not present)")" }
        let version = (try? String(contentsOfFile: "/Library/NullMoth/driver-version", encoding: .utf8))?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        lines.append("driver-version: \(version.isEmpty ? "(not present)" : String(version.prefix(40)))")
        return lines
    }

    /// Every active display's pixel size and refresh rate ("2560x1440 @ 165 Hz"), so lag reports can be split by
    /// refresh rate. A rate the display does not report (some TVs and virtual displays) is written as unknown.
    static func displayModes() -> String {
        var count: UInt32 = 0
        var ids = [CGDirectDisplayID](repeating: 0, count: 16)
        guard CGGetActiveDisplayList(UInt32(ids.count), &ids, &count) == .success, count > 0 else { return "(no active display)" }
        let modes = ids.prefix(Int(count)).compactMap { id -> String? in
            guard let m = CGDisplayCopyDisplayMode(id) else { return nil }
            let hz = m.refreshRate > 0 ? String(format: "%g Hz", m.refreshRate) : "unknown Hz"
            return "\(m.pixelWidth)x\(m.pixelHeight) @ \(hz)"
        }
        return modes.isEmpty ? "(no mode reported)" : modes.joined(separator: "; ")
    }

    /// Sends the one-time confirmation. Does nothing unless the user agreed and it has not already been sent. On a
    /// success it removes its own login item; on a failed send it counts the try and gives up (also removing the item)
    /// after a few starts, so a machine that can never reach the site is not left running it start after start.
    static func report() -> Int32 {
        var s = state()
        guard (s["consent"] as? Bool) == true, (s["sent"] as? Bool) != true else { return 0 }
        // A laptop whose NVIDIA card drives no display (the panel is on the integrated GPU) gets its Metal device from
        // the driver's headless check, 60 s after the accelerator starts. A login sooner than that read
        // "Metal device: no" on healthy GTX 1650 and RTX 4060 laptops, so the summary is taken once that check is due.
        let settle = 150 - ProcessInfo.processInfo.systemUptime
        if settle > 0 { Thread.sleep(forTimeInterval: settle) }
        let text = summary()
        let signs = failureSigns(text)
        if !signs.isEmpty { return advance(sent: reportFailure(text, signs: signs)) }
        let body = Data(redact(text).utf8)
        let sha = SHA256.hash(data: body).map { String(format: "%02x", $0) }.joined()
        var req = URLRequest(url: URL(string: "https://nullmothsystems.com/api/upload")!, timeoutInterval: 60)
        req.httpMethod = "POST"; req.httpBody = body
        req.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        req.setValue("reached-desktop.txt", forHTTPHeaderField: "X-File-Name")
        // the fixed "reached desktop" tag leads the notes so the catalog classifies these as a success, not a Mac log
        let notes = "reached desktop; 1401 Mac \(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?") (first login after install)"
        let meta = try! JSONSerialization.data(withJSONObject: ["consent": true, "notes": notes, "batch": newUploadBatch()])
        req.setValue(meta.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: ""), forHTTPHeaderField: "X-Meta")
        req.setValue(sha, forHTTPHeaderField: "X-Content-SHA256")
        let done = DispatchSemaphore(value: 0); let result = ReportUploadResult()
        let task = URLSession.shared.dataTask(with: req) { d, r, e in result.finish(data: d, response: r, error: e, sha256: sha); done.signal() }
        task.resume()
        let timedOut = done.wait(timeout: .now() + 90) == .timedOut
        if timedOut { task.cancel() }
        return advance(sent: result.take(timedOut: timedOut).0 != nil)
    }

    /// Why this login is not a clean success, from the summary's own lines: no Metal device, the driver not loaded, or
    /// an installed component missing. Empty means the driver came up and the one short text is enough. 12 of 129
    /// first-login reports on 2.3.x said "Metal device: no" or "driver loaded: no" and carried nothing else, so a plugin
    /// the system refused could not be told from a framebuffer that never came up.
    static func failureSigns(_ summary: String) -> [String] {
        var signs: [String] = []
        for line in summary.split(separator: "\n") {
            if line.hasPrefix("Metal device: no") { signs.append("no Metal device") }
            if line.hasPrefix("NVIDIA driver loaded (com.nullmoth): no") { signs.append("driver not loaded") }
            // the kernel still runs an older driver than the one on disk: a GTX 1650 SUPER reported the new app version
            // while an old NVRM ran with no framebuffer driver loaded at all, and its first-login report sent no logs
            if line.hasPrefix("loaded "), line.contains(" STALE ") {
                signs.append(String(line.dropFirst("loaded ".count).prefix { $0 != ":" }) + " stale")
            }
            if line.hasPrefix("installed "), line.hasSuffix(": (not present)") {
                signs.append(String(line.dropFirst("installed ".count).prefix { $0 != ":" }) + " missing")
            }
        }
        return signs
    }

    /// The files Send logs collects for the driver, as the first-login report attaches them when the driver did not
    /// come up. Everything else the full collection gathers (EFI partitions, panics, display and NPU logs) needs root
    /// and is not part of this report.
    static let driverFiles = ["driver-state.txt", "driver-kernel-log.txt", "driver-plugin-log.txt", "driver-crash-window.txt"]
    /// The collector, replaceable by a test: runs the driver scope of the collection into dir and returns its warnings.
    static var driverCollector: (URL) -> [String] = { dir in collectDriverLogs(into: dir) }

    /// The driver files for this report, collected only when the summary shows a failure; a clean summary collects
    /// nothing and returns no files. The WindowServer crash reports since boot ride along by their collected names.
    static func attachments(for summary: String, into dir: URL) -> (files: [URL], warnings: [String]) {
        guard !failureSigns(summary).isEmpty else { return ([], []) }
        let warnings = driverCollector(dir)
        let present = ((try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil)) ?? [])
            .filter { driverFiles.contains($0.lastPathComponent) || ($0.lastPathComponent.hasPrefix("macos-WindowServer") && $0.pathExtension == "ips") }
            .sorted { $0.lastPathComponent < $1.lastPathComponent }
        return (present, warnings)
    }

    /// A first login where the driver did not come up: the summary and the driver files go up as one batch through the
    /// same queue and redaction as Send logs (uploadReports). True when the summary itself reached the site.
    static func reportFailure(_ text: String, signs: [String]) -> Bool {
        let dir: URL, summaryFile: URL
        do {
            dir = try SavedReports.session(in: logs.appendingPathComponent("Reports"))
            summaryFile = try SavedReports.create(Data(text.utf8), in: dir, name: "reached-desktop.txt")
        } catch {
            print("reached-desktop report: could not save the report locally (\(error.localizedDescription))")
            return false
        }
        let gathered = attachments(for: text, into: dir)
        if !gathered.warnings.isEmpty {
            _ = try? SavedReports.create(Data(gathered.warnings.joined(separator: "\n").utf8), in: dir, name: "collection-errors.txt")
        }
        let app = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?"
        // the same fixed tag leads the notes; what did not come up follows it so the catalog can split these
        let notes = "reached desktop; 1401 Mac \(app) (first login after install; driver did not come up: \(signs.joined(separator: ", ")))"
        let outcome = uploadReports(files: [summaryFile] + gathered.files, pendingFiles: [], in: dir, notes: notes, batch: newUploadBatch())
        print("reached-desktop report: \(outcome.ids.count) of \(1 + gathered.files.count) files sent (\(signs.joined(separator: ", ")))")
        return outcome.acknowledgements.contains { $0["name"] == "reached-desktop.txt" }
    }

    /// The outcome of one send attempt. On a success it takes the login item back out and leaves nothing behind; on a
    /// failure it counts the try and, once a few starts have failed, gives up and takes the item out too, so a machine
    /// that can never reach the site is not left running it login after login. Kept apart from the transport so the
    /// once-and-remove and the bounded-retry behaviour can be exercised without the network.
    @discardableResult
    static func advance(sent: Bool) -> Int32 {
        if sent {
            remove()
            print("reached-desktop report: sent")
            return 0
        }
        let tries = (state()["tries"] as? Int ?? 0) + 1
        if tries >= maxTries {
            remove()
            print("reached-desktop report: gave up after \(tries) tries")
            return 1
        }
        var s = state(); s["tries"] = tries; save(s)
        print("reached-desktop report: not sent (try \(tries) of \(maxTries))")
        return 1
    }
}
