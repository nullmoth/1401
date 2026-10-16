import Foundation
import CoreAudio
import CoreGraphics

var cases = 0
func require(_ value: Bool, _ why: String) { if !value { fatalError(why) }; cases += 1 }
func bytes<T>(_ value: T) -> Data { var copy = value; return withUnsafeBytes(of: &copy) { Data($0) } }
func put<T>(_ value: T, into data: inout Data, at offset: Int) { let valueBytes = bytes(value); data.replaceSubrange(offset..<(offset + valueBytes.count), with: valueBytes) }
func streams(_ channels: [UInt32], pointer: UInt64 = 0, byteSize: UInt32 = 0) -> Data {
    let header = MemoryLayout<AudioBufferList>.offset(of: \AudioBufferList.mBuffers)!
    var result = Data(count: header + channels.count * MemoryLayout<AudioBuffer>.stride)
    put(UInt32(channels.count), into: &result, at: 0)
    for (index, channel) in channels.enumerated() {
        let offset = header + index * MemoryLayout<AudioBuffer>.stride
        put(channel, into: &result, at: offset)
        put(byteSize, into: &result, at: offset + 4)
        put(pointer, into: &result, at: offset + 8)
    }
    return result
}
let deadline = ProcessInfo.processInfo.systemUptime + 10
require(MemoryLayout<AudioObjectPropertyAddress>.size == 12, "SDK property address width")
require(MemoryLayout<AudioObjectID>.size == 4 && MemoryLayout<OSStatus>.size == 4, "SDK ID and status widths")
require(MemoryLayout<AudioValueRange>.stride == 16, "SDK rate range width")
require(MemoryLayout<AudioBuffer>.stride == 16 && MemoryLayout<AudioBufferList>.offset(of: \AudioBufferList.mBuffers) == 8, "SDK buffer list layout")
require(NativePeripheralFacts.deviceIDs(bytes(UInt32(0))) == nil, "null audio ID refused")
require(NativePeripheralFacts.deviceIDs(bytes(UInt32(8)) + bytes(UInt32(8))) == nil, "duplicate audio IDs refused")
require(NativePeripheralFacts.deviceIDs(Data(repeating: 1, count: 3)) == nil, "mis-sized ID data refused")
require(NativePeripheralFacts.deviceIDs(Data(repeating: 1, count: 65 * 4)) == nil, "audio device count bounded")
require(NativePeripheralFacts.deviceIDs(Data())?.isEmpty == true, "empty device set is valid")
require(NativePeripheralFacts.streamCounts(streams([2, 6]))?["total_channels"] as? UInt32 == 8, "SDK channel metadata counts")
require(NativePeripheralFacts.streamCounts(streams([], byteSize: 128))?["buffer_count"] as? UInt32 == 0, "empty stream configuration")
require(NativePeripheralFacts.streamCounts(streams([2], byteSize: 128)) != nil, "unused descriptor byte size is not assumed zero")
require(NativePeripheralFacts.streamCounts(streams([2], pointer: 1)) == nil, "stream metadata never follows nonnull sample pointer")
require(NativePeripheralFacts.streamCounts(streams([UInt32.max])) == nil, "channel overflow refused")
require(NativePeripheralFacts.streamCounts(streams([4096, 1])) == nil, "channel sum bounded")
require(NativePeripheralFacts.streamCounts(Data(repeating: 0, count: 4)) == nil, "truncated buffer header")
var truncated = streams([2]); truncated.removeLast()
require(NativePeripheralFacts.streamCounts(truncated) == nil, "truncated flexible buffer array")
var excessive = streams([]); put(UInt32.max, into: &excessive, at: 0)
require(NativePeripheralFacts.streamCounts(excessive) == nil, "buffer count overflow refused before multiplication")
let ranges = bytes(AudioValueRange(mMinimum: 44100, mMaximum: 48000))
require(NativePeripheralFacts.rates(ranges)?.first?["maximum_hz"] == 48000, "SDK reported nominal ranges")
for (low, high) in [(Double.nan, 48000), (44100, Double.infinity), (-1, 48000), (48000, 44100), (1, 1_000_001)] {
    require(NativePeripheralFacts.rates(bytes(AudioValueRange(mMinimum: low, mMaximum: high))) == nil, "nonfinite/reversed/unbounded rates refused")
}
require(NativePeripheralFacts.rates(Data(repeating: 0, count: 15)) == nil, "rate structure length")
require(NativePeripheralFacts.rates(Data(repeating: 0, count: 129 * 16)) == nil, "rate array bound")
require(NativePeripheralFacts.rates(Data())?.isEmpty == true, "empty reported range array")
require(NativePeripheralFacts.transport(kAudioDeviceTransportTypeAggregate)["kind"] as? String == "aggregate", "aggregate transport explicit")
require(NativePeripheralFacts.transport(kAudioDeviceTransportTypeVirtual)["kind"] as? String == "virtual", "virtual transport explicit")

let object: AudioObjectID = 0xF0012345
var queries: [AudioObjectPropertySelector] = []
let sourceData: [AudioObjectPropertySelector: Data] = [
    kAudioHardwarePropertyDevices: bytes(object), kAudioDevicePropertyTransportType: bytes(kAudioDeviceTransportTypeVirtual),
    kAudioDevicePropertyStreamConfiguration: streams([2]), kAudioDevicePropertyNominalSampleRate: bytes(Double(48000)),
    kAudioDevicePropertyAvailableNominalSampleRates: ranges,
    kAudioObjectPropertyName: Data("PRIVATE_ENDPOINT".utf8), kAudioDevicePropertyDeviceUID: Data("PRIVATE_UID".utf8)]
var reads = 0
let audio = NativePeripheralFacts.AudioAPI(size: { id, address, count in
    require(address.mElement == kAudioObjectPropertyElementMain, "main metadata element")
    require(address.mSelector != kAudioObjectPropertyName && address.mSelector != kAudioDevicePropertyDeviceUID, "no endpoint names/UID queries")
    queries.append(address.mSelector)
    guard let data = sourceData[address.mSelector] else { return -1 }; count = UInt32(data.count); return noErr
}, read: { id, address, count, buffer in
    reads += 1; let data = sourceData[address.mSelector]!
    require(Int(count) >= data.count, "typed API capacity")
    data.withUnsafeBytes { if let start = $0.baseAddress { buffer.copyMemory(from: start, byteCount: data.count) } }
    count = UInt32(data.count); return noErr
})
let observedAudio = NativePeripheralFacts.audioFacts(api: audio, deadline: deadline)
require(observedAudio["status"] as? String == "observed" && reads == 6, "exact permitted CoreAudio query set")
let audioJSON = String(decoding: try JSONSerialization.data(withJSONObject: observedAudio), as: UTF8.self)
require(!audioJSON.contains("PRIVATE") && !audioJSON.contains(String(object)), "anonymous audio output")
require((observedAudio["devices"] as? [[String: Any]])?.first?["device"] as? String == "audio0", "report-local audio index")
let initialReadCount = reads
let expiredAudio = NativePeripheralFacts.audioFacts(api: audio, deadline: 0)
require(expiredAudio["status"] as? String == "unavailable" && reads == initialReadCount, "deadline before native call")
let failedSize = NativePeripheralFacts.AudioAPI(size: { _, _, _ in -7 }, read: { _, _, _, _ in fatalError("unexpected read") })
require(NativePeripheralFacts.audioFacts(api: failedSize, deadline: deadline)["status"] as? String == "unavailable", "property size error")
let excessiveSize = NativePeripheralFacts.AudioAPI(size: { _, _, size in size = UInt32.max; return noErr }, read: { _, _, _, _ in fatalError("unexpected read") })
require(NativePeripheralFacts.audioFacts(api: excessiveSize, deadline: deadline)["status"] as? String == "unavailable", "allocation bound")
let changedSize = NativePeripheralFacts.AudioAPI(size: { _, _, size in size = 4; return noErr }, read: { _, _, size, _ in size = 5; return noErr })
if case .unavailable = NativePeripheralFacts.property(changedSize, object, kAudioDevicePropertyTransportType, deadline: deadline) { cases += 1 } else { fatalError("grown property must fail") }
let failedRead = NativePeripheralFacts.AudioAPI(size: { _, _, size in size = 4; return noErr }, read: { _, _, _, _ in -9 })
if case .unavailable = NativePeripheralFacts.property(failedRead, object, kAudioDevicePropertyTransportType, deadline: deadline) { cases += 1 } else { fatalError("read error") }

let mode = NativePeripheralFacts.Mode(width: 1920, height: 1080, pixelWidth: 3840, pixelHeight: 2160, refreshRate: 59.94)
require(NativePeripheralFacts.modeFacts(mode)?["refresh_hz"] as? [String: Any] != nil, "actual fractional refresh retained")
var unspecified = mode; unspecified.refreshRate = 0
require((NativePeripheralFacts.modeFacts(unspecified)?["refresh_hz"] as? [String: Any])?["status"] as? String == "unavailable", "zero refresh never becomes60")
for rate in [Double.nan, Double.infinity, -1, 2001] { var bad = mode; bad.refreshRate = rate; require(NativePeripheralFacts.modeFacts(bad) == nil, "invalid refresh") }
for dimension in [0, -1, Int.max] { var bad = mode; bad.width = dimension; require(NativePeripheralFacts.modeFacts(bad) == nil, "invalid dimension") }
var modeCalls = 0
let display = NativePeripheralFacts.DisplayAPI(list: { capacity, output, count in
    if let output = output { require(capacity == 1, "bounded display array"); output[0] = 0xF1230001 }; count = 1; return .success
}, current: { _ in modeCalls += 1; return unspecified }, modes: { _ in modeCalls += 1; return .values([mode, unspecified]) })
let observedDisplays = NativePeripheralFacts.displayFacts(api: display, deadline: deadline)
require(observedDisplays["status"] as? String == "observed" && modeCalls == 2, "display descriptor-only callbacks")
let displayJSON = String(decoding: try JSONSerialization.data(withJSONObject: observedDisplays), as: UTF8.self)
require(!displayJSON.contains(String(UInt32(0xF1230001))), "no persistent display ID")
let displayRows = observedDisplays["displays"] as! [[String: Any]]
let reportedModes = (displayRows[0]["available_modes"] as! [String: Any])["value"] as! [[String: Any]]
let reportedRefresh = ((reportedModes[0]["value"] as! [String: Any])["refresh_hz"] as! [String: Any])["value"] as! Double
require(reportedRefresh == mode.refreshRate, "precise fractional refresh value")
let expiredDisplay = NativePeripheralFacts.displayFacts(api: display, deadline: 0)
require(expiredDisplay["status"] as? String == "unavailable" && modeCalls == 2, "display deadline")
let excessiveDisplays = NativePeripheralFacts.DisplayAPI(list: { _, _, count in count = 17; return .success }, current: { _ in fatalError("unexpected mode") }, modes: { _ in fatalError("unexpected modes") })
require(NativePeripheralFacts.displayFacts(api: excessiveDisplays, deadline: deadline)["status"] as? String == "unavailable", "display count bound")
var growCalls = 0
let growingDisplays = NativePeripheralFacts.DisplayAPI(list: { _, _, count in growCalls += 1; count = growCalls == 1 ? 1 : 2; return .success }, current: { _ in fatalError("unexpected mode") }, modes: { _ in fatalError("unexpected modes") })
require(NativePeripheralFacts.displayFacts(api: growingDisplays, deadline: deadline)["status"] as? String == "unavailable", "display list race refuses before out-of-range iteration")
for value: CGDirectDisplayID in [0, 7] {
    let invalidIDs = NativePeripheralFacts.DisplayAPI(list: { _, output, count in
        if let output = output { output[0] = value; output[1] = value }; count = 2; return .success
    }, current: { _ in fatalError("unexpected invalid display query") }, modes: { _ in fatalError("unexpected invalid modes query") })
    require(NativePeripheralFacts.displayFacts(api: invalidIDs, deadline: deadline)["status"] as? String == "unavailable", "invalid and duplicate display IDs refused")
}
let excessiveModes = NativePeripheralFacts.DisplayAPI(list: display.list, current: display.current, modes: { _ in .values(Array(repeating: mode, count: 193)) })
require(NativePeripheralFacts.displayFacts(api: excessiveModes, deadline: deadline)["status"] as? String == "partial", "mode array count bound")
let unavailableModes = NativePeripheralFacts.DisplayAPI(list: display.list, current: { _ in nil }, modes: { _ in .unavailable("metadata unavailable") })
require(NativePeripheralFacts.displayFacts(api: unavailableModes, deadline: deadline)["status"] as? String == "partial", "mode API failure explicit")
let refused = NativePeripheralFacts.collect()
require(refused["status"] as? String == "unavailable", "native collection refused outside owned child")
print("\(cases) typed SDK/pure audio-mode metadata fixture assertions passed; no device APIs invoked")
