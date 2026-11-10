"""Every driver-side opt-in switch merged for 2.9 either has a control in the Mac app or is listed here as tester-only with the
reason. The names come from the driver tree when it is beside this one (NULLMOTH_DRIVER, or rel/driver-29): any boot argument
of the families below that the driver reads and this table does not know fails the test, so a new switch cannot ship unlisted."""
import os
import pathlib
import re
import subprocess
import tempfile
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
    "nvrmnvpcf": "--experimental", "nvfbigpu": "--experimental", "nmxvt": "--experimental", "nmhybrid20": "--experimental", "nvrtd3": "--experimental", "nvrmaspm": "--experimental",
    "NVMTL_GAME_GPU_PRIORITY": "--experimental", "NVK_HWRT_QUERY": "--experimental", "NVK_CURVES": "--experimental",
    "NVMTL_TILE_SHADING": "--experimental", "NVMTL_GPU_ICB": "--experimental",
}
# name -> why it has no control in the app. Each is off unless set; none is needed for a machine to work.
TESTER_ONLY = {
    "nmkblforce": "forces nmkbl on a keyboard the kext does not recognise; a diagnostic for testers",
    "nmhybridp2p": "zero-copy scan-out of a frame straight from the NVIDIA GPU's BAR1 (1 = only on a known-good host bridge, 2 = forced); the allowlist is empty and it has never run, so a tester switch",
    "nmhybridext": "lights a plugged Type-C monitor with colour bars on a second pipe (versions 12 and 13): a bring-up test for the hybrid panel driver's external heads, not a display feature yet, so testers only",
    "nmhybridtc": "logs Type-C cable events in the hybrid panel driver (display versions 12 and 13); diagnostic output for testers",
    "nmhybriddelay": "wait of 0 to 120 seconds before the hybrid panel driver takes the panel; a refinement of the hybrid pane's mode that testers set by hand when a machine froze without it",
    "nmhybriddmc": "loads Intel's display firmware in the hybrid panel driver through a root helper and pinned downloads; testers only until measured on hardware",
    "nmhybridresume": "sleep and wake handling of the hybrid panel driver; a tester switch beside the hybrid pane's mode",
    "NVMTL_HWRT": "per-process switch that turns hardware ray tracing on for the Cyberpunk profile only (plugin/nvmtl_app_profile.h); off by default",
}
def _group(reason, *names):
    for n in names:
        TESTER_ONLY[n] = reason


_group("recovery valve: switches one driver feature off when it misbehaves on a machine; support gives it out for that machine and nothing needs it otherwise",
       "nmdrmoff", "nmgopfboff", "nmintelfboff", "nvaccelnoheadless", "nvrmnoaspm", "nvrmnobootscreen", "nvrmnodpms", "nvrmnoflip",
       "nvrmnogamma", "nvrmnogo", "nvrmnopm", "nvrmnoshutdown", "nvrmsmallbar", "nvrmkeepbar1", "nvrmmapowner")
_group("diagnostic output or probe for support: it prints or measures more and changes no behaviour a user would want to choose",
       "nvfblog", "nvfbtrace", "nvaccelverbose", "nvrmdiag", "nvfbsurvey", "nvfbsample", "nvfbscalerprobe", "nvregdwords", "nvhud", "liludelay")
_group("tuning value support sets for one machine after a report (timing, caching, probing); the default is right for everyone else",
       "nvfbbootretry", "nvfbhotplugpoll", "nvfbigpucache", "nvfbkeepfront", "nvfbsmall", "nvhwvbl", "nvmaxbpc", "nvcursor", "nvagdcheads",
       "nvselector", "nvoffbar", "nvrmfbddc", "nvrmholdcap", "nvrmshutdown", "nmflatskip", "nmgopid", "nmhdavol")
_group("the ACPI resource name runtime D3 (the Idle GPU deep sleep item) uses on machines that need it spelled out; set by support with nvrtd3 on that machine",
       "nvrtd3res")
_group("AMD / Intel test driver (NMXGPU) tuning, hang and recovery values and display options; the test driver's switch is the only control, "
       "and these refine it for testers",
       "nmxamd_hang_ms", "nmxamd_native", "nmxamd_recover", "nmxamd_wake", "nmxintel_floor", "nmxintel_native", "nmxi915_guc",
       "nmxfb_backlight", "nmxfb_hidpi", "nmxfb_gamma", "nmxfb_hdr", "nmxfb_modes", "nmxfb_outputs", "nmxfb_tile", "alcid", "alcverbs", "nmxaudio")


STATEMENT = re.compile(r"PE_parse_boot_argn|lilu_get_boot_args|[Bb]oot_?[Aa]rg|\barg[A-Z]\w*\s*\(|\b\w*Arg(?:On|Int|Bool|Val)\w*\s*\(")
LITERAL = re.compile(r'"(-?[A-Za-z][A-Za-z0-9_-]{1,40})"')
OLD_SCANNER = re.compile(r'PE_parse_boot_argn\("([A-Za-z0-9_-]+)"')


def boot_arg_names(text):
    """Every boot-argument name a source file reads: each string literal anywhere in a statement that calls PE_parse_boot_argn,
    lilu_get_boot_args or a boot-arg helper (a name with boot arg in it, or argOn( style), on one line or spread over several."""
    names = set()
    for statement in re.split(r"[;{}]", text):
        if STATEMENT.search(statement):
            names.update(m.group(1).lstrip("-") for m in LITERAL.finditer(statement))
    return names


def old_names(text):
    return set(OLD_SCANNER.findall(text))


# the exact line shapes the old scanner missed or could miss: a literal that is not first after the call, a call over two
# lines, a helper that wraps the read, and the lilu form
SHAPES = """
{ int fv = 0; const int present = PE_parse_boot_argn("nmflatskip", &fv, sizeof fv); if (present) ALOG("x"); }
static bool on(void) { return PE_parse_boot_argn(
        "nvfbwrapped", &v, sizeof v) && v; }
if (bootArgOn("nvfbhelper")) { }
lilu_get_boot_args("liludelay", &d, sizeof d);
if (nvArgOn("nvfbhelper2")) { }
DBGLOG("nmkblnotanarg", "this is only a log tag");
"""


def head_of(root):
    r = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def tree(env, *defaults):
    """(path, how): the folder named by the environment variable, else the first default that exists. A folder the variable names
    must be a git checkout with a HEAD; one that is not is an error, never a quiet skip."""
    named = os.environ.get(env)
    if named:
        return pathlib.Path(named), "env"
    for c in defaults:
        if c and pathlib.Path(c).is_dir():
            return pathlib.Path(c), "default"
    return None, "none"


def checked_tree(test, env, *defaults, marker=None):
    root, how = tree(env, *defaults)
    if root is None:
        test.skipTest(f"no tree to scan: set {env}, or put one at {defaults[-1] if defaults else '?'}")
    if how == "env":
        test.assertTrue((root / ".git").exists(), f"{env}={root} is not a git checkout (no .git): the scan would read an unknown copy")
    head = head_of(root)
    test.assertTrue(head, f"{root} has no readable git HEAD: the scan would read an unknown copy")
    print(f"[scanning {root} at {head}]")
    if marker:
        test.assertTrue((root / marker).is_file(), f"{root} at {head} lacks {marker}: this is not the tree the audit is for")
    return root


def driver_tree():
    t, _ = tree("NULLMOTH_DRIVER", str(ROOT.parent / "driver-29"))
    return t


def nmx_tree():
    t, _ = tree("NULLMOTH_NMX", str(pathlib.Path.home() / "Work/nullmoth/nmx-rel-29-nmx"))
    return t


def names_in(root, sub=None):
    out = subprocess.run(["git", "-C", str(root), "ls-files"] + ([sub] if sub else []), capture_output=True, text=True).stdout.split()
    names = set()
    for f in out:
        if f.endswith((".cpp", ".h", ".hpp", ".c", ".m", ".mm", ".cc")):
            names |= boot_arg_names((root / f).read_text(errors="replace"))
    return names


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

    def test_a_tree_variable_that_points_at_a_non_checkout_fails_loudly(self):
        plain = tempfile.mkdtemp()
        old = os.environ.get("NULLMOTH_DRIVER")
        os.environ["NULLMOTH_DRIVER"] = plain
        try:
            with self.assertRaises(AssertionError) as c:
                checked_tree(self, "NULLMOTH_DRIVER", marker="kexts/x.cpp")
            self.assertIn("not a git checkout", str(c.exception))
            subprocess.run(["git", "-C", plain, "init", "-q"], check=True)
            with self.assertRaises(AssertionError) as c:       # a checkout with no commit has no HEAD
                checked_tree(self, "NULLMOTH_DRIVER", marker="kexts/x.cpp")
            self.assertIn("no readable git HEAD", str(c.exception))
        finally:
            if old is None:
                os.environ.pop("NULLMOTH_DRIVER", None)
            else:
                os.environ["NULLMOTH_DRIVER"] = old

    def test_the_scanner_finds_every_line_shape_and_the_old_one_does_not(self):
        found = boot_arg_names(SHAPES)
        self.assertEqual(found, {"nmflatskip", "nvfbwrapped", "nvfbhelper", "liludelay", "nvfbhelper2"})
        self.assertNotIn("nmkblnotanarg", found)                         # a log tag in a statement with no boot-arg read
        missed = found - old_names(SHAPES)
        self.assertTrue({"nvfbwrapped", "nvfbhelper", "liludelay", "nvfbhelper2"} <= missed, missed)
        # a minus flag is the same name
        self.assertEqual(boot_arg_names('if (PE_parse_boot_argn("-nvrmnoflip", nb, sizeof(nb))) {}'), {"nvrmnoflip"})

    def _unlisted(self, names):
        mac = MAC + "".join(p.read_text(errors="replace") for p in (ROOT / "mac/Resources").glob("*.json"))
        return sorted(n for n in names if n not in CONTROL and n not in TESTER_ONLY
                      and not re.search(r"(?<![A-Za-z0-9_])" + re.escape(n) + r"(?![A-Za-z0-9_])", mac))

    def test_no_boot_argument_the_driver_reads_is_unlisted(self):
        tree_ = checked_tree(self, "NULLMOTH_DRIVER", str(ROOT.parent / "driver-29"), marker="kexts/NVRM/accel/nvrm-accel.cpp")
        names = names_in(tree_, "kexts")
        self.assertGreaterEqual(len(names), 60, "the scan found too few names to trust")
        self.assertEqual(self._unlisted(names), [], "give each an app control or a tester-only line with its reason")

    def test_no_boot_argument_the_nmx_tree_reads_is_unlisted(self):
        tree_ = checked_tree(self, "NULLMOTH_NMX", str(pathlib.Path.home() / "Work/nullmoth/nmx-rel-29-nmx"))
        names = names_in(tree_)
        self.assertGreaterEqual(len(names), 10)
        self.assertEqual(self._unlisted(names), [], "give each an app control or a tester-only line with its reason")


if __name__ == "__main__":
    unittest.main()
