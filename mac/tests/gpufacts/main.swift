import Foundation
var failed = 0
func check(_ ok: Bool, _ what: String) { if ok { print("ok   " + what) } else { failed += 1; print("FAIL " + what) } }
func reg(_ s: Int, _ w: Int) -> Int { s | (w << 4) }
func le(_ v: Int) -> Data { Data([UInt8(v & 255), UInt8((v >> 8) & 255), UInt8((v >> 16) & 255), UInt8((v >> 24) & 255)]) }
typealias G = GpuFacts
check(G.decodeLink(status: reg(4, 16), caps: reg(4, 16)).verdict == "ok", "Gen4 x16 against a Gen4 x16 card is ok")
check(G.decodeLink(status: reg(3, 4), caps: reg(4, 16)).verdict == "degraded", "fewer lanes than the card supports is flagged")
check(G.decodeLink(status: reg(1, 16), caps: reg(5, 16)).verdict == "idle-or-low", "a lower speed at full width is idle step-down, not a fault")
check(G.decodeLink(status: nil, caps: reg(4, 16)).verdict == "unknown" && G.decodeLink(status: 0, caps: 0).verdict == "unknown", "unreadable registers are unknown, never ok")
check([0x2d05, 0x2684, 0x2504, 0x1f08].map(G.generation) == ["Blackwell", "Ada", "Ampere", "Turing"] && G.generation(0x1c03).contains("not supported"), "device ids map to generations")
let gpu: [String: Any] = ["IOObjectClass": "IOPCIDevice", "vendor-id": le(0x10de), "device-id": le(0x2d05), "class-code": le(0x030000), "pcidebug": "1:0:0",
    "IOPCIExpressLinkStatus": reg(5, 4), "IOPCIExpressLinkCapabilities": reg(5, 16), "nvrm-bar1-mb": 8192, "nvrm-rebar": "on",
    "IORegistryEntryChildren": [["IOObjectClass": "NVRM", "IORegistryEntryChildren": [["IOObjectClass": "NVAccel"]]]]]
let amd: [String: Any] = ["IOObjectClass": "IOPCIDevice", "vendor-id": le(0x1002), "device-id": le(0x73bf), "class-code": le(0x030000)]
let audio: [String: Any] = ["IOObjectClass": "IOPCIDevice", "vendor-id": le(0x10de), "device-id": le(0x22eb), "class-code": le(0x040300)]
var ext = gpu; ext["pcidebug"] = "7:0:0"
let tree: [[String: Any]] = [["IOObjectClass": "Root", "IORegistryEntryChildren": [
    ["IOObjectClass": "IOPCIBridge", "IORegistryEntryChildren": [gpu, amd, audio]],
    ["IOObjectClass": "IOThunderboltPort", "IORegistryEntryChildren": [["IOObjectClass": "IOPCIBridge", "IORegistryEntryChildren": [ext]]]]]]]
let found = G.gpus(tree)
check(found.count == 2, "only NVIDIA display-class devices are listed (not the AMD card, not the card's audio function)")
check(found.map { $0.external } == [false, true], "a card under a Thunderbolt port is external")
check(found[0].driver == ["NVRM", "NVAccel"], "attached driver parts are read from the card's children")
check(found[0].nvrm["nvrm-bar1-mb"] == "8192" && found[0].nvrm["nvrm-rebar"] == "on", "the kext's BAR and Resizable BAR facts are carried")
check(G.describe(found[0]).contains("LOW") && G.describe(found[0]).contains("x16"), "a Gen5 x4 link on an x16 card reads LOW with the card's width")
print("\(failed) failed"); exit(failed == 0 ? 0 : 1)
