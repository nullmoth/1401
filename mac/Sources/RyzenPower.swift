// 1401
// Copyright (c) 2026 NullMoth Systems. SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

import Foundation

/// The command line the Ryzen laptop power profile script (nullmoth-ryzen-power.sh) is run with. The numbers are checked
/// here as well as in the script, which also decides which RyzenAdj builds may be installed (ryzenadj.sha256).
enum RyzenPower {
    static func arguments(op: String, stapm: Int, slow: Int, fast: Int, temp: Int, ryzenadj: String?) -> (args: [String]?, why: String?) {
        switch op {
        case "remove", "status": return ([op], nil)
        case "install":
            guard (5...65).contains(stapm), (5...65).contains(slow), (5...65).contains(fast), stapm <= slow, slow <= fast else {
                return (nil, "Watts must be 5 to 65, with sustained at most slow at most fast.") }
            guard (50...100).contains(temp) else { return (nil, "The temperature limit must be 50 to 100 C.") }
            guard let p = ryzenadj, !p.isEmpty else { return (nil, "Choose a RyzenAdj build.") }
            return (["install", "--ryzenadj", p, "--stapm", "\(stapm)", "--slow", "\(slow)", "--fast", "\(fast)", "--temp", "\(temp)"], nil)
        default: return (nil, "Unknown Ryzen power action.")
        }
    }
}
