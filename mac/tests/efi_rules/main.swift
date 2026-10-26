import Foundation
// usage: efi_rules_test <efi_rules.json> <vectors.json>
// Every case was decided by the Python checker; the Swift checker has to reach the same issues, in the same order,
// and leave none after fixing.
let argv = CommandLine.arguments
let rules = try EfiRules.load(URL(fileURLWithPath: argv[1]))
let vectors = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: argv[2]))) as! [String: Any]
let configs = vectors["configs"] as! [String: String]
var failed = 0, passed = 0
for c in vectors["cases"] as! [[String: Any]] {
    let blob = Data(base64Encoded: configs[c["config"] as! String]!)!
    let cfg = try PropertyListSerialization.propertyList(from: blob, format: nil) as! [String: Any]
    let facts = c["facts"] as! [String: Any], scope = c["scope"] as! String
    let issues = try EfiRules.check(cfg, facts: facts, scope: scope, rules: rules)
    let fixed = try EfiRules.fix(cfg, issues)
    let after = try EfiRules.check(fixed as! [String: Any], facts: facts, scope: scope, rules: rules).map(\.id)
    // dictionaries compared as values: binary plist bytes depend on key order, which is not stable
    let unchanged = (cfg as NSDictionary).isEqual(try PropertyListSerialization.propertyList(from: blob, format: nil) as! NSDictionary)
    if issues.map(\.id) == c["issues"] as! [String] && after == c["after_fix"] as! [String] && unchanged {
        passed += 1
    } else {
        failed += 1
        print("DIFFERS: \(c["name"]!)\n  swift:  \(issues.map(\.id)) after fix \(after)\n  python: \(c["issues"]!) after fix \(c["after_fix"]!)")
    }
}
// the CPU families from real brand strings, as the Python side decided them with no codename
for c in vectors["cpu_names"] as! [[String: Any]] {
    let got = EfiRules.cpuClasses(vendor: c["vendor"] as! String, name: c["name"] as! String)
    if got == c["classes"] as! [String] { passed += 1 } else {
        failed += 1; print("DIFFERS: cpu \(c["name"]!): swift \(got), python \(c["classes"]!)")
    }
}
let dmarOn = "OCA: Found 42 ACPI tables\nOCA: Detected table DMAR (52414D44)", dmarOff = "OCA: Found 40 ACPI tables\nOCA: Detected table FACP"
if EfiRules.logFacts(dmarOn) != [] || EfiRules.logFacts(dmarOff) != ["firmware_no_dmar"] || EfiRules.logFacts(nil) != [] || EfiRules.logFacts("no tables line") != [] {
    failed += 1; print("DIFFERS: reading VT-d from the OpenCore log")
} else { passed += 1 }
// each issue names this config's own values (10-26: "it doesn't tell you which boot-args")
let sample: [String: Any] = ["Misc": ["Debug": ["Target": 3, "AppleDebug": false, "ApplePanic": false], "Security": ["ExposeSensitiveData": 6]],
                             "NVRAM": ["Add": [EfiRules.boot: ["boot-args": "-v ctrsmt=full keepsyms=1"]]],
                             "Kernel": ["Add": [["BundlePath": "CpuTopologyRebuild.kext", "Enabled": true]]]]
let sampleFacts: [String: Any] = ["macos": "24.6.0", "cpu_vendor": "Intel", "cpu_class": ["arrow_lake", "core_ultra", "intel_hybrid"],
                                  "chipset": "", "laptop": false, "amd_dgpu": false, "intel_igpu": false, "fact": []]
let shownIssues = try EfiRules.check(sample, facts: sampleFacts, scope: "installed", rules: rules)
let lines = shownIssues.flatMap(\.onThisMac).joined(separator: "\n")
for want in ["Misc > Debug > Target is 3; add 65 to it, making 67.", "remove ctrsmt=full.",
             "Kernel > Add: CpuTopologyRebuild.kext is enabled; set Enabled to false.", "Misc > Security > ExposeSensitiveData is 6; add 1 to it, making 7."] {
    if lines.contains(want) { passed += 1 } else { failed += 1; print("DIFFERS: no \"\(want)\" in:\n\(lines)") }
}
// a rule the checker cannot read must stop, never pass
let bad: [String: Any] = ["rules": [["id": "x", "scope": ["installed"], "match": ["gpu_vendr": "AMD"], "expect": []]]]
var threw = false
do { _ = try EfiRules.check([:], facts: [:], scope: "installed", rules: bad) } catch { threw = true }
if !threw { failed += 1; print("DIFFERS: an unknown match key passed instead of stopping") }
print("\(passed) cases agree with the Python checker, \(failed) differ")
exit(failed == 0 ? 0 : 1)
