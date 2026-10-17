#!/usr/bin/env python3
"""The Mac side of emulated NVRAM: nullmoth-setup.sh installs OpenCore's LogoutHook save daemon only when the booted
OpenCore config loads OpenVariableRuntimeDxe.efi, and removes it on the remove path. Extract the three functions from
the shell source and drive them with a real config.plist, a staged LogoutHook, and a fake Launchd.command that records
how it was called, so no privileged path is touched."""
import pathlib
import plistlib
import subprocess
import tempfile
import unittest

root = pathlib.Path(__file__).resolve().parents[1]
source = (root / "Resources/nullmoth-setup.sh").read_text()
block = source[source.index("loads_emulated_nvram()"):source.index("\n# Every log query has its own time cap")]


def config(driver_paths):
    drivers = [{"Path": p, "Enabled": True} for p in driver_paths]
    return plistlib.dumps({"UEFI": {"Drivers": drivers}})


def harness(fn, config_bytes, stage=True):
    """Run one of the functions against a temp ESP mount and a temp install dir (the hardcoded /Library path is swapped
    for the temp one). Returns (stdout, how the fake Launchd.command was called, whether the install dir still exists)."""
    d = tempfile.mkdtemp()
    tmp = pathlib.Path(d)
    mp = tmp / "esp"
    (mp / "EFI/OC").mkdir(parents=True)
    (mp / "EFI/OC/config.plist").write_bytes(config_bytes)
    marker = tmp / "launchd-calls.txt"
    dst = tmp / "install/LogoutHook"
    if stage:
        src = mp / "EFI/NullMoth/LogoutHook"
        src.mkdir(parents=True)
        fake = f'#!/bin/bash\necho "$@" >> "{marker}"\n'
        (src / "Launchd.command").write_text(fake)
        (src / "Launchd.command").chmod(0o755)
        (src / "nvramdump").write_text("#!/bin/bash\n:\n")
        (src / "Launchd.command.plist").write_text("<plist/>\n")
    plan = block.replace("/Library/NullMoth/LogoutHook", str(dst))
    script = f'''C="{mp}/EFI/OC/config.plist"; MP="{mp}"
note() {{ echo "NOTE $*"; }}; ok() {{ echo "OK $*"; }}
{plan}
{fn}
'''
    out = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=30)
    calls = marker.read_text().strip() if marker.exists() else ""
    return out.stdout + out.stderr, calls, dst.exists()


class InstallsHookOnlyForEmulatedBuilds(unittest.TestCase):
    def test_install_runs_the_hook_when_the_driver_is_in_the_config(self):
        out, calls, _ = harness("install_nvram_hook", config(["OpenVariableRuntimeDxe.efi", "OpenRuntime.efi"]))
        self.assertEqual(calls, "install")
        self.assertIn("OK persistent NVRAM", out)

    def test_install_does_nothing_without_the_driver(self):
        out, calls, dst = harness("install_nvram_hook", config(["OpenRuntime.efi", "HfsPlus.efi"]))
        self.assertEqual(calls, "")
        self.assertFalse(dst)

    def test_install_warns_when_the_driver_is_set_but_the_hook_was_not_staged(self):
        out, calls, dst = harness("install_nvram_hook",
                                  config(["OpenVariableRuntimeDxe.efi", "OpenRuntime.efi"]), stage=False)
        self.assertEqual(calls, "")
        self.assertIn("NOTE", out)


class RemovesHookOnUninstall(unittest.TestCase):
    def test_remove_uninstalls_and_clears_the_install_dir(self):
        # Install first, then remove, reusing one temp tree would need shared state; run remove after a manual stage by
        # calling install then remove in the same shell.
        d = tempfile.mkdtemp()
        tmp = pathlib.Path(d)
        mp = tmp / "esp"
        (mp / "EFI/OC").mkdir(parents=True)
        (mp / "EFI/OC/config.plist").write_bytes(config(["OpenVariableRuntimeDxe.efi", "OpenRuntime.efi"]))
        marker = tmp / "launchd-calls.txt"
        dst = tmp / "install/LogoutHook"
        src = mp / "EFI/NullMoth/LogoutHook"
        src.mkdir(parents=True)
        (src / "Launchd.command").write_text(f'#!/bin/bash\necho "$@" >> "{marker}"\n')
        (src / "Launchd.command").chmod(0o755)
        (src / "nvramdump").write_text("#!/bin/bash\n:\n")
        (src / "Launchd.command.plist").write_text("<plist/>\n")
        plan = block.replace("/Library/NullMoth/LogoutHook", str(dst))
        script = f'''C="{mp}/EFI/OC/config.plist"; MP="{mp}"
note() {{ echo "NOTE $*"; }}; ok() {{ echo "OK $*"; }}
{plan}
install_nvram_hook
remove_nvram_hook
'''
        subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(marker.read_text().split(), ["install", "uninstall"])
        self.assertFalse(dst.exists())

    def test_remove_is_a_no_op_when_nothing_was_installed(self):
        d = tempfile.mkdtemp()
        dst = pathlib.Path(d) / "install/LogoutHook"
        plan = block.replace("/Library/NullMoth/LogoutHook", str(dst))
        script = f'''note() {{ echo "NOTE $*"; }}; ok() {{ echo "OK $*"; }}
{plan}
remove_nvram_hook
'''
        out = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0)
        self.assertNotIn("OK persistent NVRAM: the save-at-shutdown daemon is removed", out.stdout)


if __name__ == "__main__":
    unittest.main()
