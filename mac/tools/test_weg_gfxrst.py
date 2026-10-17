#!/usr/bin/env python3
"""With WhateverGreen on in OpenCore, the setup adds gfxrst=4: WhateverGreen's boot screen copy reads an address macOS
can free before the NVIDIA display opens, and the Mac panics in IOFramebuffer::postOpen. A gfxrst the user set stays,
and removal takes out only a gfxrst=4 the install record says the setup added.

Runs the setup's real lines (sliced at their anchors) on fake configs."""
import os
import pathlib
import plistlib
import subprocess
import tempfile
import unittest

SETUP = pathlib.Path(__file__).resolve().parents[1] / "Resources/nullmoth-setup.sh"
B = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
ADD_START, ADD_END = "# WhateverGreen boot screen copy: begin", "# WhateverGreen boot screen copy: end"
REM_START = '      args=$(get NVRAM.Add.$B.boot-args); new=""\n      for a in $args; do\n        case "$a" in nvfb=*'
REM_END = 'plutil -replace NVRAM.Add.$B.boot-args -string "${new# }" "$C" || stop "could not stage boot arguments - nothing changed"'
OWN_START, OWN_END = "owned_amfi_from_prior_record() (", "\n)\n"


def kext(name, enabled=True):
    return {"Arch": "Any", "BundlePath": name, "Enabled": enabled, "ExecutablePath": "", "PlistPath": "Contents/Info.plist"}


def slice_of(start, end, include_end=True):
    s = SETUP.read_text()
    assert s.count(start) == 1, f"anchor moved: {start[:40]!r}"
    i = s.index(start)
    j = s.index(end, i)
    return s[i:j + (len(end) if include_end else 0)]


def config(tmp, kexts, args):
    c = os.path.join(tmp, "config.plist")
    with open(c, "wb") as f:
        plistlib.dump({"Kernel": {"Add": kexts}, "NVRAM": {"Add": {B: {"boot-args": args}}}}, f)
    return c


def bash(script):
    p = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return p.stdout


PRELUDE = 'get() { plutil -extract "$1" raw -o - "$C" 2>/dev/null; }; note() { echo "NOTE $*"; }; stop() { echo "STOP $*"; exit 1; }\n'


def install(kexts, args):
    """Runs the add slice after the setup has built `new` from the config's boot-args."""
    t = tempfile.mkdtemp()
    c = config(t, kexts, args)
    body = slice_of(ADD_START, ADD_END)
    out = bash(f'C="{c}"; B={B}\n{PRELUDE}new=" $(get NVRAM.Add.$B.boot-args)"; ADDED=""\n{body}\n'
               'echo "NEW=${new# }"; echo "ADDED=${ADDED# }"')
    lines = dict(l.split("=", 1) for l in out.splitlines() if l.startswith(("NEW=", "ADDED=")))
    return lines["NEW"].split(), lines["ADDED"].split(), out


def remove(args, added_args):
    t = tempfile.mkdtemp()
    c = config(t, [], args)
    body = slice_of(REM_START, REM_END)
    bash(f'C="{c}"; B={B}; ADDED_ARGS="{added_args}"; REMOVED_ARGS=""\n{PRELUDE}{body}\n')
    with open(c, "rb") as f:
        return plistlib.load(f)["NVRAM"]["Add"][B]["boot-args"].split()


class AddsGfxrst(unittest.TestCase):
    def test_whatevergreen_on_and_no_gfxrst_adds_it_and_records_it(self):
        new, added, out = install([kext("Lilu.kext"), kext("WhateverGreen.kext")], "-v nvfb=1")
        self.assertEqual(new[-1], "gfxrst=4")
        self.assertIn("gfxrst=4", added)
        self.assertEqual(out.count("NOTE "), 1, out)

    def test_whatevergreen_off_adds_nothing(self):
        new, added, out = install([kext("WhateverGreen.kext", enabled=False)], "-v nvfb=1")
        self.assertNotIn("gfxrst=4", new)
        self.assertEqual(added, [])
        self.assertNotIn("NOTE", out)

    def test_no_whatevergreen_adds_nothing(self):
        new, added, _ = install([kext("Lilu.kext")], "nvfb=1")
        self.assertEqual(new, ["nvfb=1"])
        self.assertEqual(added, [])

    def test_a_user_set_gfxrst_is_left_alone(self):
        new, added, _ = install([kext("WhateverGreen.kext")], "gfxrst=1 nvfb=1")
        self.assertEqual(new, ["gfxrst=1", "nvfb=1"])
        self.assertEqual(added, [])

    def test_an_existing_gfxrst4_is_not_claimed(self):
        new, added, _ = install([kext("WhateverGreen.kext")], "gfxrst=4")
        self.assertEqual(new, ["gfxrst=4"])
        self.assertEqual(added, [], "the setup did not add it, so removal must not take it")


class RemovesOnlyWhatItAdded(unittest.TestCase):
    def test_removal_takes_out_a_gfxrst4_the_setup_added(self):
        self.assertNotIn("gfxrst=4", remove("-v nvfb=1 gfxrst=4", "gfxrst=4"))

    def test_removal_keeps_a_gfxrst4_the_user_set(self):
        self.assertIn("gfxrst=4", remove("-v nvfb=1 gfxrst=4", ""))

    def test_reinstall_keeps_ownership_from_an_unchanged_record(self):
        t = tempfile.mkdtemp()
        rec = os.path.join(t, "state")
        with open(rec, "w") as f:
            f.write("EFI_UUID=U\nCONFIG_PATH=/c\nOCREL=EFI/OC\nCONFIG_SHA_AFTER=S\nADDED_ARGS='amfi=0x80 gfxrst=4 nvfb=1'\n")
        fn = slice_of(OWN_START, OWN_END)
        out = bash(f'{fn}\nowned_amfi_from_prior_record "{rec}" U /c EFI/OC S "nvfb=1 amfi=0x80 gfxrst=4"')
        self.assertEqual(out.split(), ["amfi=0x80", "gfxrst=4"])
        out = bash(f'{fn}\nowned_amfi_from_prior_record "{rec}" U /c EFI/OC CHANGED "gfxrst=4"')
        self.assertEqual(out.split(), [], "control: a changed config establishes no ownership")


if __name__ == "__main__":
    unittest.main()
