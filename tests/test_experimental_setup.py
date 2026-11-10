"""setup --experimental: the whole list of features that should be on is applied; boot-argument ones through the config and
NVRAM, the others as KEY=1 lines in one marked block of the knob file; turning one off removes exactly what it added and never
an argument the user set; unknown ids (the fetch-copy switch among them) change nothing."""
import pathlib
import plistlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
T = (ROOT / "mac/Resources/nullmoth-setup.sh").read_text()
a = T.index('if [ -n "${EXPER:-}" ]; then')
BLOCK = T[a:T.index('if [ -n "${GPUBOOST:-}" ]; then')]
B = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
FUNCS = (T[T.index("has() {"):T.index("\nget() {")] + "\n" + T[T.index("get() {"):T.index("; }\n", T.index("get() {")) + 4])


class Env:
    def __init__(self, args="keepsyms=1", conf="NVRM_X=1\n", record=None, kexts=("Lilu", "VirtualSMC"),
                 placed=("NMKbdBacklight", "NMHDA"), source=(), trust_source=True):
        self.trust_source = trust_source
        self.t = pathlib.Path(tempfile.mkdtemp())
        (self.t / "ns").mkdir()
        self.cfg = self.t / "config.plist"
        add = [{"BundlePath": f"{k}.kext", "Enabled": True} for k in kexts] + [
            {"BundlePath": f"{k}.kext", "Enabled": False, "Comment": "placed by the builder"} for k in placed]
        self.cfg.write_bytes(plistlib.dumps({"Kernel": {"Add": add}, "NVRAM": {"Add": {B: {"boot-args": args}}}}, sort_keys=False))
        (self.t / "Kexts").mkdir()
        self.src = self.t / "driver-kexts"       # stands in for /Library/NullMoth/kexts
        for k in source:
            (self.src / f"{k}.kext/Contents/MacOS").mkdir(parents=True)
            (self.src / f"{k}.kext/Contents/MacOS" / k).write_text("driver " + k)
        self.nv = self.t / "nvram-args"
        self.nv.write_text(args)
        self.conf = self.t / "nvrm610.conf" if conf is not None else self.t / "none.conf"
        if conf is not None:
            self.conf.write_text(conf)
            self.conf.chmod(0o640)
        if record:
            (self.t / "ns/experimental").write_text(record)

    def run(self, spec):
        block = BLOCK.replace("/Library/GPUBundles/nvmtl/nvrm610.conf", str(self.conf))
        block = block.replace("XSRC=/Library/NullMoth/kexts", f"XSRC={self.src}")
        if self.trust_source:   # the stand-in source is owned by whoever runs the test, not root
            assert block.count('&& xtrusted "$XSRC') == 1
            block = block.replace('&& xtrusted "$XSRC', '&& true "$XSRC')
        script = f'''stop() {{ echo "STOP $*"; exit 1; }}; step() {{ :; }}; ok() {{ echo "OK $*"; }}; note() {{ echo "NOTE $*"; }}; cleanup() {{ :; }}; ro_why() {{ :; }}
chown() {{ :; }}
nvram() {{ if [ "$1" = boot-args ]; then printf 'boot-args\\t%s\\n' "$(cat {self.nv})"; else echo "$1" | sed 's/^boot-args=//' > {self.nv}; fi; }}
ST={self.t / "ns"}; C={self.cfg}; B={B}; EXPER='{spec}'
{FUNCS}
{block}'''
        p = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=60)
        return p.stdout

    def args(self):
        return plistlib.loads(self.cfg.read_bytes())["NVRAM"]["Add"][B]["boot-args"].split()

    def kernel(self):
        return {k["BundlePath"]: k["Enabled"] for k in plistlib.loads(self.cfg.read_bytes())["Kernel"]["Add"]}

    def record(self):
        f = self.t / "ns/experimental"
        return f.read_text().splitlines() if f.exists() else []


class Experimental(unittest.TestCase):
    def test_a_boot_argument_feature_goes_to_the_config_and_nvram_and_is_recorded(self):
        e = Env()
        out = e.run("kbl,kblhid")
        self.assertIn("OK experimental features updated", out, out)
        self.assertEqual(e.args(), ["keepsyms=1", "nmkbl=1", "nmkblhid=1"])
        self.assertEqual(e.nv.read_text().split(), e.args())
        self.assertEqual(e.record(), ["ON=kbl", "ON=kblhid", "ARG=kbl:nmkbl=1", "ARG=kblhid:nmkblhid=1"])

    def test_the_newest_intel_graphics_wake_replay_is_one_argument_and_comes_out_again(self):
        e = Env()
        e.run("hybrid20")
        self.assertEqual(e.args(), ["keepsyms=1", "nmhybrid20=1"])
        e.run("none")
        self.assertEqual(e.args(), ["keepsyms=1"])

    def test_idle_gpu_deep_sleep_is_the_one_runtime_d3_argument_and_comes_out_again(self):
        e = Env()
        e.run("rtd3")
        self.assertEqual(e.args(), ["keepsyms=1", "nvrtd3=1"])
        self.assertNotIn("nvrtd3res", " ".join(e.args()))
        e.run("none")
        self.assertEqual(e.args(), ["keepsyms=1"])

    def test_idle_link_power_saving_is_one_argument_and_comes_out_again(self):
        e = Env()
        e.run("aspm")
        self.assertEqual(e.args(), ["keepsyms=1", "nvrmaspm=1"])
        e.run("none")
        self.assertEqual(e.args(), ["keepsyms=1"])

    def test_an_efi_driver_the_builder_placed_is_switched_on_and_off_in_the_efi(self):
        e = Env()
        out = e.run("kbl,hda")
        self.assertIn("OK experimental features updated", out, out)
        self.assertEqual(e.kernel(), {"Lilu.kext": True, "VirtualSMC.kext": True, "NMKbdBacklight.kext": True, "NMHDA.kext": True})
        self.assertEqual(e.args(), ["keepsyms=1", "nmkbl=1", "nmhdavol=1"])
        e.run("hda")
        self.assertEqual(e.kernel()["NMKbdBacklight.kext"], False)
        self.assertEqual(e.kernel()["NMHDA.kext"], True)
        e.run("none")
        self.assertEqual(e.kernel(), {"Lilu.kext": True, "VirtualSMC.kext": True, "NMKbdBacklight.kext": False, "NMHDA.kext": False})
        self.assertEqual(e.args(), ["keepsyms=1"])

    def test_an_older_efi_gets_the_driver_copied_in_from_the_installed_package(self):
        e = Env(placed=(), source=("NMKbdBacklight",))
        out = e.run("kbl")
        self.assertIn("NMKbdBacklight.kext copied into the EFI", out, out)
        self.assertEqual((e.t / "Kexts/NMKbdBacklight.kext/Contents/MacOS/NMKbdBacklight").read_text(), "driver NMKbdBacklight")
        entry = plistlib.loads(e.cfg.read_bytes())["Kernel"]["Add"][-1]
        self.assertEqual((entry["BundlePath"], entry["Enabled"], entry["ExecutablePath"], entry["PlistPath"]),
                         ("NMKbdBacklight.kext", True, "Contents/MacOS/NMKbdBacklight", "Contents/Info.plist"))
        e.run("none")
        self.assertEqual(e.kernel()["NMKbdBacklight.kext"], False)

    def test_a_driver_copy_that_root_does_not_own_is_never_put_into_the_efi(self):
        e = Env(placed=(), source=("NMKbdBacklight",), trust_source=False)
        before = e.cfg.read_bytes()
        out = e.run("kbl")
        self.assertIn("STOP", out, out)
        self.assertFalse((e.t / "Kexts/NMKbdBacklight.kext").exists())
        self.assertEqual(e.cfg.read_bytes(), before)

    def test_a_driver_that_is_nowhere_to_be_found_changes_nothing_not_even_nvram(self):
        e = Env(placed=(), source=())
        before = e.cfg.read_bytes()
        out = e.run("kbl,rtd3")
        self.assertIn("STOP", out); self.assertIn("NMKbdBacklight.kext", out)
        self.assertEqual(e.cfg.read_bytes(), before)
        self.assertEqual(e.nv.read_text().split(), ["keepsyms=1"])

    def test_the_keyboard_driver_is_refused_without_virtualsmc(self):
        e = Env(kexts=("Lilu", "FakeSMC"))
        before = e.cfg.read_bytes()
        out = e.run("kbl")
        self.assertIn("needs VirtualSMC.kext", out, out)
        self.assertEqual(e.cfg.read_bytes(), before)
        self.assertEqual(e.nv.read_text().split(), ["keepsyms=1"])

    def test_the_power_budget_is_three_arguments_together(self):
        e = Env()
        e.run("tgp")
        self.assertEqual(e.args(), ["keepsyms=1", "nvrmtgp=1", "nvrmgps=1", "nvrmnvpcf=1"])

    def test_the_knob_file_gets_one_marked_block_of_key_1_lines_and_keeps_its_mode_and_other_lines(self):
        e = Env()
        e.run("gameprio,hwrt,curves,tile,icb")
        text = e.conf.read_text()
        self.assertEqual(text, "NVRM_X=1\n# --- 1401 experimental ---\nNVMTL_GAME_GPU_PRIORITY=1\nNVK_HWRT_QUERY=1\nNVK_CURVES=1\nNVMTL_TILE_SHADING=1\nNVMTL_GPU_ICB=1\n# --- end 1401 experimental ---\n")
        self.assertEqual(oct(e.conf.stat().st_mode & 0o777), "0o640")
        self.assertEqual(e.args(), ["keepsyms=1"])

    def test_turning_one_off_removes_exactly_what_it_added(self):
        e = Env()
        e.run("kbl,gameprio,tgp")
        e.run("kbl")
        self.assertEqual(e.args(), ["keepsyms=1", "nmkbl=1"])
        self.assertNotIn("NVMTL_GAME_GPU_PRIORITY", e.conf.read_text())
        self.assertEqual(e.record(), ["ON=kbl", "ARG=kbl:nmkbl=1"])

    def test_none_puts_everything_back_and_deletes_the_record(self):
        e = Env()
        e.run("kbl,xvt,icb")
        e.run("none")
        self.assertEqual(e.args(), ["keepsyms=1"])
        self.assertEqual(e.conf.read_text(), "NVRM_X=1\n")
        self.assertEqual(e.record(), [])

    def test_an_argument_the_user_set_themselves_is_never_removed(self):
        e = Env(args="keepsyms=1 nmkbl=1")
        out = e.run("kbl")
        self.assertIn("already set by you", out)
        e.run("none")
        self.assertEqual(e.args(), ["keepsyms=1", "nmkbl=1"])

    def test_unknown_ids_and_the_fetch_copy_switch_change_nothing(self):
        for bad in ("kbl,fetchcopy", "NVMTL_FETCH_COPY", "nvfetchcopy", "kbl;rm"):
            e = Env()
            out = e.run(bad)
            self.assertIn("STOP unknown experimental feature", out, bad)
            self.assertEqual(e.args(), ["keepsyms=1"]); self.assertEqual(e.conf.read_text(), "NVRM_X=1\n"); self.assertEqual(e.record(), [])

    def test_the_hid_route_without_the_backlight_is_refused(self):
        e = Env()
        self.assertIn("needs the keyboard backlight", e.run("kblhid"))
        self.assertEqual(e.args(), ["keepsyms=1"])

    def test_a_driver_less_mac_cannot_get_the_knob_file_features_and_its_config_is_restored(self):
        e = Env(conf=None)
        out = e.run("kbl,icb")
        self.assertIn("knob file is missing", out)
        self.assertEqual(e.args(), ["keepsyms=1"])


class Wiring(unittest.TestCase):
    def test_the_app_sends_only_the_catalog_and_reads_the_record(self):
        swift = (ROOT / "mac/Sources/main.swift").read_text()
        self.assertIn('Experimental.argument(b["items"])', swift)
        self.assertIn('"--experimental", list', swift)
        self.assertIn("experimentalOn", swift)


if __name__ == "__main__":
    unittest.main()
