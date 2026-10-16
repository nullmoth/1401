import Foundation

func require(_ passed: Bool, _ text: String) {
    if !passed { fatalError(text) }
}

let values: [String: Any] = [
    "vendor-id": Data([0xde, 0x10, 0, 0]), "device-id": Data([0x04, 0x22, 0, 0]),
    "subsystem-id": Data([0xaf, 0x87, 0, 0]), "class-code": Data([0, 0, 3, 0]),
    "VendorID": 0x06cb, "ProductID": 0x1234, "PrimaryUsagePage": 1, "PrimaryUsage": 2,
    "IOHDACodecVendorID": 0x10ec0295,
    "compatible": Data("PNP0C50\u{0}PRIVATE_SERIAL_1234\u{0}".utf8),
    "SerialNumber": "PRIVATE_SERIAL_1234", "USB Serial Number": "PRIVATE_SERIAL_1234",
    "MACAddress": Data([1, 2, 3, 4, 5, 6]), "Product": "PRIVATE_ENDPOINT",
    "HIDInput": "PRIVATE_INPUT", "Path": "/private/PRIVATE_ACCOUNT", "VendorIDBad": true
]
let observed = HardwareMap.facts(values)
require(observed["pci_vendor"] as? UInt64 == 0x10de, "PCI byte order")
require(observed["pci_class"] as? UInt64 == 0x030000, "PCI class")
require(observed["audio_codec_vendor_device"] as? UInt64 == 0x10ec0295, "codec evidence")
require(observed["acpi_ids"] as? [String] == ["PNP0C50"], "ACPI whitelist")
require(HardwareMap.integer(true, maximum: 0xffff) == nil, "boolean must not become an ID")
require(HardwareMap.integer(-1, maximum: 0xffff) == nil, "negative ID")
require(HardwareMap.integer(1.5, maximum: 0xffff) == nil, "fractional ID")
require(HardwareMap.integer(Data(repeating: 255, count: 9), maximum: UInt64.max) == nil, "oversized binary")
require(HardwareMap.integer(Data([0, 0, 1]), maximum: 0xffff) == nil, "overflow")
require(HardwareMap.integer(Data([1]), maximum: 0xffff) == 1, "unaligned short binary")
let serialized = String(decoding: try JSONSerialization.data(withJSONObject: observed), as: UTF8.self)
require(!serialized.contains("PRIVATE"), "privacy whitelist")
let paired = HardwareMap.localNodes([
    100: ["driver_class": "IOPCIBridge", "observed": ["pci_vendor": 0x8086]],
    101: ["driver_class": "IOPCIDevice", "observed": ["pci_vendor": 0x10de, "pci_device": 0x2204], "parent_registry_id": UInt64(100)],
    102: ["driver_class": "IOPCIDevice", "observed": ["pci_vendor": 0x10de, "pci_device": 0x2204], "parent_registry_id": UInt64(100)]
])
require(paired.count == 3 && Set(paired.compactMap { $0["id"] as? String }).count == 3, "identical adapters stay distinct")
require(paired[1]["parent"] as? String == "n0" && paired[2]["parent"] as? String == "n0", "parent graph")
require(paired.allSatisfy { $0["parent_registry_id"] == nil }, "registry IDs are report local")
let isolated = HardwareMap.localNodes([101: ["parent_registry_id": UInt64(100)]])
require(isolated[0]["parent"] == nil && isolated[0]["parent_status"] != nil, "unobserved parent explicit")
let bounded = HardwareMap.collect(maximumNodes: 1, maximumVisited: 1, seconds: 0)
require(bounded["status"] as? String == "partial", "zero budget")
require((bounded["nodes"] as? [[String: Any]])?.isEmpty == true, "zero budget nodes")
print("Hardware map privacy, identifiers, codec and bounds: passed")
if CommandLine.arguments.contains("--local-readonly") {
    let map = HardwareMap.collect()
    let data = try JSONSerialization.data(withJSONObject: map, options: [.sortedKeys])
    let out = URL(fileURLWithPath: CommandLine.arguments.last!)
    try data.write(to: out)
    try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: out.path)
    print("Local read-only map: \(map["status"]!), \((map["nodes"] as? [[String: Any]])?.count ?? 0) nodes, \(data.count) bytes")
}

func worker(_ code: String, timeout: Double = 1, limit: Int = 2048) -> [String: Any] {
    HardwareMapWorker.run(executable: URL(fileURLWithPath: "/bin/sh"), arguments: ["-c", code],
                          timeout: timeout, maximumBytes: limit)
}
let started = ProcessInfo.processInfo.systemUptime
let stalled = worker("exec /bin/sleep 30", timeout: 0.1)
require(ProcessInfo.processInfo.systemUptime - started < 2, "worker timeout bound")
require(stalled["status"] as? String == "unavailable", "stalled worker diagnostic")
require(worker("exit 7")["status"] as? String == "unavailable", "worker failure")
require(worker("printf '[]'")["status"] as? String == "unavailable", "invalid worker shape")
require(worker("/usr/bin/head -c 4096 /dev/zero", limit: 128)["status"] as? String == "unavailable", "output bound")
let valid = worker("printf '%s' '{\"schema\":\"nullmoth-hardware-map/1\",\"status\":\"partial\",\"nodes\":[]}'")
require(valid["status"] as? String == "partial", "valid worker result")
let offsetBytes = Data([0xff, 0xde, 0x10, 0, 0, 0xff]).subdata(in: 1..<5)
require(HardwareMap.integer(offsetBytes, maximum: UInt64(UInt32.max)) == 0x10de, "offset byte decode")
require(HardwareMap.integer(Data([0, 0, 0, 0, 1]), maximum: UInt64(UInt32.max)) == nil, "32-bit numeric overflow")
print("Owned worker timeout, crash, output and shape checks: passed")

var absentBattery: [String: Any] = ["laptop": false]
Profile.attachChassisEvidence(servicePresent: false, batteryInstalled: nil, to: &absentBattery)
require(absentBattery["chassis"] as? String == "unknown", "absent battery chassis unknown")
require(absentBattery["laptop"] == nil, "no desktop classification from absent battery")
require(!Profile.matches(["laptop": false], absentBattery), "unknown chassis must not select desktop rule")
require(!Profile.matches(["laptop": true], absentBattery), "unknown chassis must not select laptop rule")
Profile.attachChassisEvidence(servicePresent: true, batteryInstalled: nil, to: &absentBattery)
require(absentBattery["laptop"] == nil, "unconfigured battery service unknown")
Profile.attachChassisEvidence(servicePresent: true, batteryInstalled: false, to: &absentBattery)
require(absentBattery["laptop"] == nil, "no installed battery is not desktop proof")
Profile.attachChassisEvidence(servicePresent: true, batteryInstalled: true, to: &absentBattery)
require(Profile.matches(["laptop": true], absentBattery), "positive battery evidence")
print("Missing battery chassis evidence and rule selection: passed")
