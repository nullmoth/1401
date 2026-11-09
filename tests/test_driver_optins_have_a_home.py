"""Every driver-side opt-in switch merged for 2.9 either has a control in the Mac app or is listed here as tester-only with the
reason. The names come from the driver tree when it is beside this one (NULLMOTH_DRIVER, or rel/driver-29): any boot argument
of the families below that the driver reads and this table does not know fails the test, so a new switch cannot ship unlisted."""
import os
import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MAC = "".join(p.read_text(errors="replace") for p in list((ROOT / "mac/Sources").glob("*.swift")) + list((ROOT / "mac/Resources").glob("*"))
              if p.is_file() and p.suffix in (".swift", ".sh", ".js", ".html"))

# name -> where the Mac app turns it on (a string that must appear in the app's own files)
CONTROL = {
    "nmsmn": "--ryzen-power",            # the Ryzen power profile pane writes nmsmn=1
    "nmhybrid": "--hybrid",              # the hybrid laptop pane writes nmhybrid=1|2
    "nmxamd": "--gpu-test",              # the AMD / Intel test driver switch writes nmxamd / nmxintel
    "nmxintel": "--gpu-test",
    "nmxnpu": "--gpu-test",
    # the Experimental features pane (setup --experimental); each is off until ticked and needs a restart
    "nmkbl": "--experimental", "nmkblhid": "--experimental", "nvrmtgp": "--experimental", "nvrmgps": "--experimental",
    "nvrmnvpcf": "--experimental", "nvfbigpu": "--experimental", "nmxvt": "--experimental",
    "NVMTL_GAME_GPU_PRIORITY": "--experimental", "NVK_HWRT_QUERY": "--experimental", "NVK_CURVES": "--experimental",
    "NVMTL_TILE_SHADING": "--experimental", "NVMTL_GPU_ICB": "--experimental",
}
# name -> why it has no control in the app. Each is off unless set; none is needed for a machine to work.
TESTER_ONLY = {
    "nmkblforce": "forces nmkbl on a keyboard the kext does not recognise; a diagnostic for testers",
    "nmhybriddelay": "wait of 0 to 120 seconds before the hybrid panel driver takes the panel; a refinement of the hybrid pane's mode that testers set by hand when a machine froze without it",
    "nmhybriddmc": "loads Intel's display firmware in the hybrid panel driver through a root helper and pinned downloads; testers only until measured on hardware",
    "nmhybridresume": "sleep and wake handling of the hybrid panel driver; a tester switch beside the hybrid pane's mode",
    "NVMTL_HWRT": "per-process switch that turns hardware ray tracing on for the Cyberpunk profile only (plugin/nvmtl_app_profile.h); off by default",
}
FAMILY = re.compile(r"^(nmkbl\w*|nmx\w*|nmhybrid\w*|nvrm(?:tgp|gps|nvpcf)|nvfbigpu|nmsmn)$")


def driver_tree():
    for c in (os.environ.get("NULLMOTH_DRIVER"), str(ROOT.parent / "driver-29")):
        if c and (pathlib.Path(c) / "kexts").is_dir():
            return pathlib.Path(c)
    return None


class OptIns(unittest.TestCase):
    def test_every_control_is_really_in_the_app(self):
        for name, marker in CONTROL.items():
            self.assertIn(marker, MAC, f"{name}: the app has no {marker}")
            self.assertTrue(name == "nmsmn" or name in (ROOT / "mac/Resources/nullmoth-setup.sh").read_text() or name.startswith("nmx") or name == "nmhybrid", name)
        # the pane's items are exactly the ones above, in the page, in Swift and in setup
        page = (ROOT / "mac/Resources/index.html").read_text()
        ids = re.findall(r'class="expitem" id="exp-(\w+)"', page)
        self.assertEqual(sorted(ids), sorted(re.findall(r'"(\w+)"', re.search(r"static let ids: \[String\] = \[([^\]]*)\]", (ROOT / "mac/Sources/Experimental.swift").read_text()).group(1))))
        setup = (ROOT / "mac/Resources/nullmoth-setup.sh").read_text()
        for i in ids:
            self.assertRegex(setup, rf"\b{i}\)")
        blk = setup[setup.index('if [ -n "${EXPER:-}" ]; then'):setup.index('if [ -n "${GPUBOOST:-}" ]; then')]
        self.assertNotIn("FETCH_COPY", page + blk)
        self.assertNotIn("fetchcopy", (page + blk).replace("fetch-copy switch", "").lower())

    def test_every_tester_only_switch_names_its_reason(self):
        for name, why in TESTER_ONLY.items():
            self.assertGreater(len(why), 40, name)
            self.assertNotIn(name, CONTROL)
            self.assertNotIn(f'"{name}', (ROOT / "mac/Sources/main.swift").read_text(), f"{name} has a control now: move it to CONTROL")

    def test_no_boot_argument_of_these_families_in_the_driver_is_unlisted(self):
        tree = driver_tree()
        if tree is None:
            self.skipTest("the driver tree (NULLMOTH_DRIVER, or ../driver-29) is needed to list its boot arguments")
        out = subprocess.run(["git", "-C", str(tree), "grep", "-h", "-o", "-E", r'PE_parse_boot_argn\("[A-Za-z0-9_-]+"', "--", "kexts"],
                             capture_output=True, text=True).stdout
        names = {m.group(1) for m in re.finditer(r'"([A-Za-z0-9_-]+)"', out)}
        names = {n for n in names if FAMILY.match(n)}
        self.assertGreaterEqual(len(names), 3, "the scan found too few names to trust")
        unlisted = sorted(n for n in names if n not in CONTROL and n not in TESTER_ONLY)
        self.assertEqual(unlisted, [], "give each an app control or a tester-only line with its reason")


if __name__ == "__main__":
    unittest.main()
