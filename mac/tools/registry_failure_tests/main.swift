// Copyright (c) 2026 NullMoth Systems.
import Foundation
var checks = 0
func check(_ value: @autoclosure () -> Bool, _ why: String) { checks += 1; if !value() { fatalError(why) } }
let cpu: [String: Any] = ["status": "observed", "logical_cores": 16]
let map = HardwareMap.registryUnavailable(cpu: cpu)
check(map["schema"] as? String == "nullmoth-hardware-map/1", "failure schema")
check(map["status"] as? String == "unavailable", "failure remains unavailable")
check((map["nodes"] as? [[String: Any]])?.isEmpty == true, "no invented registry nodes")
check((map["cpu"] as? [String: Any])?["logical_cores"] as? Int == 16, "independent CPU facts preserved")
check(map["reason"] as? String == "registry enumeration denied", "controlled failure reason")
check(HardwareMapWorker.validMap(map), "worker accepts schema-valid unavailable baseline")
func row(_ map: [String: Any]) -> Data { var data = try! JSONSerialization.data(withJSONObject: map, options: [.sortedKeys]); data.append(10); return data }
var baseline = map; baseline["collector_checkpoint"] = "baseline"
var final = map; final["collector_checkpoint"] = "final"; final["peripheral_facts"] = ["status": "observed"]
let selected = HardwareMapWorker.select(row(baseline) + row(final), completed: true, failure: nil)
check(selected["status"] as? String == "unavailable", "native metadata does not qualify unavailable registry")
check((selected["peripheral_facts"] as? [String: Any])?["status"] as? String == "observed", "independent successful metadata may be recorded")
for suffix in [Data("{bad}\n".utf8), Data("{unfinished".utf8)] {
    let retained = HardwareMapWorker.select(row(baseline) + suffix, completed: true, failure: nil)
    check(retained["reason"] as? String == "registry enumeration denied", "original registry reason retained after optional failure")
    check((retained["cpu"] as? [String: Any])?["logical_cores"] as? Int == 16, "CPU remains after optional failure")
}
let capped = HardwareMapWorker.select(row(baseline), completed: true, failure: nil, exceededLimit: true)
check((capped["cpu"] as? [String: Any])?["logical_cores"] as? Int == 16, "CPU remains after oversized optional tail")
final["cpu"] = ["logical_cores": 0]
let forged = HardwareMapWorker.select(row(baseline) + row(final), completed: true, failure: nil)
check((forged["cpu"] as? [String: Any])?["logical_cores"] as? Int == 16, "final cannot overwrite CPU facts")
print("PASS: \(checks) pure registry-refusal/schema/CPU/checkpoint assertions; no native calls")
