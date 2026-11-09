import Foundation

var failures = 0
func arm(_ name: String, _ ok: Bool) { print((ok ? "  ok   " : "  FAIL ") + name); if !ok { failures += 1 } }

let good = RyzenPower.arguments(op: "install", stapm: 13, slow: 14, fast: 15, temp: 70, ryzenadj: "/tmp/ryzenadj")
arm("a valid install passes every limit to the script", good.args == ["install", "--ryzenadj", "/tmp/ryzenadj", "--stapm", "13", "--slow", "14", "--fast", "15", "--temp", "70"])
arm("remove and status take no options", RyzenPower.arguments(op: "remove", stapm: 0, slow: 0, fast: 0, temp: 0, ryzenadj: nil).args == ["remove"]
    && RyzenPower.arguments(op: "status", stapm: 0, slow: 0, fast: 0, temp: 0, ryzenadj: nil).args == ["status"])
arm("watts outside 5 to 65 are refused", RyzenPower.arguments(op: "install", stapm: 4, slow: 14, fast: 15, temp: 70, ryzenadj: "/x").args == nil
    && RyzenPower.arguments(op: "install", stapm: 13, slow: 14, fast: 66, temp: 70, ryzenadj: "/x").args == nil)
arm("sustained above slow, or slow above fast, is refused", RyzenPower.arguments(op: "install", stapm: 20, slow: 14, fast: 25, temp: 70, ryzenadj: "/x").args == nil
    && RyzenPower.arguments(op: "install", stapm: 13, slow: 30, fast: 20, temp: 70, ryzenadj: "/x").args == nil)
arm("a temperature outside 50 to 100 is refused", RyzenPower.arguments(op: "install", stapm: 13, slow: 14, fast: 15, temp: 49, ryzenadj: "/x").args == nil
    && RyzenPower.arguments(op: "install", stapm: 13, slow: 14, fast: 15, temp: 101, ryzenadj: "/x").args == nil)
arm("an install with no build chosen is refused", RyzenPower.arguments(op: "install", stapm: 13, slow: 14, fast: 15, temp: 70, ryzenadj: nil).args == nil
    && RyzenPower.arguments(op: "install", stapm: 13, slow: 14, fast: 15, temp: 70, ryzenadj: "").args == nil)
arm("an unknown action is refused", RyzenPower.arguments(op: "rm -rf", stapm: 13, slow: 14, fast: 15, temp: 70, ryzenadj: "/x").args == nil)
if failures > 0 { exit(1) }
