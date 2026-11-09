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
if failures > 0 { exit(1) }
