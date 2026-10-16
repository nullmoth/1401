import Foundation
import Darwin
import CoreFoundation

// This release has no independently verified privileged diagnostics installer.
// Neither a mutable app resource nor a matching receipt can enable authority.
enum OptionalDiagnostics {
    static let productionBridgeQualified = false
    static let schema = "nullmoth-optional-diagnostics/1"
    static let missingBridge = "Optional capture is unavailable in this version. Send logs still collects hardware, kernel and panic evidence. No security settings have changed."

    static func prerequisites(executable: URL, targetPID: Int32) -> [String: Any] {
        let fm = FileManager.default
        let dir = fm.temporaryDirectory.appendingPathComponent("1401-diagnostics-" + UUID().uuidString)
        do { try fm.createDirectory(at: dir, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700]) }
        catch { return blocked("Read-only prerequisite output is unavailable.") }
        defer { try? fm.removeItem(at: dir) }
        let output = dir.appendingPathComponent("preflight.json")
        guard fm.createFile(atPath: output.path, contents: nil, attributes: [.posixPermissions: 0o600]),
              let handle = try? FileHandle(forWritingTo: output) else { return blocked("Read-only prerequisite output is unavailable.") }
        defer { try? handle.close() }
        let child = Process(); child.executableURL = executable; child.arguments = [String(targetPID)]
        child.environment = ["PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"]
        child.standardOutput = handle; child.standardError = FileHandle.nullDevice; child.standardInput = FileHandle.nullDevice
        let done = DispatchSemaphore(value: 0); child.terminationHandler = { _ in done.signal() }
        do { try child.run() } catch { return blocked("The read-only prerequisite checker is missing or could not start.") }
        if done.wait(timeout: .now() + 8) == .timedOut {
            if child.isRunning { kill(child.processIdentifier, SIGKILL) }
            _ = done.wait(timeout: .now() + 0.5)
            return blocked("The read-only prerequisite check timed out. Other logs are retained.")
        }
        guard child.terminationReason == .exit, child.terminationStatus == 0,
              let read = try? FileHandle(forReadingFrom: output) else { return blocked("The read-only prerequisite checker failed. Other logs are retained.") }
        defer { try? read.close() }
        guard let data = try? read.read(upToCount: 32769), data.count <= 32768,
              let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              object["schema"] as? String == schema, object["status"] as? String == "blocked",
              let capture = object["captureAvailable"] as? NSNumber, CFGetTypeID(capture) == CFBooleanGetTypeID(), !capture.boolValue,
              let qualified = object["productionBridgeQualified"] as? NSNumber, CFGetTypeID(qualified) == CFBooleanGetTypeID(), !qualified.boolValue else {
            return blocked("The read-only prerequisite response was invalid. Capture remains unavailable.")
        }
        return object
    }
    static func blocked(_ reason: String) -> [String: Any] {
        ["schema": schema, "status": "blocked", "captureAvailable": false,
         "productionBridgeQualified": false, "ordinaryLogsAvailable": true, "localGuidance": reason]
    }
    static func guidance(_ response: [String: Any]) -> String {
        var lines = [missingBridge]
        if let local = response["localGuidance"] as? String { lines.append(local) }
        if let tool = response["tool"] as? [String: Any] { lines.append((tool["available"] as? Bool == true) ? "The system's DTrace tool is available." : "The system's DTrace tool is unavailable or could not be verified.") }
        if let csr = response["csr"] as? [String: Any] {
            lines.append((csr["activeBitSet"] as? Bool == true && csr["effectivePermissionAllowed"] as? Bool == true)
                ? "System tracing permission is available."
                : "System tracing permission is unavailable. This version cannot capture even if permission changes.")
        }
        if let security = response["security"] as? [String: Any], let reasons = security["reasons"] as? [String] {
            let incompatible: Set<String> = ["security_policy_incompatible_with_authenticated_capture", "boot_security_policy_incompatible", "system_library_validation_disabled"]
            let unknown: Set<String> = ["hardened_runtime_unavailable", "sip_state_unknown", "boot_security_policy_unknown", "library_validation_policy_unknown"]
            if !incompatible.isDisjoint(with: reasons) { lines.append("Current system security settings are incompatible with optional capture.") }
            if !unknown.isDisjoint(with: reasons) { lines.append("Some system security prerequisites could not be verified.") }
        }
        lines.append("This availability check starts no trace. Use Send logs to share ordinary diagnostics.")
        return lines.joined(separator: "\n\n")
    }
}

enum DiagnosticReceiptError: Error { case invalid, consentRequired, unsafeFile, tooLarge }

// Imported receipts are data, never authority. Only a small validated summary
// enters Send logs; identities, paths, tokens, right definitions and raw text do not.
enum DiagnosticReceipts {
    static let maximumBytes = 65536
    static let profile = "cpu-samples-10hz-v1"
    static let componentNames: Set<String> = ["local_diagnostics_helper", "gpu_plugin", "translator_bundle_sibling", "translator_runtime_fallback", "vulkan_loader", "vulkan_backend", "NVRM", "NVAccel", "NVRMFB", "NVRMAGDC"]
    static func dict(_ value: Any?, keys: Set<String>) throws -> [String: Any] {
        guard let d = value as? [String: Any], Set(d.keys).isSubset(of: keys) else { throw DiagnosticReceiptError.invalid }; return d
    }
    static func bool(_ value: Any?) throws -> Bool {
        guard let n = value as? NSNumber, CFGetTypeID(n) == CFBooleanGetTypeID() else { throw DiagnosticReceiptError.invalid }; return n.boolValue
    }
    static func number(_ value: Any?, minimum: Int64 = 0, maximum: Int64 = Int64.max) throws -> Int64 {
        guard let n = value as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID(), n.doubleValue.isFinite,
              n.doubleValue.rounded(.towardZero) == n.doubleValue, n.doubleValue >= Double(minimum), n.doubleValue <= Double(maximum) else { throw DiagnosticReceiptError.invalid }; return n.int64Value
    }
    static func text(_ value: Any?, pattern: String) throws -> String {
        guard let t = value as? String, t.utf8.count <= 512, t.range(of: pattern, options: .regularExpression) != nil else { throw DiagnosticReceiptError.invalid }; return t
    }
    static func hash(_ value: Any?) throws -> String { try text(value, pattern: #"^(?:[0-9a-f]{64}|unavailable)$"#) }
    static func sanitized(_ data: Data, sendLogsConsent: Bool) throws -> Data {
        guard sendLogsConsent else { throw DiagnosticReceiptError.consentRequired }
        var summary = try validatedSummary(data)
        summary["sendLogsConsent"] = true
        return try JSONSerialization.data(withJSONObject: summary, options: [.sortedKeys])
    }
    static func validatedSummary(_ data: Data) throws -> [String: Any] {
        guard !data.isEmpty, data.count <= maximumBytes else { throw DiagnosticReceiptError.tooLarge }
        let root = try dict(JSONSerialization.jsonObject(with: data), keys: ["schemaVersion", "sessionID", "uploadConsent", "profileID", "durationSeconds", "result"])
        guard try number(root["schemaVersion"], maximum: 1) == 1, try bool(root["uploadConsent"]) else { throw DiagnosticReceiptError.consentRequired }
        guard let session = root["sessionID"] as? String, UUID(uuidString: session) != nil,
              root["profileID"] as? String == profile else { throw DiagnosticReceiptError.invalid }
        let duration = try number(root["durationSeconds"], maximum: 15)
        guard [5, 10, 15].contains(duration) else { throw DiagnosticReceiptError.invalid }
        let result = try dict(root["result"], keys: ["status", "reason", "receipt", "trace", "traceAttempted", "traceEnabled", "securitySettingsChanged"])
        let status = try text(result["status"], pattern: #"^(session_finished|blocked|stopped)$"#)
        var output: [String: Any] = ["schema": "nullmoth-diagnostic-upload/1", "qualification": "imported_receipt_not_independently_authenticated", "profileID": profile, "durationSeconds": duration, "sessionUploadConsent": true, "status": status]
        if status != "session_finished" {
            let reasons: Set<String> = ["local_cancelled_or_timed_out", "explicit_local_consent_required", "administrator_authorization_declined_or_unavailable", "session_expired", "protected_target_refused", "required_probe_unavailable", "target_unavailable_or_changed", "csr_dtrace_permission_required", "system_dtrace_unavailable", "administrator_authorization_required", "cancelled"]
            guard let reason = result["reason"] as? String, reasons.contains(reason), Set(result.keys).isSubset(of: ["status", "reason", "traceEnabled"]) else { throw DiagnosticReceiptError.invalid }
            if let enabled = result["traceEnabled"] { guard try !bool(enabled) else { throw DiagnosticReceiptError.invalid } }
            output["reason"] = reason
        } else {
            guard result["reason"] == nil, try bool(result["traceAttempted"]), try !bool(result["securitySettingsChanged"]) else { throw DiagnosticReceiptError.invalid }
            output["traceEnabled"] = try bool(result["traceEnabled"])
            let trace = try dict(result["trace"], keys: ["status", "complete", "samples", "errors", "dataLossOrToolFailure", "started", "ended", "transportStatus", "exitCode", "capturedBytes", "childReaped"])
            var cleanTrace: [String: Any] = [:]
            cleanTrace["status"] = try text(trace["status"], pattern: #"^(captured|inconclusive_no_samples|trace_incomplete)$"#)
            cleanTrace["transportStatus"] = try text(trace["transportStatus"], pattern: #"^(completed|process_failed|cancelled|target_changed|timeout|output_limit|read_failure|wait_failure|pipe_cleanup_timeout|launch_failure|pipe_failure)$"#)
            for key in ["complete", "dataLossOrToolFailure", "started", "ended", "childReaped"] { cleanTrace[key] = try bool(trace[key]) }
            for key in ["samples", "errors"] { cleanTrace[key] = try number(trace[key], maximum: 100000) }
            cleanTrace["exitCode"] = try number(trace["exitCode"], minimum: -1, maximum: 255)
            cleanTrace["capturedBytes"] = try number(trace["capturedBytes"], maximum: 65536)
            guard (try bool(result["traceEnabled"])) == (try bool(trace["started"])) else { throw DiagnosticReceiptError.invalid }
            if try bool(trace["complete"]) {
                guard try bool(trace["started"]), try bool(trace["ended"]), try bool(trace["childReaped"]), try !bool(trace["dataLossOrToolFailure"]), try number(trace["errors"]) == 0, trace["transportStatus"] as? String == "completed", try number(trace["exitCode"]) == 0 else { throw DiagnosticReceiptError.invalid }
                let samples = try number(trace["samples"])
                guard (trace["status"] as? String == "captured" && samples > 0) || (trace["status"] as? String == "inconclusive_no_samples" && samples == 0) else { throw DiagnosticReceiptError.invalid }
            } else {
                guard trace["status"] as? String == "trace_incomplete" else { throw DiagnosticReceiptError.invalid }
            }
            output["trace"] = cleanTrace
            output["configuration"] = try configuration(result["receipt"])
        }
        return output
    }
    static func configuration(_ value: Any?) throws -> [String: Any] {
        let receipt = try dict(value, keys: ["schemaVersion", "tool", "csr", "administrator", "target", "providers", "providerInventoryStatus", "system", "PCIdevices", "components", "limitations"])
        guard try number(receipt["schemaVersion"], maximum: 1) == 1 else { throw DiagnosticReceiptError.invalid }
        _ = try bool(receipt["administrator"])
        let tool = try dict(receipt["tool"], keys: ["path", "available", "signatureStatus", "AppleSignatureVerified", "signatureNetworkAccess", "SHA256"])
        guard tool["path"] as? String == "/usr/sbin/dtrace", try !bool(tool["signatureNetworkAccess"]) else { throw DiagnosticReceiptError.invalid }
        for key in ["available", "AppleSignatureVerified"] { _ = try bool(tool[key]) }; _ = try number(tool["signatureStatus"], minimum: -100000, maximum: 100000)
        let csr = try dict(receipt["csr"], keys: ["known", "activeConfig", "requiredFlag", "activeBitSet", "effectivePermissionAllowed"])
        for key in ["known", "activeBitSet", "effectivePermissionAllowed"] { _ = try bool(csr[key]) }
        let csrConfig = try number(csr["activeConfig"], maximum: 0xffffffff); guard try number(csr["requiredFlag"]) == 32 else { throw DiagnosticReceiptError.invalid }
        let target = try dict(receipt["target"], keys: ["known", "pid", "ownedByClient", "systemProcess", "startSeconds", "startMicroseconds", "codeStatus", "executableSHA256", "fileDevice", "fileInode", "fileBytes", "fileModifiedSeconds", "fileModifiedNanoseconds"])
        let known = try bool(target["known"])
        if known { for key in ["ownedByClient", "systemProcess"] { _ = try bool(target[key]) }; for key in ["pid", "startSeconds", "startMicroseconds", "codeStatus", "fileDevice", "fileInode", "fileBytes", "fileModifiedSeconds", "fileModifiedNanoseconds"] { _ = try number(target[key]) }; _ = try hash(target["executableSHA256"]) }
        else { guard target.count == 1 else { throw DiagnosticReceiptError.invalid } }
        let providers = try dict(receipt["providers"], keys: ["profile-10", "tick-1sec", "BEGIN", "END", "ERROR"])
        for v in providers.values { _ = try bool(v) }
        _ = try text(receipt["providerInventoryStatus"], pattern: #"^(not_checked_missing_prerequisites|completed|process_failed|timeout|output_limit|launch_failure|pipe_failure|read_failure|wait_failure|pipe_cleanup_timeout)$"#)
        let system = try dict(receipt["system"], keys: ["osVersion", "osBuild", "kernelRelease", "modelReportedByOS", "logicalCPUs", "startupVolumeFSID", "bootSessionUUID"])
        let os = try text(system["osVersion"], pattern: #"^(?:[0-9]{1,2}\.[0-9]{1,2}(?:\.[0-9]{1,2})?|unavailable)$"#)
        let build = try text(system["osBuild"], pattern: #"^(?:[0-9]{2}[A-Z][0-9]{1,6}[a-z]?|unavailable)$"#)
        _ = try text(system["kernelRelease"], pattern: #"^(?:[0-9]{1,2}(?:\.[0-9]{1,2}){1,2}|unavailable)$"#)
        _ = try text(system["modelReportedByOS"], pattern: #"^[A-Za-z0-9,.-]{1,64}$"#)
        let cpus = try number(system["logicalCPUs"], maximum: 4096)
        guard let fsid = system["startupVolumeFSID"] as? [Any], fsid.count == 0 || fsid.count == 2 else { throw DiagnosticReceiptError.invalid }
        for n in fsid { _ = try number(n, minimum: Int64(Int32.min), maximum: Int64(Int32.max)) }
        guard let uuid = system["bootSessionUUID"] as? String, uuid == "unavailable" || UUID(uuidString: uuid) != nil else { throw DiagnosticReceiptError.invalid }
        guard let devices = receipt["PCIdevices"] as? [[String: Any]], devices.count <= 64 else { throw DiagnosticReceiptError.invalid }
        var pci: [[String: Int64]] = []
        for device in devices {
            let d = try dict(device, keys: ["vendor-id", "device-id", "subsystem-vendor-id", "subsystem-id", "class-code", "revision-id", "registryEntryID"])
            var clean: [String: Int64] = [:]
            for (key, value) in d { let n = try number(value, maximum: key == "registryEntryID" ? Int64.max : 0xffffffff); if key != "registryEntryID" { clean[key] = n } }; pci.append(clean)
        }
        guard let components = receipt["components"] as? [[String: Any]], components.count <= 10 else { throw DiagnosticReceiptError.invalid }
        var seen = Set<String>(), cleanComponents: [[String: Any]] = []
        for c in components {
            let d = try dict(c, keys: ["component", "present", "SHA256", "loadedState"])
            guard let name = d["component"] as? String, componentNames.contains(name), seen.insert(name).inserted else { throw DiagnosticReceiptError.invalid }
            if let loaded = d["loadedState"] { guard loaded as? String == "not_observed" else { throw DiagnosticReceiptError.invalid } }
            cleanComponents.append(["component": name, "present": try bool(d["present"]), "SHA256": try hash(d["SHA256"])])
        }
        let knownLimitations: Set<String> = ["CPU scheduling counts only; no GPU commands, kernel function bodies, stack addresses, memory or document contents are collected.", "Some processes deny tracing independently of SIP; zero samples are inconclusive."]
        guard let limitations = receipt["limitations"] as? [String], limitations.count <= 2, Set(limitations).isSubset(of: knownLimitations) else { throw DiagnosticReceiptError.invalid }
        return ["osVersion": os, "osBuild": build, "logicalCPUs": cpus, "csrActiveConfig": csrConfig, "dtraceSHA256": try hash(tool["SHA256"]), "PCIdevices": pci, "components": cleanComponents]
    }
    static func privateFile(_ url: URL) throws -> Data {
        guard url.isFileURL, url.standardizedFileURL.path == url.resolvingSymlinksInPath().standardizedFileURL.path else { throw DiagnosticReceiptError.unsafeFile }
        var parent = stat(); let directory = url.deletingLastPathComponent()
        guard lstat(directory.path, &parent) == 0, (parent.st_mode & S_IFMT) == S_IFDIR, parent.st_uid == getuid(), parent.st_mode & 0o022 == 0 else { throw DiagnosticReceiptError.unsafeFile }
        let fd = open(url.path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK); guard fd >= 0 else { throw DiagnosticReceiptError.unsafeFile }; defer { close(fd) }
        var before = stat(); guard fstat(fd, &before) == 0, (before.st_mode & S_IFMT) == S_IFREG, before.st_uid == getuid(), before.st_nlink == 1, before.st_mode & 0o777 == 0o600 else { throw DiagnosticReceiptError.unsafeFile }
        guard before.st_size > 0, before.st_size <= maximumBytes else { throw DiagnosticReceiptError.tooLarge }
        var data = Data(count: Int(before.st_size)); let amount = data.withUnsafeMutableBytes { read(fd, $0.baseAddress, $0.count) }
        var after = stat(); guard amount == data.count, fstat(fd, &after) == 0, before.st_size == after.st_size, before.st_mtimespec.tv_sec == after.st_mtimespec.tv_sec, before.st_mtimespec.tv_nsec == after.st_mtimespec.tv_nsec else { throw DiagnosticReceiptError.unsafeFile }; return data
    }
    static func stage(_ data: Data, directory: URL) throws {
        guard data.count <= maximumBytes else { throw DiagnosticReceiptError.tooLarge }
        let fm = FileManager.default
        if !fm.fileExists(atPath: directory.path) { try fm.createDirectory(at: directory, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700]) }
        var s = stat(); guard directory.standardizedFileURL.path == directory.resolvingSymlinksInPath().standardizedFileURL.path,
            lstat(directory.path, &s) == 0, (s.st_mode & S_IFMT) == S_IFDIR, s.st_uid == getuid(), s.st_mode & 0o777 == 0o700 else { throw DiagnosticReceiptError.unsafeFile }
        let temporary = directory.appendingPathComponent(".receipt-" + UUID().uuidString)
        let fd = open(temporary.path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o600)
        guard fd >= 0 else { throw DiagnosticReceiptError.unsafeFile }
        defer { close(fd); unlink(temporary.path) }
        let amount = data.withUnsafeBytes { write(fd, $0.baseAddress, $0.count) }
        guard amount == data.count, fsync(fd) == 0, rename(temporary.path, directory.appendingPathComponent("diagnostic-receipt.json").path) == 0 else { throw DiagnosticReceiptError.unsafeFile }
    }
}
