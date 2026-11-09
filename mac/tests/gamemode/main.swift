import Foundation

// GameModeService builds the root command for the bundled service script and reads its status line.
var failures = 0
func arm(_ name: String, _ ok: Bool, _ detail: String = "") {
    print((ok ? "  ok   " : "  FAIL ") + name + (detail.isEmpty ? "" : "   [\(detail)]"))
    if !ok { failures += 1 }
}

let res = URL(fileURLWithPath: "/Applications/1401.app/Contents/Resources")
let table = ["nullmoth-gamemode-service.sh": "a", "nullmoth-gamemode-policy.py": "b", "nullmoth-gamemode-indicator": "c"]

let install = GameModeService.command("install", resources: res, table: table) ?? ""
arm("install runs the checked service script with the two files it installs", install.contains("nullmoth-gamemode-service.sh") && install.contains("install")
    && install.contains("nullmoth-gamemode-policy.py") && install.contains("nullmoth-gamemode-indicator"))
arm("the files are passed as paths into the verified private copy, not the bundle", install.contains("\"$r\"/"))
let remove = GameModeService.command("remove", resources: res, table: table) ?? ""
arm("remove runs the same checked script with only the word remove after it", remove.contains("'nullmoth-gamemode-service.sh' 'remove'; rc=$?"))
arm("any other word is refused", GameModeService.command("restart", resources: res, table: table) == nil && GameModeService.command("", resources: res, table: table) == nil)
let unknown = GameModeService.command("install", resources: res, table: ["other.sh": "x"]) ?? ""
arm("a build with no hash for the script refuses to run it", unknown.contains("has no check for"))

arm("status: installed and running", GameModeService.parse("installed , running") == (true, true))
arm("status: installed but stopped", GameModeService.parse("installed , stopped") == (true, false))
arm("status: not installed", GameModeService.parse("not installed , stopped") == (false, false))
arm("status: noise reads as nothing installed", GameModeService.parse("") == (false, false))

if failures > 0 { print("\(failures) failed"); exit(1) }
print("all ok")
