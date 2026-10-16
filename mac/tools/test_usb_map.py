#!/usr/bin/env python3
"""Run the production mapper against sparse ports and repeated controller IDs."""
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = (root / 'Sources/main.swift').read_text()
production = source[source.index('func usbControllerKey('):source.index('let crashDirs =')]
checks = r'''
func controller(_ path: String, _ ports: [Int]) -> [String: Any] {
    ["controller": "XHC0", "key": path, "path": path, "vendor": "1022", "device": "149C",
     "ports": ports.map { ["name": "P\($0)", "port": $0, "devices": []] as [String: Any] }]
}
let a = controller("IOService:/PCI0/GP13/XHC0", [1, 17, 21])
let b = controller("IOService:/PCI0/GP14/XHC0", [2, 18])
let ak = usbControllerKey(a), bk = usbControllerKey(b)
let (plist, error) = utbMap([a, b], [ak: ["P1": 0, "P21": 3], bk: ["P18": 255]])
assert(error == nil)
let bytes = try PropertyListSerialization.data(fromPropertyList: plist!, format: .xml, options: 0)
let roundtrip = try PropertyListSerialization.propertyList(from: bytes, options: [], format: nil) as! [String: Any]
let personalities = roundtrip["IOKitPersonalities"] as! [String: [String: Any]]
assert(personalities.count == 2)
for personality in personalities.values {
    let path = personality["IOPathMatch"] as! String
    let properties = personality["IOProviderMergeProperties"] as! [String: Any]
    let ports = properties["ports"] as! [String: Any]
    let top = properties["port-count"] as! Data
    assert(top == Data([path == ak ? 21 : 18, 0, 0, 0]))
    assert(ports.count == (path == ak ? 2 : 1))
}
func refused(_ ctrls: [[String: Any]], _ selected: [String: [String: Int]]) {
    let (map, error) = utbMap(ctrls, selected)
    assert(map == nil && error != nil)
}
refused([a], [ak: ["P99": 3]])
refused([a], [ak: ["P1": 0], bk: ["P18": 3]])
refused([controller(ak, [0])], [ak: ["P0": 0]])
refused([controller(ak, [1, 1])], [ak: ["P1": 0]])
refused([a], [ak: ["P1": 7]])
refused([a, a], [ak: ["P1": 0]])
let noPath = controller("", [1])
refused([noPath, noPath], ["XHC0": ["P1": 0]])
let many = controller(ak, Array(1...16))
refused([many], [ak: Dictionary(uniqueKeysWithValues: (1...16).map { ("P\($0)", 3) })])
let (single, singleError) = utbMap([noPath], ["XHC0": ["P1": 0]])
assert(single != nil && singleError == nil)
print("Sparse port bounds, distinct duplicate-ID controllers, plist roundtrip and invalid selections passed.")
'''
with tempfile.TemporaryDirectory() as directory:
    script = Path(directory) / 'usb.swift'
    script.write_text('import Foundation\n' + production + checks)
    subprocess.run(['xcrun', 'swift', str(script)], check=True)
