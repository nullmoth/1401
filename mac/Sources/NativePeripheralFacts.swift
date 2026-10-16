// Copyright (c) 2026 NullMoth Systems.
import Foundation
import CoreAudio
import CoreGraphics

enum NativePeripheralFacts {
    static let maximumPropertyBytes = 4096
    static let maximumAudioDevices = 64
    static let maximumStreamBuffers = 128
    static let maximumChannels = 4096
    static let maximumRateRanges = 128
    static let maximumDisplays = 16
    static let maximumDisplayModes = 192

    struct AudioAPI {
        var size: (AudioObjectID, inout AudioObjectPropertyAddress, inout UInt32) -> OSStatus
        var read: (AudioObjectID, inout AudioObjectPropertyAddress, inout UInt32, UnsafeMutableRawPointer) -> OSStatus
    }
    struct Mode {
        var width: Int
        var height: Int
        var pixelWidth: Int
        var pixelHeight: Int
        var refreshRate: Double
    }
    enum Modes { case values([Mode]), unavailable(String) }
    struct DisplayAPI {
        var list: (UInt32, UnsafeMutablePointer<CGDirectDisplayID>?, inout UInt32) -> CGError
        var current: (CGDirectDisplayID) -> Mode?
        var modes: (CGDirectDisplayID) -> Modes
    }
    enum Property { case bytes(Data), unavailable(String) }

    static func unavailable(_ source: String, _ reason: String) -> [String: Any] {
        ["status": "unavailable", "source": source, "reason": reason]
    }
    static func observed(_ source: String, _ value: Any) -> [String: Any] {
        ["status": "observed", "source": source, "value": value]
    }

    static func property(_ api: AudioAPI, _ object: AudioObjectID, _ selector: AudioObjectPropertySelector,
                         scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal,
                         deadline: Double) -> Property {
        guard ProcessInfo.processInfo.systemUptime < deadline else { return .unavailable("metadata deadline reached") }
        var address = AudioObjectPropertyAddress(mSelector: selector, mScope: scope, mElement: kAudioObjectPropertyElementMain)
        var size: UInt32 = 0
        let result = api.size(object, &address, &size)
        guard result == noErr else { return .unavailable("CoreAudio status \(result)") }
        guard size <= UInt32(maximumPropertyBytes) else { return .unavailable("property byte count exceeds bounded probe") }
        if size == 0 { return .bytes(Data()) }
        guard ProcessInfo.processInfo.systemUptime < deadline else { return .unavailable("metadata deadline reached") }
        let capacity = Int(size)
        let buffer = UnsafeMutableRawPointer.allocate(byteCount: capacity, alignment: MemoryLayout<UInt64>.alignment)
        defer { buffer.deallocate() }
        buffer.initializeMemory(as: UInt8.self, repeating: 0, count: capacity)
        let readResult = api.read(object, &address, &size, buffer)
        guard readResult == noErr else { return .unavailable("CoreAudio status \(readResult)") }
        guard size <= UInt32(capacity) else { return .unavailable("property changed beyond allocated byte count") }
        return .bytes(Data(bytes: buffer, count: Int(size)))
    }

    static func uint32(_ data: Data, offset: Int = 0) -> UInt32? {
        guard offset >= 0, offset <= data.count, 4 <= data.count - offset else { return nil }
        return data.withUnsafeBytes { $0.loadUnaligned(fromByteOffset: offset, as: UInt32.self) }
    }
    static func double(_ data: Data, offset: Int = 0) -> Double? {
        guard offset >= 0, offset <= data.count, 8 <= data.count - offset else { return nil }
        return data.withUnsafeBytes { $0.loadUnaligned(fromByteOffset: offset, as: Double.self) }
    }
    static func deviceIDs(_ data: Data) -> [AudioObjectID]? {
        guard data.count % MemoryLayout<AudioObjectID>.size == 0,
              data.count / MemoryLayout<AudioObjectID>.size <= maximumAudioDevices else { return nil }
        var ids: [AudioObjectID] = []
        for offset in stride(from: 0, to: data.count, by: MemoryLayout<AudioObjectID>.size) {
            guard let id = uint32(data, offset: offset), id != kAudioObjectUnknown, !ids.contains(id) else { return nil }
            ids.append(id)
        }
        return ids
    }
    static func streamCounts(_ data: Data) -> [String: Any]? {
        guard let header = MemoryLayout<AudioBufferList>.offset(of: \AudioBufferList.mBuffers),
              let channelsOffset = MemoryLayout<AudioBuffer>.offset(of: \AudioBuffer.mNumberChannels),
              let pointerOffset = MemoryLayout<AudioBuffer>.offset(of: \AudioBuffer.mData),
              let count = uint32(data), count <= UInt32(maximumStreamBuffers), data.count >= header else { return nil }
        let stride = MemoryLayout<AudioBuffer>.stride
        guard Int(count) <= (data.count - header) / stride else { return nil }
        var channels: [UInt32] = []
        var total: UInt32 = 0
        for index in 0..<Int(count) {
            let start = header + index * stride
            guard let value = uint32(data, offset: start + channelsOffset), value <= UInt32(maximumChannels),
                  pointerOffset <= stride, MemoryLayout<UnsafeRawPointer>.size <= stride - pointerOffset else { return nil }
            // The documented stream-configuration property has no sample data pointers.
            let pointerBytes = data[(start + pointerOffset)..<(start + pointerOffset + MemoryLayout<UnsafeRawPointer>.size)]
            guard pointerBytes.allSatisfy({ $0 == 0 }), total <= UInt32(maximumChannels) - value else { return nil }
            total += value; channels.append(value)
        }
        return ["buffer_count": count, "channels_per_buffer": channels, "total_channels": total]
    }
    static func rates(_ data: Data) -> [[String: Double]]? {
        let stride = MemoryLayout<AudioValueRange>.stride
        guard stride == 16, data.count % stride == 0, data.count / stride <= maximumRateRanges else { return nil }
        var result: [[String: Double]] = []
        for offset in Swift.stride(from: 0, to: data.count, by: stride) {
            guard let minimum = double(data, offset: offset), let maximum = double(data, offset: offset + 8),
                  minimum.isFinite, maximum.isFinite, minimum > 0, maximum >= minimum, maximum <= 1_000_000 else { return nil }
            result.append(["minimum_hz": minimum, "maximum_hz": maximum])
        }
        return result
    }
    static func transport(_ code: UInt32) -> [String: Any] {
        let kind: String
        switch code {
        case kAudioDeviceTransportTypeAggregate: kind = "aggregate"
        case kAudioDeviceTransportTypeVirtual: kind = "virtual"
        case kAudioDeviceTransportTypeBuiltIn: kind = "built-in"
        case kAudioDeviceTransportTypePCI: kind = "PCI"
        case kAudioDeviceTransportTypeUSB: kind = "USB"
        case kAudioDeviceTransportTypeBluetooth, kAudioDeviceTransportTypeBluetoothLE: kind = "Bluetooth"
        case kAudioDeviceTransportTypeHDMI: kind = "HDMI"
        case kAudioDeviceTransportTypeDisplayPort: kind = "DisplayPort"
        case kAudioDeviceTransportTypeAirPlay: kind = "AirPlay"
        case kAudioDeviceTransportTypeUnknown: kind = "unknown"
        default: kind = "other"
        }
        return ["code": code, "kind": kind]
    }
    static func audioFacts(api: AudioAPI, deadline: Double) -> [String: Any] {
        let source = "CoreAudio AudioObjectGetPropertyDataSize/Data"
        let ids: [AudioObjectID]
        switch property(api, AudioObjectID(kAudioObjectSystemObject), kAudioHardwarePropertyDevices, deadline: deadline) {
        case .unavailable(let reason): return unavailable(source, reason)
        case .bytes(let bytes):
            guard let values = deviceIDs(bytes) else { return unavailable(source, "invalid or oversized audio device array") }
            ids = values
        }
        var rows: [[String: Any]] = []
        var partial = false
        for (index, id) in ids.enumerated() {
            guard ProcessInfo.processInfo.systemUptime < deadline else { partial = true; break }
            var row: [String: Any] = ["device": "audio\(index)",
                "codec_relationship": "unavailable: identity/name properties not queried",
                "physical_speaker_wiring": "unobserved"]
            let queries: [(String, AudioObjectPropertySelector, AudioObjectPropertyScope)] = [
                ("transport", kAudioDevicePropertyTransportType, kAudioObjectPropertyScopeGlobal),
                ("input_stream_channels", kAudioDevicePropertyStreamConfiguration, kAudioObjectPropertyScopeInput),
                ("output_stream_channels", kAudioDevicePropertyStreamConfiguration, kAudioObjectPropertyScopeOutput),
                ("nominal_sample_rate", kAudioDevicePropertyNominalSampleRate, kAudioObjectPropertyScopeGlobal),
                ("available_nominal_sample_rates", kAudioDevicePropertyAvailableNominalSampleRates, kAudioObjectPropertyScopeGlobal)]
            for (key, selector, scope) in queries {
                let selectorSource = source + ": " + key
                switch property(api, id, selector, scope: scope, deadline: deadline) {
                case .unavailable(let reason): row[key] = unavailable(selectorSource, reason); partial = true
                case .bytes(let bytes):
                    var value: Any?
                    if key == "transport", bytes.count == 4, let code = uint32(bytes) { value = transport(code) }
                    else if key == "nominal_sample_rate", bytes.count == 8, let rate = double(bytes), rate.isFinite, rate > 0, rate <= 1_000_000 { value = rate }
                    else if key == "available_nominal_sample_rates" { value = rates(bytes) }
                    else if key == "input_stream_channels" || key == "output_stream_channels" { value = streamCounts(bytes) }
                    if let observedValue = value { row[key] = observed(selectorSource, observedValue) }
                    else { row[key] = unavailable(selectorSource, "invalid bounded property metadata"); partial = true }
                }
            }
            rows.append(row)
        }
        return ["status": partial ? "partial" : "observed", "source": source, "devices": rows,
                "meaning": "driver-reported descriptors and nominal rate ranges; no stream initialization or physical audio qualification"]
    }
    static func modeFacts(_ mode: Mode) -> [String: Any]? {
        guard [mode.width, mode.height, mode.pixelWidth, mode.pixelHeight].allSatisfy({ $0 > 0 && $0 <= 65536 }),
              mode.refreshRate.isFinite, mode.refreshRate >= 0, mode.refreshRate <= 2000 else { return nil }
        let refresh: [String: Any] = mode.refreshRate == 0
            ? unavailable("CGDisplayModeGetRefreshRate", "driver did not specify a fixed refresh rate")
            : observed("CGDisplayModeGetRefreshRate", mode.refreshRate)
        return ["width_points": mode.width, "height_points": mode.height, "pixel_width": mode.pixelWidth,
                "pixel_height": mode.pixelHeight, "refresh_hz": refresh]
    }
    static func displayFacts(api: DisplayAPI, deadline: Double) -> [String: Any] {
        let source = "CoreGraphics active display modes"
        guard ProcessInfo.processInfo.systemUptime < deadline else { return unavailable(source, "metadata deadline reached") }
        var count: UInt32 = 0
        let result = api.list(0, nil, &count)
        guard result == .success else { return unavailable(source, "CoreGraphics status \(result.rawValue)") }
        guard count <= UInt32(maximumDisplays) else { return unavailable(source, "active display count exceeds bounded probe") }
        if count == 0 { return ["status": "observed", "source": source, "displays": []] }
        let capacity = Int(count)
        var displays = [CGDirectDisplayID](repeating: 0, count: capacity)
        let listed = displays.withUnsafeMutableBufferPointer { api.list(UInt32(capacity), $0.baseAddress, &count) }
        guard listed == .success, count <= UInt32(capacity) else { return unavailable(source, "active display array changed or unavailable") }
        let selected = Array(displays.prefix(Int(count)))
        guard selected.allSatisfy({ $0 != kCGNullDirectDisplay }), Set(selected).count == selected.count else {
            return unavailable(source, "invalid or duplicate active display metadata")
        }
        var rows: [[String: Any]] = [], partial = false
        for index in 0..<Int(count) {
            guard ProcessInfo.processInfo.systemUptime < deadline else { partial = true; break }
            let id = displays[index]
            var row: [String: Any] = ["display": "display\(index)", "gpu_relationship": "unavailable: no documented exact device join queried"]
            if let current = api.current(id), let value = modeFacts(current) { row["current_mode"] = observed("CGDisplayCopyDisplayMode", value) }
            else { row["current_mode"] = unavailable("CGDisplayCopyDisplayMode", "current mode unavailable or malformed"); partial = true }
            if ProcessInfo.processInfo.systemUptime >= deadline {
                row["available_modes"] = unavailable("CGDisplayCopyAllDisplayModes", "metadata deadline reached"); partial = true
            } else {
                switch api.modes(id) {
                case .unavailable(let reason): row["available_modes"] = unavailable("CGDisplayCopyAllDisplayModes", reason); partial = true
                case .values(let modes):
                    if modes.count > maximumDisplayModes { row["available_modes"] = unavailable("CGDisplayCopyAllDisplayModes", "mode count exceeds bounded probe"); partial = true }
                    else {
                        var values: [[String: Any]] = []
                        var malformed = false
                        for (modeIndex, mode) in modes.enumerated() {
                            if let value = modeFacts(mode) { values.append(["mode": "mode\(modeIndex)", "value": value]) }
                            else { malformed = true }
                        }
                        row["available_modes"] = ["status": malformed ? "partial" : "observed", "source": "CGDisplayCopyAllDisplayModes", "value": values]
                        partial = partial || malformed
                    }
                }
            }
            rows.append(row)
        }
        return ["status": partial ? "partial" : "observed", "source": source, "displays": rows,
                "meaning": "current and driver-enumerated modes; availability does not prove selectable/stable modes or monitor/GPU wiring"]
    }
    private static var nativeAudio: AudioAPI {
        AudioAPI(size: { id, address, size in AudioObjectGetPropertyDataSize(id, &address, 0, nil, &size) },
                 read: { id, address, size, buffer in AudioObjectGetPropertyData(id, &address, 0, nil, &size, buffer) })
    }
    private static func nativeMode(_ mode: CGDisplayMode) -> Mode {
        Mode(width: mode.width, height: mode.height, pixelWidth: mode.pixelWidth, pixelHeight: mode.pixelHeight, refreshRate: mode.refreshRate)
    }
    private static var nativeDisplay: DisplayAPI {
        DisplayAPI(list: { max, ids, count in CGGetActiveDisplayList(max, ids, &count) },
            current: { id in CGDisplayCopyDisplayMode(id).map(nativeMode) },
            modes: { id in
                guard let array = CGDisplayCopyAllDisplayModes(id, nil) else { return .unavailable("driver mode array unavailable") }
                let count = CFArrayGetCount(array)
                guard count <= maximumDisplayModes else { return .unavailable("mode count exceeds bounded probe") }
                var values: [Mode] = []
                for index in 0..<count {
                    guard let pointer = CFArrayGetValueAtIndex(array, index) else { return .unavailable("invalid mode array") }
                    let value = unsafeBitCast(pointer, to: CFTypeRef.self)
                    guard CFGetTypeID(value) == CGDisplayMode.typeID else { return .unavailable("unexpected mode metadata type") }
                    values.append(nativeMode(unsafeBitCast(pointer, to: CGDisplayMode.self)))
                }
                return .values(values)
            })
    }
    static func collect(seconds: Double = 1.25) -> [String: Any] {
        guard CommandLine.arguments.count == 2, CommandLine.arguments[1] == "--hardware-map" else {
            return unavailable("owned hardware-map child", "native metadata collection declined outside child mode")
        }
        let deadline = ProcessInfo.processInfo.systemUptime + min(max(seconds, 0), 2)
        return ["schema": "nullmoth-peripheral-facts/1", "audio": audioFacts(api: nativeAudio, deadline: deadline),
                "display_modes": displayFacts(api: nativeDisplay, deadline: deadline),
                "wifi": unavailable("CoreWLAN documented capability API", "supported channels depend on adopted country; no location/country query or wireless scan performed"),
                "qualification": "driver-reported metadata only; functional hardware support not assessed"]
    }
}
