import Foundation

var failures = 0
func arm(_ name: String, _ ok: Bool) { print((ok ? "  ok   " : "  FAIL ") + name); if !ok { failures += 1 } }

arm("nothing installed reads as not installed whatever the setting file says", GPUBoost.describe(installed: false, setting: "gpuboost=1").hasPrefix("Not installed"))
arm("installed with gpuboost=1 reads as on", GPUBoost.describe(installed: true, setting: "gpuboost=1").hasPrefix("On"))
arm("installed with gpuboost=0 reads as switched off", GPUBoost.describe(installed: true, setting: "gpuboost=0").hasPrefix("Installed, switched off"))
arm("a setting the daemon does not accept is named, not called on", GPUBoost.describe(installed: true, setting: "gpuboost=2").contains("does not accept")
    && !GPUBoost.describe(installed: true, setting: "gpuboost=2").hasPrefix("On"))
arm("no setting file is said so", GPUBoost.describe(installed: true, setting: nil).contains("no setting file"))
arm("the files read are the ones boost_daemon.sh uses", GPUBoost.binary == "/usr/local/libexec/nullmoth/nvmtl-boost" && GPUBoost.conf == "/Library/NullMoth/gpuboost"
    && GPUBoost.plist == "/Library/LaunchDaemons/com.nullmoth.nvmtl-boost.plist")
if failures > 0 { exit(1) }
