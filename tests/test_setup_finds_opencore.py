#!/usr/bin/env python3
"""Finding the OpenCore config, two cases from setup logs that stopped as "no OpenCore config":
- a MacPro7,1 whose OpenCore lives in EFI/macos/OC (2.5.3, boot-path \\EFI\\macos\\OC\\OpenCore.efi): the folder named in
  OpenCore's boot-path is looked at, so that config is found;
- a PC reporting its own model (82JQ, 2.7.2) with no boot-path: that start did not go through OpenCore, and the stop
  says so instead of asking for a disk that is already connected."""
import pathlib
import plistlib
import subprocess
import tempfile
import sys
import unittest

SETUP = pathlib.Path(__file__).resolve().parents[1] / "mac/Resources/nullmoth-setup.sh"
TEXT = SETUP.read_text()


def func(name):
    a = TEXT.index(f"\n{name}() {{") + 1
    end = TEXT.index("; }\n", a) + len("; }\n")
    return TEXT[a:end]


FUNCS = "\n".join(func(n) for n in ("ocrel_in", "boot_ocrel", "not_oc_model"))
BOOTPATH = r"PciRoot(0x0)/Pci(0x1C,0x4)/Pci(0x0,0x0)/NVMe(0x1,00-00-00-00-00-00-82-0C)/HD(1,GPT,0A0B0C0D-1111-2222-3333-444455556666,0x800,0x96000)/\EFI\macos\OC\OpenCore.efi%00"


def shell(script, model, bootpath):
    stubs = (f"sysctl() {{ echo '{model}'; }}\n"
             f"nvram() {{ case \"$1\" in *:boot-path) [ -n '{bootpath}' ] || return 1; printf '%s\\t%s\\n' \"$1\" '{bootpath}';; *) return 1;; esac; }}\n")
    return subprocess.run(["/bin/bash", "-c", stubs + FUNCS + "\n" + script], capture_output=True, text=True, timeout=30)


def efi(folder, model):
    root = pathlib.Path(tempfile.mkdtemp())
    d = root / folder
    d.mkdir(parents=True)
    (d / "config.plist").write_bytes(plistlib.dumps({"PlatformInfo": {"Generic": {"SystemProductName": model}}}))
    return root


class FindsOpenCore(unittest.TestCase):
    def test_boot_path_folder_is_read_from_the_variable(self):
        out = shell("boot_ocrel", "MacPro7,1", BOOTPATH)
        self.assertEqual(out.stdout.strip(), "EFI/macos/OC", out.stderr)

    def test_config_in_a_custom_folder_is_found(self):
        root = efi("EFI/macos/OC", "MacPro7,1")
        out = shell(f"ocrel_in '{root}'", "MacPro7,1", BOOTPATH)
        self.assertEqual(out.stdout.strip(), "EFI/macos/OC", out.stderr)

    def test_without_a_boot_path_only_the_usual_folders_count(self):
        root = efi("EFI/macos/OC", "MacPro7,1")
        self.assertEqual(shell(f"ocrel_in '{root}'", "MacPro7,1", "").stdout.strip(), "")
        root = efi("EFI/OC", "MacPro7,1")
        self.assertEqual(shell(f"ocrel_in '{root}'", "MacPro7,1", "").stdout.strip(), "EFI/OC")

    def test_a_boot_path_outside_efi_or_climbing_out_is_ignored(self):
        for bad in (r"PciRoot(0x0)/HD(1,GPT,x)/\OC\OpenCore.efi", r"PciRoot(0x0)/HD(1,GPT,x)/\EFI\..\x\OpenCore.efi",
                    r"PciRoot(0x0)/HD(1,GPT,x)/\OpenCore.efi", "garbage"):
            self.assertEqual(shell("boot_ocrel", "MacPro7,1", bad).stdout.strip(), "", bad)

    def test_a_config_for_another_model_is_still_skipped(self):
        root = efi("EFI/macos/OC", "iMacPro1,1")
        self.assertEqual(shell(f"ocrel_in '{root}'", "MacPro7,1", BOOTPATH).stdout.strip(), "")

    def test_a_pc_model_with_no_boot_path_is_not_an_opencore_start(self):
        self.assertEqual(shell("not_oc_model && echo yes", "82JQ", "").stdout.strip(), "yes")

    def test_a_mac_model_or_a_boot_path_is_an_opencore_start(self):
        self.assertEqual(shell("not_oc_model && echo yes", "MacBookPro16,2", "").stdout.strip(), "")
        self.assertEqual(shell("not_oc_model && echo yes", "82JQ", BOOTPATH).stdout.strip(), "")

    def test_the_stop_names_the_start_that_skipped_opencore(self):
        block = TEXT[TEXT.index("not_oc_model && [ -z \"$denied\" ]"):]
        self.assertLess(block.index("did not go through OpenCore"), block.index("no OpenCore config for this Mac"))

def load_tests(loader, tests, pattern):
    """These tests run the Mac side (bash and macOS tools), so they are collected on a Mac only: the Windows package
    check counts a skipped test as a failure, and the Mac release step runs them."""
    return tests if sys.platform == "darwin" else unittest.TestSuite()


if __name__ == "__main__":
    unittest.main()
