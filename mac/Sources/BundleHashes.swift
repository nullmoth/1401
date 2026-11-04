// The list build.sh compiles into the app has the SHA-256 of every file in Contents/Resources.
// This empty one is for code compiled without build.sh; with it, Privileged.bundleScript refuses to run anything.
enum BundleHashes {
    static let table: [String: String] = [:]
}
