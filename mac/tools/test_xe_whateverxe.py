#!/usr/bin/env python3
"""Intel Xe graphics through WhateverXe (setup --xe): runs the setup's real block on fake OpenCore configs with stubbed
system tools. On adds WhateverXe after Lilu, the WhateverXe AMFIPass build, WhateverGreen off and SIP >= 0x803; off puts
the config back exactly; an unsupported GPU, an old macOS, the NMX Intel test driver or a bad download change nothing."""
import base64
import hashlib
import os
import pathlib
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

SETUP = pathlib.Path(__file__).resolve().parents[1] / "Resources/nullmoth-setup.sh"
BASH = os.environ.get("BASH") or shutil.which("bash") or "/bin/bash"
BASE64 = shutil.which("base64") or "/usr/bin/base64"
START, END = 'if [ -n "${XE:-}" ]; then', 'if [ -n "${GPUTEST:-}" ]; then'
HS, HE = "# Kexts the driver's OpenCore setup needs", "booted_part() {"
GUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
PINS = {"WhateverXe.kext": "5b71e14ce10c673f6baba276183f268d7f04766d298cd34f1df0bb96f11c8e4b",
        "AMFIPass-Mod.zip": "71f41de42e355d2a83e6f093ef34a5b24d0a9c9a9085830b2317f1b874f56250",
        "WhateverXe-Graphics.pkg": "7f7ce3b924ad421cff0c4f30534598858474b8c9539c4b889a461bc1d5fed02c"}
PKG = b"pkg\n"


def kext(name, enabled=True):
    return {"Arch": "Any", "BundlePath": name, "Enabled": enabled, "ExecutablePath": f"Contents/MacOS/{name[:-5]}",
            "PlistPath": "Contents/Info.plist", "Comment": "", "MaxKernel": "", "MinKernel": ""}


def zipped(t, name, top):
    z = os.path.join(t, name)
    with zipfile.ZipFile(z, "w") as f:
        f.writestr(f"{top}/Contents/Info.plist", "<plist/>")
    with open(z, "rb") as f:
        return z, hashlib.sha256(f.read()).hexdigest()


def stub(b, name, body):
    p = os.path.join(b, name)
    with open(p, "w") as f:
        f.write("#!/bin/bash\n" + body + "\n")
    os.chmod(p, 0o755)


# The setup block uses macOS's plutil and ditto. On a Windows build machine those do not exist; small Python
# stand-ins with the same command lines keep this test runnable there (macOS still uses the real tools).
PLUTIL = r'''
import base64, json, plistlib, sys
def load(p):
    with open(p, "rb") as f:
        return plistlib.load(f)
def save(p, c):
    with open(p, "wb") as f:
        plistlib.dump(c, f)
def get(c, parts):
    for p in parts:
        c = c[int(p)] if isinstance(c, list) else c[p]
    return c
def put(c, parts, value, insert):
    for p in parts[:-1]:
        if isinstance(c, list):
            i = int(p)
            while len(c) <= i:
                c.append({})
            c = c[i]
        else:
            c = c.setdefault(p, {})
    last = parts[-1]
    if isinstance(c, list):
        i = int(last)
        if insert:
            c.insert(min(i, len(c)), value)
        else:
            while len(c) <= i:
                c.append(None)
            c[i] = value
    else:
        c[last] = value
def raw(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, bytes):
        return base64.b64encode(v).decode()
    return str(v)
try:
    op, args = sys.argv[1], sys.argv[2:]
    path = args[-1]
    cfg = load(path)
    if op == "-extract":
        print(raw(get(cfg, args[0].split("."))))
    elif op in ("-replace", "-insert"):
        key, kind, value = args[0], args[1], args[2]
        if kind == "-bool":
            value = value == "true"
        elif kind == "-data":
            value = base64.b64decode(value)
        elif kind == "-json":
            value = json.loads(value)
        elif kind == "-integer":
            value = int(value)
        put(cfg, key.split("."), value, op == "-insert")
        save(path, cfg)
    elif op == "-remove":
        parts = args[0].split(".")
        parent = get(cfg, parts[:-1])
        if isinstance(parent, list):
            del parent[int(parts[-1])]
        else:
            del parent[parts[-1]]
        save(path, cfg)
    elif op == "-lint":
        print(path + ": OK")
finally:
    pass
'''
DITTO = r'''
import os, shutil, sys, zipfile
a = sys.argv[1:]
if a[:2] == ["-x", "-k"]:
    zipfile.ZipFile(a[2]).extractall(a[3])
elif os.path.isdir(a[0]):
    shutil.copytree(a[0], a[1], dirs_exist_ok=True)
else:
    os.makedirs(os.path.dirname(os.path.abspath(a[1])), exist_ok=True)
    shutil.copy2(a[0], a[1])
'''


def native_tool(b, name, code):
    script = os.path.join(b, name + ".py")
    with open(script, "w", encoding="utf-8") as f:
        f.write(code)
    exe = sys.executable.replace("\\", "/")
    stub(b, name, 'exec "%s" "%s" "$@"' % (exe, script.replace("\\", "/")))


def run(mode, kexts, folders=("Lilu.kext",), dev="9A49", ver="15.8.1", bootargs="", csr=0x0,
        loaded="", good=True, t=None, cfg_extra=None):
    s = SETUP.read_text()
    for a in (START, END, HS, HE):
        assert s.count(a) == 1, f"anchor moved in nullmoth-setup.sh: {a}"
    t = (t or tempfile.mkdtemp()).replace("\\", "/")
    oc = os.path.join(t, "EFI/OC").replace("\\", "/")
    cfg = os.path.join(oc, "config.plist").replace("\\", "/")
    if not os.path.exists(cfg):
        for f in folders:
            os.makedirs(os.path.join(oc, "Kexts", f, "Contents"), exist_ok=True)
            with open(os.path.join(oc, "Kexts", f, "Contents/Info.plist"), "w") as fh:
                fh.write("<plist>" + f + "</plist>")
        nv = {"boot-args": bootargs}
        if csr is not None:
            nv["csr-active-config"] = csr.to_bytes(4, "little")
        c = {"Kernel": {"Add": kexts}, "NVRAM": {"Add": {GUID: nv}}}
        c.update(cfg_extra or {})
        os.makedirs(oc, exist_ok=True)
        with open(cfg, "wb") as fh:
            plistlib.dump(c, fh)
    wz, wsha = zipped(t, "wex.zip", "WhateverXe.kext")
    az, asha = zipped(t, "amfi.zip", "AMFIPass.kext")
    wz, az = wz.replace("\\", "/"), az.replace("\\", "/")
    b = os.path.join(t, "bin").replace("\\", "/"); os.makedirs(b, exist_ok=True)
    if not shutil.which("plutil"):
        native_tool(b, "plutil", PLUTIL)
    if not shutil.which("ditto"):
        native_tool(b, "ditto", DITTO)
    if os.name == "nt":
        # Git Bash's GNU base64 uses -d; the setup script (and macOS) uses -D.
        stub(b, "base64", 'args=(); for a in "$@"; do [ "$a" = "-D" ] && a="-d"; args+=("$a"); done\n'
                           'exec "%s" "${args[@]}"' % BASE64.replace("\\", "/"))
    stub(b, "curl", f'out=""; url=""; while [ $# -gt 0 ]; do case "$1" in -o) out=$2; shift;; http*) url=$1;; esac; shift; done\n'
                    f'case "$url" in *WhateverXe-0.8.0*) cp "{wz}" "$out";; *AMFIPass*) cp "{az}" "$out";; '
                    f'*.pkg) echo pkg > "$out";; *) exit 22;; esac')
    stub(b, "sysctl", 'echo GenuineIntel')
    d = dev.lower()
    stub(b, "ioreg", f'echo "+-o IGPU"; echo \'  "vendor-id" = <86800000>\'; echo \'  "device-id" = <{d[2:]}{d[:2]}0000>\'; '
                     f'echo \'  "class-code" = <00000300>\'')
    stub(b, "sw_vers", f'echo {ver}')
    stub(b, "kmutil", f'echo "{loaded}"')
    stub(b, "nvram", f'printf "boot-args\\t{bootargs}\\n"')
    stub(b, "installer", f'echo installed > "{t}/installed"')
    stub(b, "pkgutil", f'[ -f "{t}/installed" ] && echo org.b00t0x.WhateverXe.Common; true')
    block = 'KT=""\n' + s[s.index(HS):s.index(HE)] + s[s.index(START):s.index(END)]
    fake = {"WhateverXe.kext": wsha, "AMFIPass-Mod.zip": asha, "WhateverXe-Graphics.pkg": hashlib.sha256(PKG).hexdigest()}
    for k, real in PINS.items():
        block = block.replace(real, fake[k] if good else "0" * 64)
    st = os.path.join(t, "state").replace("\\", "/"); os.makedirs(st, exist_ok=True)
    script = (f'C="{cfg}"; B={GUID}; ST="{st}"; XE={mode}\n'
              'has() { plutil -extract "$1" raw -o - "$C" >/dev/null 2>&1; }\n'
              'get() { plutil -extract "$1" raw -o - "$C" 2>/dev/null; }\n'
              'step() { echo "STEP $*"; }; ok() { echo "OK $*"; }; note() { echo "NOTE $*"; }; ro_why() { :; }\n'
              'cleanup() { :; }; stop() { echo "STOP $*"; exit 3; }\n'
              + s[s.index("csr_of() {"):s.index("\n", s.index("csr_data() {"))] + "\n"
              + block)
    env = dict(os.environ, PATH=b + ":" + os.environ["PATH"])
    script_path = os.path.join(t, "run-xe.sh")
    with open(script_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(script)
    r = subprocess.run([BASH, script_path], capture_output=True, text=True, timeout=60, env=env)
    with open(cfg, "rb") as fh:
        c = plistlib.load(fh)
    return r.returncode, r.stdout + r.stderr, c, t


def names(c):
    return [(k["BundlePath"], k["Enabled"]) for k in c["Kernel"]["Add"]]


def csr(c):
    return int.from_bytes(c["NVRAM"]["Add"][GUID]["csr-active-config"], "little")


BASE = [kext("Lilu.kext"), kext("VirtualSMC.kext"), kext("WhateverGreen.kext")]


class Xe(unittest.TestCase):
    def test_on_adds_whateverxe_after_lilu_and_turns_whatevergreen_off(self):
        rc, out, c, _ = run("on", list(BASE), folders=("Lilu.kext", "VirtualSMC.kext", "WhateverGreen.kext"), csr=0x0)
        self.assertEqual(rc, 0, out)
        self.assertEqual(names(c), [("Lilu.kext", True), ("WhateverXe.kext", True), ("AMFIPass.kext", True),
                                    ("VirtualSMC.kext", True), ("WhateverGreen.kext", False)], out)
        self.assertEqual(csr(c) & 0x803, 0x803, out)
        self.assertEqual(c["NVRAM"]["Add"][GUID]["boot-args"].split(), ["-allow3d", "-disablegfxfirmware"], out)
        self.assertIn("restart", out)

    def test_off_removes_only_the_boot_arguments_it_added(self):
        rc, out, c, t = run("on", list(BASE), folders=("Lilu.kext",), bootargs="keepsyms=1 -allow3d", csr=0x0A43)
        self.assertEqual(rc, 0, out)
        self.assertEqual(c["NVRAM"]["Add"][GUID]["boot-args"].split(), ["keepsyms=1", "-allow3d", "-disablegfxfirmware"], out)
        rc, out, c, _ = run("off", None, t=t)
        self.assertEqual(rc, 0, out)
        self.assertEqual(c["NVRAM"]["Add"][GUID]["boot-args"].split(), ["keepsyms=1", "-allow3d"], out)

    def test_off_puts_the_config_back_exactly(self):
        before = list(BASE)
        rc, out, c, t = run("on", before, folders=("Lilu.kext", "VirtualSMC.kext", "WhateverGreen.kext"), csr=0x0A43)
        self.assertEqual(rc, 0, out)
        rc, out, c, _ = run("off", None, t=t)
        self.assertEqual(rc, 0, out)
        self.assertEqual(names(c), [(k["BundlePath"], k["Enabled"]) for k in before], out)
        self.assertEqual(csr(c), 0x0A43, out)
        self.assertFalse(os.path.exists(os.path.join(t, "EFI/OC/Kexts/WhateverXe.kext")), out)
        self.assertFalse(os.path.exists(os.path.join(t, "EFI/OC/Kexts/AMFIPass.kext")), out)

    def test_an_existing_amfipass_is_kept_aside_and_comes_back(self):
        start = [kext("Lilu.kext"), kext("AMFIPass.kext")]
        rc, out, c, t = run("on", start, folders=("Lilu.kext", "AMFIPass.kext"), csr=0x0A43)
        self.assertEqual(rc, 0, out)
        self.assertIn("AMFIPass.kext.nullmoth-xe", out)
        rc, out, c, _ = run("off", None, t=t)
        self.assertEqual(rc, 0, out)
        self.assertEqual(names(c), [("Lilu.kext", True), ("AMFIPass.kext", True)], out)
        with open(os.path.join(t, "EFI/OC/Kexts/AMFIPass.kext/Contents/Info.plist")) as fh:
            info = fh.read()
        self.assertIn("AMFIPass.kext", info, "the user's own AMFIPass must be the one back in place")

    def test_sip_set_higher_by_the_nvidia_driver_is_left_alone(self):
        rc, out, c, _ = run("on", list(BASE), folders=("Lilu.kext",), csr=0x0A43)
        self.assertEqual(rc, 0, out)
        self.assertEqual(csr(c), 0x0A43, out)
        self.assertNotIn("csr-active-config", out)

    def test_second_run_with_whateverxe_loaded_raises_sip_before_the_package(self):
        # A Windows-built EFI already carries WhateverXe, so setup can see it loaded before setup ever raised SIP;
        # the graphics package needs 0x803, so the first toggle must fix SIP and ask for a restart, not install.
        rc, out, c, t = run("on", list(BASE), folders=("Lilu.kext",), csr=0x3, loaded="org.b00t0x.WhateverXe (0.8.0) X")
        self.assertEqual(rc, 0, out)
        self.assertFalse(os.path.exists(os.path.join(t, "installed")), out)
        self.assertEqual(csr(c) & 0x803, 0x803, out)
        self.assertIn("restart", out)
        self.assertTrue(os.path.exists(os.path.join(t, "state/xe-state")), out)

    def test_second_run_after_the_sip_fix_installs_the_graphics_package(self):
        rc, out, c, t = run("on", list(BASE), folders=("Lilu.kext",), csr=0x3, loaded="org.b00t0x.WhateverXe (0.8.0) X")
        self.assertEqual(rc, 0, out)
        rc, out, c, t = run("on", None, t=t, loaded="org.b00t0x.WhateverXe (0.8.0) X")
        self.assertEqual(rc, 0, out)
        self.assertTrue(os.path.exists(os.path.join(t, "installed")), out)
        self.assertNotIn(("WhateverXe.kext", True), names(c), "the package step does not touch the config")

    def test_second_run_with_compliant_sip_installs_the_graphics_package(self):
        rc, out, c, t = run("on", list(BASE), folders=("Lilu.kext",), csr=0x803,
                            loaded="org.b00t0x.WhateverXe (0.8.0) X")
        self.assertEqual(rc, 0, out)
        self.assertTrue(os.path.exists(os.path.join(t, "installed")), out)
        self.assertNotIn(("WhateverXe.kext", True), names(c), "the package step does not touch the config")

    # negative controls: each must stop with the config untouched
    def assert_untouched(self, **kw):
        rc, out, c, _ = run("on", list(BASE), folders=("Lilu.kext",), **kw)
        self.assertEqual(rc, 3, out)
        self.assertEqual(names(c), [(k["BundlePath"], k["Enabled"]) for k in BASE], out)
        return out

    def test_unsupported_intel_gpu_is_refused(self):
        self.assertIn("not one WhateverXe supports", self.assert_untouched(dev="3E92"))

    def test_old_macos_is_refused(self):
        self.assertIn("15.8 or later", self.assert_untouched(ver="15.7.4"))

    def test_tahoe_before_26_7_is_refused(self):
        self.assertIn("26.7 or later", self.assert_untouched(ver="26.6.2"))

    def test_the_nmx_intel_test_driver_blocks_it(self):
        self.assertIn("turn it off first", self.assert_untouched(bootargs="-nmxintel keepsyms=1"))

    def test_a_download_with_the_wrong_hash_changes_nothing(self):
        self.assertIn("SHA-256", self.assert_untouched(good=False))

    def test_no_lilu_is_refused(self):
        rc, out, c, _ = run("on", [kext("VirtualSMC.kext")], folders=())
        self.assertEqual(rc, 3, out)
        self.assertIn("needs Lilu", out)


if __name__ == "__main__":
    unittest.main()
