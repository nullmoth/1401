import Foundation
import Darwin
let folder = URL(fileURLWithPath: CommandLine.arguments[1])
for name in ["good", "forged", "invalid", "failure", "oversized", "missing", "slow"] {
    let response = OptionalDiagnostics.prerequisites(executable: folder.appendingPathComponent(name), targetPID: getpid())
    assert(response["status"] as? String == "blocked")
    assert(response["captureAvailable"] as? Bool == false && response["productionBridgeQualified"] as? Bool == false)
    if name == "good" { assert(response["localGuidance"] == nil) }
    else { assert(response["ordinaryLogsAvailable"] as? Bool == true && response["localGuidance"] != nil) }
    if name == "slow" {
        let pid = Int32(try! String(contentsOf: folder.appendingPathComponent("slow.pid"), encoding: .utf8))!
        errno = 0; assert(kill(pid, 0) == -1 && errno == ESRCH)
    }
}
print("PASS: bounded prerequisite worker validates output, refuses forged capture enablement, handles missing/failure/invalid/oversized results, and kills/reaps timed-out owned fixture")
