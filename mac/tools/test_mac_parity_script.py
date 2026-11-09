#!/usr/bin/env python3
"""nullmoth-mac-parity.sh reads how the installed Mac presents itself to Apple's services and sleep settings. The
system tools are replaced with scripts on PATH, so the checks run anywhere and nothing real is read or written."""
import os
import pathlib
import stat
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "Resources" / "nullmoth-mac-parity.sh"


class Fake:
    """A directory of fake tools. Each tool prints a fixed text; pmset also logs what it was asked to set."""

    def __init__(self, serial="C02ABCDEF8J1", mac="a4:c3:f0:11:22:33", rom="%a4%c3%f0%11%22%33", model="MacPro7,1",
                 power=None):
        self.dir = tempfile.mkdtemp()
        self.state = tempfile.mkdtemp()
        self.log = os.path.join(self.dir, "pmset.log")
        power = power or {"powernap": "1", "standby": "1", "autopoweroff": "1", "proximitywake": "1", "hibernatemode": "3"}
        custom = "Battery Power:\nAC Power:\n" + "".join(f" {k}  {v}\n" for k, v in power.items())
        tools = {
            "ioreg": f'echo \'    "IOPlatformSerialNumber" = "{serial}"\'' if serial else "true",
            "ifconfig": f"echo '\tether {mac}'" if mac else "true",
            "nvram": f"printf 'key:ROM\\t%s\\n' '{rom}'" if rom else "true",
            "networksetup": "echo 'Hardware Port: Ethernet'; echo 'Device: en0'",
            "sysctl": f"echo {model}",
            "pmset": f'if [ "$1" = "-g" ]; then cat <<EOT\n{custom}EOT\nelse echo "$@" >> "{self.log}"; fi',
        }
        for name, body in tools.items():
            p = os.path.join(self.dir, name)
            with open(p, "w") as f:
                f.write("#!/bin/bash\n" + body + "\n")
            os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)

    def run(self, *args):
        env = {"PATH": self.dir + ":/usr/bin:/bin", "NULLMOTH_STATE_DIR": self.state}
        r = subprocess.run(["/bin/bash", str(SCRIPT), *args], capture_output=True, text=True, env=env)
        return r.returncode, r.stdout


class Identity(unittest.TestCase):
    def test_a_rom_equal_to_the_en0_address_and_a_real_serial_report_nothing(self):
        code, out = Fake().run("identity")
        self.assertEqual(code, 0, out)
        self.assertIn("the ROM equals en0's address", out)

    def test_a_different_rom_is_reported(self):
        code, out = Fake(rom="%a4%c3%f0%11%22%44").run("identity")
        self.assertEqual(code, 1)
        self.assertIn("differs from en0's address", out)

    def test_no_rom_is_reported(self):
        code, out = Fake(rom=None).run("identity")
        self.assertEqual(code, 1)
        self.assertIn("ROM is not set", out)

    def test_a_placeholder_or_missing_serial_is_reported(self):
        for serial, text in (("A0000000009", "placeholder"), (None, "no serial number")):
            code, out = Fake(serial=serial).run("identity")
            self.assertEqual(code, 1, serial)
            self.assertIn(text, out)

    def test_no_en0_is_reported(self):
        code, out = Fake(mac=None).run("identity")
        self.assertEqual(code, 1)
        self.assertIn("no en0", out)


class GameMode(unittest.TestCase):
    def run_gm(self, *args, stored=None):
        f = Fake()
        body = ('if [ "$1" = read ]; then ' + ('echo 1' if stored else 'exit 1') + '; else echo "$@" >> "' + os.path.join(f.dir, "defaults.log") + '"; fi')
        p = os.path.join(f.dir, "defaults")
        with open(p, "w") as fh:
            fh.write("#!/bin/bash\n" + body + "\n")
        os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)
        return f, f.run("gamemode", *args)

    def test_status_reports_whether_the_preference_is_stored(self):
        self.assertEqual(self.run_gm("status", stored=True)[1][0], 0)
        code, out = self.run_gm("status", stored=False)[1]
        self.assertEqual(code, 1)
        self.assertIn("off", out)

    def test_on_and_off_need_root_and_a_bad_word_is_refused(self):
        if os.getuid() != 0:
            code, out = self.run_gm("on")[1]
            self.assertEqual(code, 2)
            self.assertIn("needs root", out)
        self.assertEqual(self.run_gm("sideways")[1][0], 2)


class Power(unittest.TestCase):
    def test_check_lists_what_the_profile_changes_and_writes_nothing(self):
        f = Fake()
        code, out = f.run("power", "check")
        self.assertEqual(code, 1)
        self.assertIn("differs powernap is 1", out)
        self.assertFalse(os.path.exists(f.log))

    def test_a_laptop_keeps_its_hibernate_mode(self):
        code, out = Fake(model="MacBookPro16,2").run("power", "check")
        self.assertNotIn("hibernatemode", out)

    def test_apply_needs_root(self):
        if os.getuid() == 0:
            self.skipTest("running as root")
        code, out = Fake().run("power", "apply")
        self.assertEqual(code, 2)
        self.assertIn("needs root", out)

    def test_apply_saves_the_previous_values_and_restore_puts_them_back(self):
        if os.getuid() != 0:
            self.skipTest("the write path needs root; the guard above covers the refusal")
        f = Fake()
        code, _ = f.run("power", "apply")
        saved = open(os.path.join(f.state, "power-profile.backup")).read()
        self.assertIn("powernap 1", saved)
        f.run("power", "restore")
        self.assertIn("powernap 1", open(f.log).read())


if __name__ == "__main__":
    unittest.main()
