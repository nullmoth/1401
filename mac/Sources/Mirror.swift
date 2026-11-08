import Foundation

// When GitHub's download servers fail (11-08: every github.com release download answered 504 for hours while its API
// still answered), the same release file comes from the site's static copy. Trust does not change: a file from the
// mirror passes the same SHA-256 and Ed25519 release-signature checks as one from GitHub, or it is refused.
let mirrorBase = "https://nullmothsystems.com/download/nvidia/"
func mirrorURL(_ u: URL) -> URL? {
    guard u.scheme == "https", u.host == "github.com" else { return nil }
    let p = u.path.split(separator: "/", omittingEmptySubsequences: false).map(String.init)
    // "", nullmoth, nvidia-macos-driver, releases, download, v<version>, <file>
    guard p.count == 7, p[1] == "nullmoth", p[2] == "nvidia-macos-driver", p[3] == "releases", p[4] == "download",
          p[5].range(of: #"^v[0-9]+(\.[0-9]+)*$"#, options: .regularExpression) != nil,
          p[6].range(of: #"^[A-Za-z0-9][A-Za-z0-9._-]*$"#, options: .regularExpression) != nil else { return nil }
    return URL(string: mirrorBase + p[5] + "/" + p[6])
}
