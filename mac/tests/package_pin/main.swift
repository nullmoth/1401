import Foundation

var failures = 0
func arm(_ name: String, _ ok: Bool) { print((ok ? "  ok   " : "  FAIL ") + name); if !ok { failures += 1 } }

let pin = String(repeating: "a", count: 64)
let good = "/Volumes/Data/Downloads/nullmoth-nvidia-2.8.1.tar.gz"
let planted = "/tmp/planted.tar.gz"
let hashes = [good: pin, planted: String(repeating: "b", count: 64)]
let hash: (String) -> String? = { hashes[$0] }

arm("the package that hashes to the pin is chosen, with the PIN as the sha", PackagePin.choose(candidates: [good], pinnedSha: pin, hash: hash)?.path == good
    && PackagePin.choose(candidates: [good], pinnedSha: pin, hash: hash)?.sha == pin)
arm("a planted file is skipped and the genuine one after it is chosen", PackagePin.choose(candidates: [planted, good], pinnedSha: pin, hash: hash)?.path == good)
arm("when only a file that does not hash to the pin exists, nothing is chosen (hybrid, ryzenpower, GPU boost and the rest are refused)",
    PackagePin.choose(candidates: [planted], pinnedSha: pin, hash: hash) == nil)
arm("a file is never judged by its own hash: whatever the hash is, if it is not the pin it is refused",
    PackagePin.choose(candidates: ["/tmp/x"], pinnedSha: pin, hash: { _ in String(repeating: "c", count: 64) }) == nil)
arm("an empty pin, an empty list and unreadable files choose nothing",
    PackagePin.choose(candidates: [good], pinnedSha: "", hash: hash) == nil && PackagePin.choose(candidates: [], pinnedSha: pin, hash: hash) == nil
    && PackagePin.choose(candidates: [good], pinnedSha: pin, hash: { _ in nil }) == nil)
arm("the comparison ignores case", PackagePin.choose(candidates: [good], pinnedSha: pin.uppercased(), hash: hash)?.path == good)
if failures > 0 { exit(1) }
