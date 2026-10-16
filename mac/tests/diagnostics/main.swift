import Foundation
import Darwin

func encoded(_ object: [String: Any]) -> Data { try! JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]) }
func refused(_ block: () throws -> Void) { do { try block(); fatalError("Refusal required") } catch {} }
let digest = String(repeating: "a", count: 64)
let receipt: [String: Any] = [
    "schemaVersion": 1,
    "tool": ["path": "/usr/sbin/dtrace", "available": true, "signatureStatus": 0, "AppleSignatureVerified": true, "signatureNetworkAccess": false, "SHA256": digest],
    "csr": ["known": true, "activeConfig": 35, "requiredFlag": 32, "activeBitSet": true, "effectivePermissionAllowed": true],
    "administrator": true,
    "target": ["known": true, "pid": 234, "ownedByClient": true, "systemProcess": false, "startSeconds": 345, "startMicroseconds": 42, "codeStatus": 65537, "executableSHA256": digest, "fileDevice": 12, "fileInode": 56, "fileBytes": 678, "fileModifiedSeconds": 111, "fileModifiedNanoseconds": 2],
    "providers": ["profile-10": true, "tick-1sec": true, "BEGIN": true, "END": true, "ERROR": true],
    "providerInventoryStatus": "completed",
    "system": ["osVersion": "15.7.1", "osBuild": "24G231", "kernelRelease": "24.6.0", "modelReportedByOS": "MacPro7,1", "logicalCPUs": 16, "startupVolumeFSID": [-123, 42], "bootSessionUUID": "ABABABAB-ABAB-ABAB-ABAB-ABABABABABAB"],
    "PCIdevices": [["vendor-id": 4318, "device-id": 11008, "registryEntryID": 98765]],
    "components": [["component": "gpu_plugin", "present": true, "SHA256": digest, "loadedState": "not_observed"]],
    "limitations": ["CPU scheduling counts only; no GPU commands, kernel function bodies, stack addresses, memory or document contents are collected.", "Some processes deny tracing independently of SIP; zero samples are inconclusive."]
]
let trace: [String: Any] = ["status": "captured", "complete": true, "samples": 17, "errors": 0, "dataLossOrToolFailure": false, "started": true, "ended": true, "transportStatus": "completed", "exitCode": 0, "capturedBytes": 128, "childReaped": true]
let result: [String: Any] = ["status": "session_finished", "receipt": receipt, "trace": trace, "traceAttempted": true, "traceEnabled": true, "securitySettingsChanged": false]
let session = "CDCDCDCD-CDCD-CDCD-CDCD-CDCDCDCDCDCD"
let original: [String: Any] = ["schemaVersion": 1, "sessionID": session, "uploadConsent": true, "profileID": DiagnosticReceipts.profile, "durationSeconds": 10, "result": result]
let data = encoded(original)
let safe = try! DiagnosticReceipts.sanitized(data, sendLogsConsent: true)
let safeText = String(decoding: safe, as: UTF8.self)
assert(!safeText.contains(session) && !safeText.contains("ABABABAB") && !safeText.contains("pid") && !safeText.contains("fileInode") && !safeText.contains("registryEntryID") && !safeText.contains("MacPro7,1"))
assert(safeText.contains("gpu_plugin") && safeText.contains("4318") && safeText.contains("17"))
let preview = try! DiagnosticReceipts.validatedSummary(data)
assert(preview["sendLogsConsent"] == nil)
refused { _ = try DiagnosticReceipts.sanitized(data, sendLogsConsent: false) }
for (key, bad) in [("uploadConsent", false as Any), ("uploadConsent", 1 as Any), ("schemaVersion", true as Any), ("durationSeconds", 16 as Any), ("profileID", "fbt-all" as Any), ("sessionID", "account-name" as Any), ("externalForm", "token" as Any)] {
    var changed = original; changed[key] = bad; refused { _ = try DiagnosticReceipts.sanitized(encoded(changed), sendLogsConsent: true) }
}
for (key, bad) in [("authorization", "secret" as Any), ("rightDefinition", ["class": "allow"] as Any), ("securitySettingsChanged", true as Any), ("traceEnabled", false as Any)] {
    var r = result; r[key] = bad; var changed = original; changed["result"] = r; refused { _ = try DiagnosticReceipts.sanitized(encoded(changed), sendLogsConsent: true) }
}
for path in ["target", "tool", "system", "csr"] {
    var r = receipt; var nested = r[path] as! [String: Any]; nested["externalForm"] = "secret"; r[path] = nested
    var outcome = result; outcome["receipt"] = r; var changed = original; changed["result"] = outcome
    refused { _ = try DiagnosticReceipts.sanitized(encoded(changed), sendLogsConsent: true) }
}
for key in ["samples", "errors", "capturedBytes"] {
    var t = trace; t[key] = key == "capturedBytes" ? 65537 : 100001
    var outcome = result; outcome["trace"] = t; var changed = original; changed["result"] = outcome
    refused { _ = try DiagnosticReceipts.sanitized(encoded(changed), sendLogsConsent: true) }
}
var incomplete = trace; incomplete["status"] = "trace_incomplete"; incomplete["complete"] = false; incomplete["transportStatus"] = "timeout"; incomplete["ended"] = false
var partialResult = result; partialResult["trace"] = incomplete; var partial = original; partial["result"] = partialResult
assert((try! DiagnosticReceipts.validatedSummary(encoded(partial)))["status"] as? String == "session_finished")
var blocked = original; blocked["result"] = ["status": "blocked", "reason": "protected_target_refused", "traceEnabled": false]
assert((try! DiagnosticReceipts.validatedSummary(encoded(blocked)))["reason"] as? String == "protected_target_refused")
refused { _ = try DiagnosticReceipts.sanitized(Data(repeating: 65, count: 65537), sendLogsConsent: true) }
refused { _ = try DiagnosticReceipts.sanitized(Data("{bad}".utf8), sendLogsConsent: true) }
let fm = FileManager.default
let root = fm.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent("nd-receipt-test-" + UUID().uuidString)
try! fm.createDirectory(at: root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
defer { try? fm.removeItem(at: root) }
let input = root.appendingPathComponent("input.json"); try! data.write(to: input); chmod(input.path, 0o600)
assert(try! DiagnosticReceipts.privateFile(input) == data)
chmod(input.path, 0o644); refused { _ = try DiagnosticReceipts.privateFile(input) }; chmod(input.path, 0o600)
let symlink = root.appendingPathComponent("alias.json"); assert(Darwin.symlink(input.path, symlink.path) == 0); refused { _ = try DiagnosticReceipts.privateFile(symlink) }
let hard = root.appendingPathComponent("hard.json"); assert(link(input.path, hard.path) == 0); refused { _ = try DiagnosticReceipts.privateFile(input) }; unlink(hard.path)
let fifo = root.appendingPathComponent("fifo.json"); assert(mkfifo(fifo.path, 0o600) == 0); refused { _ = try DiagnosticReceipts.privateFile(fifo) }
let stage = root.appendingPathComponent("stage"); try! DiagnosticReceipts.stage(data, directory: stage)
assert(try! DiagnosticReceipts.privateFile(stage.appendingPathComponent("diagnostic-receipt.json")) == data)
chmod(stage.path, 0o755); refused { try DiagnosticReceipts.stage(data, directory: stage) }; chmod(stage.path, 0o700)
let unsafeParent = root.appendingPathComponent("unsafe"); try! fm.createDirectory(at: unsafeParent, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o777]); chmod(unsafeParent.path, 0o777)
let unsafe = unsafeParent.appendingPathComponent("receipt.json"); try! data.write(to: unsafe); chmod(unsafe.path, 0o600); refused { _ = try DiagnosticReceipts.privateFile(unsafe) }
assert(!OptionalDiagnostics.productionBridgeQualified)
let guidance = OptionalDiagnostics.guidance(["tool": ["available": false], "csr": ["activeBitSet": false, "effectivePermissionAllowed": false], "security": ["reasons": ["boot_security_policy_incompatible"]]])
assert(guidance.contains("unavailable in this version") && guidance.contains("tracing permission is unavailable") && guidance.contains("security settings are incompatible") && guidance.contains("starts no trace") && guidance.contains("No security settings have changed"))
for jargon in ["mutable resources", "privileged installer", "kernel integrity", "control-port", "CSR 0x20"] { assert(!guidance.contains(jargon)) }
print("PASS: separate session/send consent, strict receipt schema/types/limits, nested credential refusal, incomplete outcomes, privacy projection, private filesystem/symlink/hardlink/FIFO guards, blocked authority guidance; no trace/admin/network")
