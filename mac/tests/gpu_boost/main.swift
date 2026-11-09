import Foundation

var failures = 0
func arm(_ name: String, _ ok: Bool) { print((ok ? "  ok   " : "  FAIL ") + name); if !ok { failures += 1 } }

arm("nothing installed reads as not installed whatever the setting file says", GPUBoost.describe(installed: false, setting: "gpuboost=1").hasPrefix("Not installed"))
arm("installed with gpuboost=1 reads as on", GPUBoost.describe(installed: true, setting: "gpuboost=1").hasPrefix("On"))
arm("installed with gpuboost=0 reads as switched off", GPUBoost.describe(installed: true, setting: "gpuboost=0").hasPrefix("Installed, switched off"))
arm("a setting the daemon does not accept is named, not called on", GPUBoost.describe(installed: true, setting: "gpuboost=2").contains("does not accept")
    && !GPUBoost.describe(installed: true, setting: "gpuboost=2").hasPrefix("On"))
arm("no setting file is said so", GPUBoost.describe(installed: true, setting: nil).contains("no setting file"))
func plistData(_ args: [String]) -> Data { try! PropertyListSerialization.data(fromPropertyList: ["Label": "x", "ProgramArguments": args], format: .xml, options: 0) }
arm("the program is read from the job's plist, wherever the package puts it",
    GPUBoost.program(plistData: plistData(["/Library/PrivilegedHelperTools/nvmtl-boost"])) == "/Library/PrivilegedHelperTools/nvmtl-boost"
    && GPUBoost.program(plistData: plistData(["/Library/NullMoth/boost/nvmtl-boost", "-v"])) == "/Library/NullMoth/boost/nvmtl-boost")
arm("a relative program, an empty list and a non-plist give none",
    GPUBoost.program(plistData: plistData(["nvmtl-boost"])) == nil && GPUBoost.program(plistData: plistData([])) == nil
    && GPUBoost.program(plistData: Data("junk".utf8)) == nil)
arm("the setting and job files are the ones boost_daemon.sh uses", GPUBoost.conf == "/Library/NullMoth/gpuboost"
    && GPUBoost.plist == "/Library/LaunchDaemons/com.nullmoth.nvmtl-boost.plist")
let rootDir: (Int, Int, Bool) = (0, 0o755, false)
let attrs: [String: (owner: Int, mode: Int, isLink: Bool)] = [
    "/Library": rootDir, "/Library/NullMoth": rootDir, "/Library/NullMoth/boost": rootDir, "/Library/NullMoth/boost/nvmtl-boost": (0, 0o755, false),
    "/Volumes": rootDir, "/Volumes/Data": (501, 0o755, false), "/Volumes/Data/bin": (501, 0o755, false),
    "/Library/Loose": (0, 0o775, false), "/Library/Loose/x": rootDir, "/Library/Link": (0, 0o755, true), "/Library/Link/x": rootDir]
let lookup: (String) -> (owner: Int, mode: Int, isLink: Bool)? = { attrs[$0] }
arm("a path of root-owned, non-writable directories is trusted", GPUBoost.trusted("/Library/NullMoth/boost/nvmtl-boost", attributes: lookup))
arm("a user-owned component is not trusted", !GPUBoost.trusted("/Volumes/Data/bin/nvmtl-boost", attributes: lookup))
arm("a group-writable component is not trusted", !GPUBoost.trusted("/Library/Loose/x", attributes: lookup))
arm("a symbolic link on the way is not trusted", !GPUBoost.trusted("/Library/Link/x", attributes: lookup))
arm("a missing component and a relative path are not trusted", !GPUBoost.trusted("/Library/NullMoth/none/x", attributes: lookup) && !GPUBoost.trusted("nvmtl-boost", attributes: lookup))
arm("an untrusted path reads as not usable, whatever the setting", GPUBoost.describe(installed: true, setting: "gpuboost=1", trusted: false).contains("not trusted")
    && !GPUBoost.describe(installed: true, setting: "gpuboost=1", trusted: false).hasPrefix("On"))
if failures > 0 { exit(1) }
