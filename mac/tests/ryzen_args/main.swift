import Foundation

var failures = 0
func arm(_ name: String, _ ok: Bool) { print((ok ? "  ok   " : "  FAIL ") + name); if !ok { failures += 1 } }

arm("valid limits become sustained:slow:fast:temperature", RyzenPower.limits(stapm: 13, slow: 14, fast: 15, temp: 70).limits == "13:14:15:70")
arm("the edges are accepted", RyzenPower.limits(stapm: 5, slow: 5, fast: 65, temp: 50).limits == "5:5:65:50" && RyzenPower.limits(stapm: 65, slow: 65, fast: 65, temp: 100).limits == "65:65:65:100")
arm("watts outside 5 to 65 are refused", RyzenPower.limits(stapm: 4, slow: 14, fast: 15, temp: 70).limits == nil && RyzenPower.limits(stapm: 13, slow: 14, fast: 66, temp: 70).limits == nil)
arm("sustained above slow, or slow above fast, is refused", RyzenPower.limits(stapm: 20, slow: 14, fast: 25, temp: 70).limits == nil && RyzenPower.limits(stapm: 13, slow: 30, fast: 20, temp: 70).limits == nil)
arm("a temperature outside 50 to 100 is refused", RyzenPower.limits(stapm: 13, slow: 14, fast: 15, temp: 49).limits == nil && RyzenPower.limits(stapm: 13, slow: 14, fast: 15, temp: 101).limits == nil)
arm("the page's missing numbers (-1) are refused", RyzenPower.limits(stapm: -1, slow: -1, fast: -1, temp: -1).limits == nil)
if failures > 0 { exit(1) }
