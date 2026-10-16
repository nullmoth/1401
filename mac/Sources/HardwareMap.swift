// Copyright (c) 2026 NullMoth Systems.
import Foundation
import IOKit
import Darwin

enum HardwareMap {
    static let integerFields: [String: (String, UInt64)] = [
        "vendor-id": ("pci_vendor", 0xffff), "device-id": ("pci_device", 0xffff),
        "subsystem-vendor-id": ("pci_subsystem_vendor", 0xffff),
        "subsystem-id": ("pci_subsystem_device", 0xffff),
        "class-code": ("pci_class", 0xffffff), "revision-id": ("pci_revision", 0xff),
        "idVendor": ("usb_vendor", 0xffff), "idProduct": ("usb_product", 0xffff),
        "bDeviceClass": ("usb_class", 0xff), "bDeviceSubClass": ("usb_subclass", 0xff),
        "bInterfaceClass": ("usb_interface_class", 0xff),
        "bInterfaceSubClass": ("usb_interface_subclass", 0xff),
        "bInterfaceNumber": ("usb_interface_number", 0xff),
        "port": ("usb_port", 0xffffffff), "UsbConnector": ("usb_connector", 0xff),
        "VendorID": ("hid_vendor", 0xffff), "ProductID": ("hid_product", 0xffff),
        "PrimaryUsagePage": ("hid_usage_page", 0xffff), "PrimaryUsage": ("hid_usage", 0xffff),
        "IOHDACodecVendorID": ("audio_codec_vendor_device", 0xffffffff),
        "IOHDACodecRevisionID": ("audio_codec_revision", 0xffffffff),
        "cpu-number": ("cpu_index", 0xffff)
    ]

    static func integer(_ value: Any?, maximum: UInt64) -> UInt64? {
        if let data = value as? Data {
            guard (1...8).contains(data.count) else { return nil }
            var number: UInt64 = 0
            for (i, byte) in data.enumerated() { number |= UInt64(byte) << (8 * i) }
            return number <= maximum ? number : nil
        }
        if let number = value as? NSNumber {
            guard CFGetTypeID(number) != CFBooleanGetTypeID(),
                  let result = UInt64(number.stringValue), result <= maximum else { return nil }
            return result
        }
        return nil
    }

    static func acpiIDs(_ value: Any?) -> [String] {
        let values: [String]
        if let data = value as? Data, data.count <= 256 {
            values = data.split(separator: 0).compactMap { String(data: Data($0), encoding: .ascii) }
        } else if let text = value as? String, text.utf8.count <= 256 { values = [text] }
        else { return [] }
        return values.filter { $0.range(of: #"^(?:PNP[0-9A-F]{4}|ACPI[0-9A-F]{4}|[A-Z]{3}[0-9A-F]{4}|[A-Z]{4}[0-9A-F]{4})$"#, options: .regularExpression) != nil }
    }

    static func collectionUsages(_ value: Any?) -> [[String: UInt64]]? {
        guard let pairs = value as? [[String: Any]], pairs.count <= 64 else { return nil }
        var result: [[String: UInt64]] = []
        for pair in pairs {
            guard let page = integer(pair["DeviceUsagePage"], maximum: 0xffff),
                  let usage = integer(pair["DeviceUsage"], maximum: 0xffff) else { return nil }
            result.append(["usage_page": page, "usage": usage])
        }
        return result
    }

    // A strict allow-list prevents serials, MACs, user-assigned device names,
    // addresses and HID input from entering the report.
    static func facts(_ properties: [String: Any]) -> [String: Any] {
        var out: [String: Any] = [:]
        for (key, rule) in integerFields {
            if let value = integer(properties[key], maximum: rule.1) { out[rule.0] = value }
        }
        if let raw = properties["DeviceUsagePairs"] {
            if let pairs = collectionUsages(raw) {
                out["hid_top_level_collection_usages"] = pairs
                out["hid_declared_digitizer_collection_count"] = pairs.filter { $0["usage_page"] == 13 }.count
            } else {
                out["hid_collection_status"] = "unavailable: invalid or oversized collection metadata"
            }
        }
        let ids = Set(["compatible", "acpi-hid", "acpi-cid"].flatMap { acpiIDs(properties[$0]) }).sorted()
        if !ids.isEmpty { out["acpi_ids"] = ids }
        return out
    }

    static func relevant(_ name: String, _ facts: [String: Any]) -> Bool {
        if !facts.isEmpty { return true }
        return ["PCI", "USB", "HID", "I2C", "PS2", "Audio", "HDA", "Bluetooth", "Ethernet", "80211", "NVMe", "AHCI", "SDXC", "Battery", "Framebuffer", "DisplayConnect", "IOCPU"].contains { name.contains($0) }
    }

    static func className(_ entry: io_registry_entry_t) -> String {
        var name = [CChar](repeating: 0, count: 128)
        guard IOObjectGetClass(entry, &name) == KERN_SUCCESS else { return "unavailable" }
        return String(cString: name)
    }

    static func property(_ entry: io_registry_entry_t, _ name: String) -> Any? {
        IORegistryEntryCreateCFProperty(entry, name as CFString, kCFAllocatorDefault, 0)?.takeRetainedValue()
    }

    static func cpuFacts() -> [String: Any] {
        let names = ["hw.ncpu", "hw.physicalcpu", "hw.physicalcpu_max", "hw.logicalcpu", "hw.logicalcpu_max",
                     "hw.l1icachesize", "hw.l1dcachesize", "hw.l2cachesize", "hw.l3cachesize",
                     "hw.nperflevels", "hw.perflevel0.physicalcpu", "hw.perflevel0.logicalcpu",
                     "hw.perflevel1.physicalcpu", "hw.perflevel1.logicalcpu", "kern.hv_vmm_present"]
        var fields: [String: Any] = [:]
        for name in names {
            var size = 0
            guard sysctlbyname(name, nil, &size, nil, 0) == 0, [4, 8].contains(size) else {
                fields[name] = ["status": "unavailable", "source": "kernel sysctl"]
                continue
            }
            var value: UInt64 = 0
            let expected = size
            guard sysctlbyname(name, &value, &size, nil, 0) == 0, size == expected else {
                fields[name] = ["status": "unavailable", "source": "kernel sysctl"]
                continue
            }
            fields[name] = ["status": "observed", "source": "kernel sysctl", "value": value]
        }
        return ["fields": fields, "scope": "kernel-visible CPU and cache counts; does not prove firmware or package topology"]
    }

    static func localNodes(_ entries: [UInt64: [String: Any]]) -> [[String: Any]] {
        let keys = entries.keys.sorted()
        let labels = Dictionary(uniqueKeysWithValues: keys.enumerated().map { ($0.element, "n\($0.offset)") })
        return keys.map { id -> [String: Any] in
            var row = entries[id]!
            row["id"] = labels[id]!
            if let parent = row.removeValue(forKey: "parent_registry_id") as? UInt64 {
                if let label = labels[parent] { row["parent"] = label }
                else { row["parent_status"] = "outside selected registry nodes" }
            }
            return row
        }
    }

    static func registryUnavailable(cpu: [String: Any]) -> [String: Any] {
        ["schema": "nullmoth-hardware-map/1", "status": "unavailable", "source": "IOService registry",
         "reason": "registry enumeration denied", "nodes": [[String: Any]](), "cpu": cpu]
    }

    static func collect(maximumNodes: Int = 2048, maximumVisited: Int = 12000,
                        seconds: Double = 2) -> [String: Any] {
        let nodeLimit = min(max(maximumNodes, 1), 4096)
        let visitLimit = min(max(maximumVisited, 1), 24000)
        let deadline = ProcessInfo.processInfo.systemUptime + min(max(seconds, 0), 3)
        var iterator: io_iterator_t = 0
        guard IORegistryCreateIterator(kIOMainPortDefault, kIOServicePlane,
                                      IOOptionBits(kIORegistryIterateRecursively), &iterator) == KERN_SUCCESS else {
            return registryUnavailable(cpu: cpuFacts())
        }
        defer { IOObjectRelease(iterator) }
        var entries: [UInt64: [String: Any]] = [:]
        var visited = 0, truncated = false
        while true {
            if entries.count >= nodeLimit || visited >= visitLimit || ProcessInfo.processInfo.systemUptime >= deadline {
                truncated = true; break
            }
            let entry = IOIteratorNext(iterator)
            if entry == 0 { break }
            defer { IOObjectRelease(entry) }
            visited += 1
            let cls = className(entry)
            var properties: [String: Any] = [:]
            for key in integerFields.keys { properties[key] = property(entry, key) }
            for key in ["compatible", "acpi-hid", "acpi-cid", "DeviceUsagePairs"] { properties[key] = property(entry, key) }
            let values = facts(properties)
            guard relevant(cls, values) else { continue }
            var id: UInt64 = 0
            guard IORegistryEntryGetRegistryEntryID(entry, &id) == KERN_SUCCESS else { continue }
            var row: [String: Any] = ["driver_class": cls, "observed": values]
            var parent: io_registry_entry_t = 0
            if IORegistryEntryGetParentEntry(entry, kIOServicePlane, &parent) == KERN_SUCCESS {
                defer { IOObjectRelease(parent) }
                var parentID: UInt64 = 0
                if IORegistryEntryGetRegistryEntryID(parent, &parentID) == KERN_SUCCESS {
                    row["parent_registry_id"] = parentID
                    row["parent_driver_class"] = className(parent)
                }
            }
            entries[id] = row
        }
        // Node numbers are local to this report; no persistent hardware ID is emitted.
        let nodes = localNodes(entries)
        return ["schema": "nullmoth-hardware-map/1", "status": truncated ? "partial" : "observed",
                "source": "IOService registry", "identity_origin": "live registry; firmware or driver properties may be injected",
                "nodes": nodes, "visited": visited, "cpu": cpuFacts(),
                "not_observed": ["firmware-disabled devices", "physical connector wiring", "hardware display mux wiring",
                                 "fan and RGB wiring", "Tensor or RT unit counts", "macOS driver qualification"]]
    }
}
