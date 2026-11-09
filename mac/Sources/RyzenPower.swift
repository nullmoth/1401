// 1401
// Copyright (c) 2026 NullMoth Systems. SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

import Foundation

/// The limits the Ryzen power profile is turned on with, as setup's --ryzen-limits wants them: sustained:slow:fast:temperature.
/// Checked here as well as in setup, which also decides which RyzenAdj build may be installed (the pinned one the package carries).
enum RyzenPower {
    static func limits(stapm: Int, slow: Int, fast: Int, temp: Int) -> (limits: String?, why: String?) {
        guard (5...65).contains(stapm), (5...65).contains(slow), (5...65).contains(fast), stapm <= slow, slow <= fast else {
            return (nil, "Watts must be 5 to 65, with sustained at most slow at most fast.") }
        guard (50...100).contains(temp) else { return (nil, "The temperature limit must be 50 to 100 C.") }
        return ("\(stapm):\(slow):\(fast):\(temp)", nil)
    }
}
