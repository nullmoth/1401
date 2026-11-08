// mirror: the site's copy is used only for NullMoth driver release files, keeps the version and file name exactly,
// and refuses every other address (another repository, another host, http, a path that climbs out, extra parts).
import Foundation
var failed = 0
func arm(_ ok: Bool, _ name: String) { print((ok ? "ok   " : "FAIL ") + name); if !ok { failed += 1 } }
let gh = "https://github.com/nullmoth/nvidia-macos-driver/releases/download/"
func m(_ s: String) -> String? { URL(string: s).flatMap(mirrorURL)?.absoluteString }
arm(m(gh + "v2.8/nullmoth-nvidia-2.8.tar.gz") == "https://nullmothsystems.com/download/nvidia/v2.8/nullmoth-nvidia-2.8.tar.gz",
    "a driver release package maps to the same version and file on the site")
arm(m(gh + "v2.8.1/1401-Mac-2.8.1.zip.bsig") == "https://nullmothsystems.com/download/nvidia/v2.8.1/1401-Mac-2.8.1.zip.bsig",
    "a three-part version and a signature file keep their exact names")
arm(m(gh + "v2.8/SHA256SUMS.txt") != nil, "SHA256SUMS.txt has a mirror")
arm(m("https://github.com/nullmoth/1401/releases/download/v2.8/1401-Windows-2.8.zip") == nil, "another repository has no mirror")
arm(m("https://github.com/evil/nvidia-macos-driver/releases/download/v2.8/x.tar.gz") == nil, "another owner has no mirror")
arm(m("https://example.com/nullmoth/nvidia-macos-driver/releases/download/v2.8/x.tar.gz") == nil, "another host has no mirror")
arm(m("http://github.com/nullmoth/nvidia-macos-driver/releases/download/v2.8/x.tar.gz") == nil, "plain http has no mirror")
arm(m(gh + "v2.8/../../../etc/passwd") == nil, "a path that climbs out has no mirror")
arm(m(gh + "v2.8/a/b.tar.gz") == nil, "an extra path part has no mirror")
arm(m(gh + "latest/x.tar.gz") == nil, "a non-version tag has no mirror")
arm(m(gh + "v2.8/.hidden") == nil, "a hidden file name has no mirror")
arm(m(gh + "v2.8/%2e%2e") == nil, "an encoded dot-dot has no mirror")
print(failed == 0 ? "mirror: all arms hold" : "mirror: \(failed) FAILED"); exit(failed == 0 ? 0 : 1)
