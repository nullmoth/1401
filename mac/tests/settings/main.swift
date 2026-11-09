import Foundation

// The settings engine against the command-line tool's own answers (vectors.json is that tool's output), plus the rules the
// window adds: nothing is written without a plan, hostile values never reach a shell, a conf survives a round trip.
var failed = 0
func check(_ ok: Bool, _ what: String) { if ok { print("ok   " + what) } else { failed += 1; print("FAIL " + what) } }

let dir = CommandLine.arguments[1]
let cat = DriverSettings.load(try! Data(contentsOf: URL(fileURLWithPath: dir + "/../../Resources/settings_catalog.json")))!
let vectors = try! JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: dir + "/vectors.json"))) as! [[String: Any]]
check(cat.settings.count == 17, "the catalogue holds the 17 settings the command-line tool has")

var bad: [String] = [], n = 0
for v in vectors {
    n += 1
    let fn = v["fn"] as! String
    switch fn {
    case "normalize":
        let s = cat.find(v["id"] as! String)!, val = v["value"] as! String
        var refused = false, got: String? = nil
        do { got = try DriverSettings.normalize(cat, s, val) } catch { refused = true }   // nil with no refusal = "default"
        if v["error"] != nil { if !refused { bad.append("normalize \(s.id) \(val.prefix(20)) should refuse") } }
        else {
            let want = v["expect"] as? String
            if refused || got != want { bad.append("normalize \(s.id) \(val.prefix(20)): got \(String(describing: got)) refused \(refused) want \(String(describing: want))") }
        }
    case "bootargs_set":
        let got = DriverSettings.bootargsSet(v["line"] as! String, v["key"] as! String, v["value"] as? String)
        if got != v["expect"] as! String { bad.append("bootargs_set \(v["line"]!) \(v["key"]!) -> \(got)") }
    case "bootargs_get":
        let got = DriverSettings.bootargsGet(v["line"] as! String, v["key"] as! String)
        if got != v["expect"] as? String { bad.append("bootargs_get \(v["line"]!) \(v["key"]!)") }
    case "conf_set":
        let got = DriverSettings.confSet(cat, v["text"] as! String, v["key"] as! String, v["value"] as? String)
        if got != v["expect"] as! String { bad.append("conf_set \(v["text"]!) \(v["key"]!) -> \(got)") }
    case "conf_get":
        let got = DriverSettings.confGet(cat, v["text"] as! String, v["key"] as! String)
        if got != v["expect"] as? String { bad.append("conf_get \(v["key"]!)") }
    default: bad.append("unknown vector \(fn)")
    }
}
check(bad.isEmpty, "all \(n) vectors from the command-line tool give the same answer here" + (bad.isEmpty ? "" : ": " + bad.prefix(5).joined(separator: " | ")))

let fps = cat.find("fps-limit")!, hdr = cat.find("hdr")!
// a plan only describes the change
let ba = "-v keepsyms=1 debug=0x144"
if case .bootArgs(let l)? = try? DriverSettings.plan(cat, hdr, "on", bootArgs: ba, conf: "") { check(l == ba + " nvfbhdr=1", "enabling HDR adds one boot argument and keeps the others") } else { check(false, "enabling HDR plans a boot-args change") }
check((try? DriverSettings.plan(cat, hdr, "on", bootArgs: "bad;arg $(x)", conf: "")) == nil, "a boot line with shell characters is never rewritten")
check((try? DriverSettings.plan(cat, fps, "60; rm -rf /", bootArgs: ba, conf: "")) == nil, "a frame limit with shell characters is refused before any command exists")
check((try? DriverSettings.plan(cat, fps, "5", bootArgs: ba, conf: "")) == nil, "a frame limit below 10 is refused")
// a shipped line that an update would drop makes the whole plan refuse, so the user's block never holds a line that vanishes
let wrong = cat.blockStart + "\nNVMTL_BAD=a b\n" + cat.blockEnd + "\n"
check((try? DriverSettings.plan(cat, fps, "60", bootArgs: ba, conf: wrong)) == nil, "a block holding a line an update would drop is not extended")

// the root command really writes the file, atomically, and survives hostile text in the conf it carries
let tmp = NSTemporaryDirectory() + "settings-test-" + UUID().uuidString
try! FileManager.default.createDirectory(atPath: tmp, withIntermediateDirectories: true)
let confPath = tmp + "/it's a conf.conf"      // a quote in the path is quoted correctly too
let local = DriverSettings.Catalog(confPath: confPath, blockStart: cat.blockStart, blockEnd: cat.blockEnd, kept: cat.kept, settings: cat.settings)
let original = "NVMTL_A=1\n# it's \"quoted\" $(touch \(tmp)/pwned) `touch \(tmp)/pwned2`\n"
try! original.write(toFile: confPath, atomically: true, encoding: .utf8)
guard case .conf(let newText) = try! DriverSettings.plan(local, fps, "Game=60,*=0", bootArgs: ba, conf: original) else { fatalError() }
let owner = "\(getuid()):\(getgid())"
let p = Process(); p.executableURL = URL(fileURLWithPath: "/bin/sh"); p.arguments = ["-c", DriverSettings.command(local, .conf(newText), owner: owner)]
try! p.run(); p.waitUntilExit()
let after = try! String(contentsOfFile: confPath, encoding: .utf8)
check(p.terminationStatus == 0 && after == newText, "the command writes exactly the planned conf")
check(after.contains("# it's \"quoted\" $(touch") && !FileManager.default.fileExists(atPath: tmp + "/pwned") && !FileManager.default.fileExists(atPath: tmp + "/pwned2"),
      "quotes, $( ) and backticks in the existing conf are written as text, never run")
check((try! FileManager.default.contentsOfDirectory(atPath: tmp)).count == 1, "no temporary file is left beside the conf")
check(DriverSettings.confGet(local, after, "NVMTL_FPS_LIMIT") == "Game=60,*=0", "the frame limit reads back from the file")
check(DriverSettings.command(cat, .bootArgs("a b=1")).hasPrefix("/usr/sbin/nvram boot-args='a b=1'"), "a boot-args change goes through nvram, quoted")
try? FileManager.default.removeItem(atPath: tmp)
print("\(failed) failed"); exit(failed == 0 ? 0 : 1)
