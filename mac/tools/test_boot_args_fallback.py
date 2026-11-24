"""nullmoth-setup.sh's nvram_boot_args: when nvram(8) refuses the write (#590 on macOS 26), the value goes into the
OpenCore config and boot-args joins NVRAM.Delete so OpenCore sets it at the next start; when nvram works, the config is
not touched. The function is lifted from the script and run with a stand-in nvram."""
import os
import pathlib
import plistlib
import subprocess
import tempfile
import unittest

SETUP = pathlib.Path(__file__).resolve().parents[1] / "Resources/nullmoth-setup.sh"
B = "7C436110-AB2A-4BBB-A880-FE41995C9F82"


def lifted():
    s = SETUP.read_text()
    start = s.index("has() {")
    end = s.index("\n}\n", s.index("nvram_boot_args() {")) + 3
    return s[start:end]


def run(nvram_ok, config):
    d = tempfile.mkdtemp()
    c = os.path.join(d, "config.plist")
    with open(c, "wb") as fh:
        plistlib.dump(config, fh)
    bindir = os.path.join(d, "bin")
    os.makedirs(bindir)
    with open(os.path.join(bindir, "nvram"), "w") as fh:
        fh.write("#!/bin/bash\n" + ("echo \"$@\" >> %s/nvram.log; exit 0\n" % d if nvram_ok else
                                    "echo 'nvram: Error creating CFTypeRef for value IONVRAM-SYNCNOW-PROPERTY' >&2; exit 1\n"))
    os.chmod(os.path.join(bindir, "nvram"), 0o755)
    script = f'B={B}\nC="{c}"\nnote() {{ echo "NOTE $*"; }}\n' + lifted() + '\nnvram_boot_args "-v nmsmn=1 keepsyms=1"; echo "rc=$?"\n'
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                         env=dict(os.environ, PATH=bindir + ":/usr/bin:/bin")).stdout
    with open(c, "rb") as fh:
        return out, plistlib.load(fh), d


class Fallback(unittest.TestCase):
    base = {"NVRAM": {"Add": {B: {"boot-args": "-v alcid=11"}}, "Delete": {B: ["csr-active-config"]}}}

    def test_a_refused_write_lands_in_the_config_and_opencore_deletes_the_old_value(self):
        out, cfg, _ = run(False, self.base)
        self.assertIn("rc=0", out)
        self.assertIn("OpenCore config", out)
        args = cfg["NVRAM"]["Add"][B]["boot-args"].split()
        for a in ("-v", "alcid=11", "nmsmn=1", "keepsyms=1"):
            self.assertIn(a, args)
        self.assertEqual(args.count("-v"), 1)
        self.assertIn("boot-args", cfg["NVRAM"]["Delete"][B])
        self.assertIn("csr-active-config", cfg["NVRAM"]["Delete"][B])

    def test_a_config_with_no_delete_list_gets_one(self):
        out, cfg, _ = run(False, {"NVRAM": {"Add": {B: {}}}})
        self.assertIn("rc=0", out)
        self.assertEqual(cfg["NVRAM"]["Delete"][B], ["boot-args"])
        self.assertEqual(cfg["NVRAM"]["Add"][B]["boot-args"], "-v nmsmn=1 keepsyms=1")

    def test_negative_control_a_working_nvram_leaves_the_config_alone(self):
        out, cfg, d = run(True, self.base)
        self.assertIn("rc=0", out)
        self.assertEqual(cfg, self.base)
        self.assertIn("boot-args=-v nmsmn=1 keepsyms=1", open(os.path.join(d, "nvram.log")).read())


if __name__ == "__main__":
    unittest.main()
