import Foundation

var failures = 0
func arm(_ name: String, _ ok: Bool) { print((ok ? "  ok   " : "  FAIL ") + name); if !ok { failures += 1 } }

let pin = String(repeating: "a", count: 64)
let known = "/Volumes/Data/Downloads/nullmoth-nvidia-2.8.1.tar.gz"
let hashes = [known: pin, "/tmp/evil.tar.gz": String(repeating: "b", count: 64), "/tmp/same-as-itself.tar.gz": String(repeating: "c", count: 64)]
let hash: (String) -> String? = { hashes[$0] }

let ok = PackagePin.resolve(requested: known, candidates: [known], pinnedSha: pin, hash: hash)
arm("the app's own package that hashes to the pin is accepted, with the PIN as the sha", ok?.path == known && ok?.sha == pin)
arm("a page-supplied path to a file the app did not list is refused", PackagePin.resolve(requested: "/tmp/evil.tar.gz", candidates: [known], pinnedSha: pin, hash: hash) == nil)
arm("a file whose own hash is not the pin is refused even if it is listed", PackagePin.resolve(requested: "/tmp/evil.tar.gz", candidates: ["/tmp/evil.tar.gz"], pinnedSha: pin, hash: hash) == nil)
arm("a file is never checked against its own hash (the old behaviour accepted this)",
    PackagePin.resolve(requested: "/tmp/same-as-itself.tar.gz", candidates: ["/tmp/same-as-itself.tar.gz"], pinnedSha: pin, hash: hash) == nil)
arm("an empty request, an empty pin and an unreadable file are refused",
    PackagePin.resolve(requested: "", candidates: [known], pinnedSha: pin, hash: hash) == nil
    && PackagePin.resolve(requested: known, candidates: [known], pinnedSha: "", hash: hash) == nil
    && PackagePin.resolve(requested: known, candidates: [known], pinnedSha: pin, hash: { _ in nil }) == nil)
arm("a path that reaches the listed package through .. is the same file and is accepted",
    PackagePin.resolve(requested: "/Volumes/Data/Downloads/../Downloads/nullmoth-nvidia-2.8.1.tar.gz", candidates: [known], pinnedSha: pin, hash: hash)?.sha == pin)
arm("a path that merely starts like a listed one is refused",
    PackagePin.resolve(requested: known + ".evil", candidates: [known], pinnedSha: pin, hash: hash) == nil)
if failures > 0 { exit(1) }
