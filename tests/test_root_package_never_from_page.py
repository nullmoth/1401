"""A root action never takes its integrity check from the page: the page may name a package, the app resolves it against
its own list and hands setup the SHA-256 compiled into the app (PackagePin). Static pins on main.swift; the behaviour is
tested in mac/tests/package_pin (Swift)."""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MAIN = (ROOT / "mac/Sources/main.swift").read_text()
PIN = (ROOT / "mac/Sources/PackagePin.swift").read_text()


class RootPackages(unittest.TestCase):
    def test_no_hash_is_taken_of_a_path_the_page_sent(self):
        self.assertEqual(re.findall(r"sha256\(URL\(fileURLWithPath: pk\)\)", MAIN), [])
        self.assertEqual(re.findall(r'let sha = sha256\(URL\(fileURLWithPath: ', MAIN), [])

    def test_hybrid_ryzen_boost_tahoe_and_direct_runs_resolve_through_the_pin(self):
        for marker in ('"--hybrid", level, "--pkg", pkg.path, "--sha", pkg.sha', '"--ryzen-power", "on", "--ryzen-limits", limits, "--pkg", pkg.path, "--sha", pkg.sha',
                       '"--gpu-boost", "on", "--pkg", pkg.path, "--sha", pkg.sha', 'run(mode: "tahoe", pkg: pkg.path',
                       'run(mode: mode, pkg: pkg.path'):
            self.assertIn(marker, MAIN)
        self.assertEqual(MAIN.count("rootPackage("), 6)   # the definition and five handlers

    def test_the_pin_is_the_apps_compiled_in_sha_and_the_candidates_are_the_apps_own_list(self):
        self.assertIn("pinnedSha: Package.sha256", MAIN)
        self.assertIn("App.findPackages().compactMap", MAIN)
        self.assertIn("hash(path)?.lowercased() == pinnedSha.lowercased()", PIN)

    def test_every_pkg_argument_in_main_is_a_resolved_one(self):
        for m in re.finditer(r'"--pkg", ([^,\]]+)', MAIN):
            self.assertIn(m.group(1).strip(), ("pkg.path", "path", "pkg"), m.group(0))


if __name__ == "__main__":
    unittest.main()
