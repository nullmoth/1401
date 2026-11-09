"""An AMD laptop's vendor SSDT declares Method ALIB, which returns no value in macOS and stops the boot at PCI
configuration. The build renames that one declaration and ships a table that answers Zero. Synthetic tables only."""
import os
import platform
import plistlib
import subprocess
import tempfile
import unittest
import zipfile

from p1401 import acpi_shims, dsdt_pass1 as d, validate


def pkg(op, body):
    return op + d._encode_pkglen(len(body)) + body


def ssdt(body, oem=b"Vortex  "):
    t = bytearray(b"SSDT" + (36 + len(body)).to_bytes(4, "little") + b"\x02\x00" + b"AMD   " + oem +
                  (1).to_bytes(4, "little") + b"INTL" + (0x20200528).to_bytes(4, "little")) + body
    t[9] = (-sum(t)) & 0xFF
    return bytes(t)


ALIB = pkg(b"\x14", b"ALIB\x02" + b"\xa4\x00")                       # Method (ALIB, 2) { Return (Zero) }
CALLER = pkg(b"\x14", b"CALL\x00" + b"\x70" + b"ALIB\x00\x00" + b"\x61")  # Method (CALL, 0) { Store (ALIB (0, 0), Local1) }
IN_SB = pkg(b"\x10", b"\\_SB_" + ALIB + CALLER)
IN_PCI0 = pkg(b"\x10", b"\\\x2e_SB_PCI0" + ALIB)


def build(tables, extra_oc=None):
    t = tempfile.mkdtemp()
    acpi, out = os.path.join(t, "acpi"), os.path.join(t, "out")
    os.makedirs(acpi)
    os.makedirs(os.path.join(out, "EFI", "OC", "ACPI"))
    for name, data in tables.items():
        open(os.path.join(acpi, name), "wb").write(data)
    cfg = {"ACPI": {"Add": [], "Patch": []}}
    with open(os.path.join(out, "EFI", "OC", "config.plist"), "wb") as f:
        plistlib.dump(cfg, f)
    changes = acpi_shims.apply(acpi, out)
    return out, changes, plistlib.load(open(os.path.join(out, "EFI", "OC", "config.plist"), "rb"))["ACPI"]


class AlibShim(unittest.TestCase):
    def test_the_declaration_is_found_with_its_container_and_argument_count(self):
        out, changes, acpi = build({"SSDT-3.aml": ssdt(IN_SB)})
        found, _ = acpi_shims.find_alib(os.path.join(os.path.dirname(out), "acpi"))
        self.assertEqual([(f["path"], f["argc"], f["oem_table_id"]) for f in found], [((b"_SB_",), 2, b"Vortex  ")])

    def test_only_the_declaration_is_renamed_and_calls_keep_reaching_alib(self):
        out, changes, acpi = build({"SSDT-3.aml": ssdt(IN_SB)})
        (patch,) = acpi["Patch"]
        self.assertTrue(patch["Find"].startswith(b"\x14") and patch["Find"].endswith(b"ALIB"))
        self.assertEqual(patch["Replace"], patch["Find"][:-4] + b"XLIB")
        table = ssdt(IN_SB)
        self.assertEqual(table.count(patch["Find"]), 1, "the Find bytes match the declaration once, not the call")
        self.assertEqual(table.count(b"ALIB"), 2)   # the declaration and the call
        self.assertEqual(patch["OemTableId"], b"Vortex  ")
        self.assertEqual(patch["TableSignature"], b"SSDT")
        self.assertEqual(len(patch["Find"]), len(patch["Replace"]))

    def test_the_shim_declares_alib_again_at_the_same_path_and_returns_zero(self):
        out, changes, acpi = build({"SSDT-3.aml": ssdt(IN_PCI0)})
        shim = open(os.path.join(out, "EFI", "OC", "ACPI", acpi_shims.SHIM_FILE), "rb").read()
        self.assertEqual(int.from_bytes(shim[4:8], "little"), len(shim))
        self.assertEqual(sum(shim) & 0xFF, 0)
        self.assertEqual(d.methods_defined(shim), {(b"_SB_", b"PCI0", b"ALIB"): (2, d.methods_defined(shim)[(b"_SB_", b"PCI0", b"ALIB")][1])})
        self.assertTrue(shim.endswith(b"\xa4\x00"))                 # Return (Zero)
        self.assertEqual([e["Path"] for e in acpi["Add"]], [acpi_shims.SHIM_FILE])
        self.assertTrue(acpi["Add"][0]["Enabled"])

    def test_a_machine_without_alib_gets_nothing(self):
        other = pkg(b"\x10", b"\\_SB_" + pkg(b"\x14", b"FOO_\x00\xa4\x00"))
        out, changes, acpi = build({"SSDT-1.aml": ssdt(other), "DSDT.aml": b"DSDT"})
        self.assertEqual((changes, acpi["Patch"], acpi["Add"]), ([], [], []))
        self.assertFalse(os.path.exists(os.path.join(out, "EFI", "OC", "ACPI", acpi_shims.SHIM_FILE)))

    def test_a_second_build_over_the_same_efi_adds_nothing_twice(self):
        out, _, first = build({"SSDT-3.aml": ssdt(IN_SB)})
        acpi_shims.apply(os.path.join(os.path.dirname(out), "acpi"), out)
        again = plistlib.load(open(os.path.join(out, "EFI", "OC", "config.plist"), "rb"))["ACPI"]
        self.assertEqual((len(again["Patch"]), len(again["Add"])), (1, 1))

    def test_an_ssdt_the_walk_cannot_read_is_named_not_guessed(self):
        bad = ssdt(b"\x0f" + ALIB)                                  # an opcode the walk does not know
        out, changes, acpi = build({"SSDT-9.aml": bad})
        self.assertEqual(acpi["Patch"], [])
        self.assertEqual(len(changes), 1)
        self.assertIn("SSDT-9.aml", changes[0]["why"])

    def test_each_oem_table_id_gets_its_own_patch(self):
        out, changes, acpi = build({"SSDT-3.aml": ssdt(IN_SB), "SSDT-4.aml": ssdt(IN_SB, b"AmdTable")})
        self.assertEqual(sorted(p["OemTableId"] for p in acpi["Patch"]), [b"AmdTable", b"Vortex  "])
        self.assertEqual(len(acpi["Add"]), 1)


class AlibShimValidates(unittest.TestCase):
    def test_opencore_validator_accepts_the_patch_and_the_added_table(self):
        archive = os.environ.get("OPENCORE_TEST_ZIP", os.path.join(validate.CACHE, "OpenCore-1.0.8-RELEASE.zip"))
        if not os.path.isfile(archive):
            self.skipTest("The OpenCore 1.0.8 release archive is required for this check.")
        with zipfile.ZipFile(archive) as z:
            sample = plistlib.loads(z.read("Docs/Sample.plist"))
            name = {"Windows": "ocvalidate.exe", "Linux": "ocvalidate.linux"}.get(platform.system(), "ocvalidate")
            tool = z.read("Utilities/ocvalidate/" + name)
        out, _, acpi = build({"SSDT-3.aml": ssdt(IN_SB)})
        sample["ACPI"]["Add"] = []
        sample["ACPI"]["Patch"] = []
        t = tempfile.mkdtemp()
        exe = os.path.join(t, "ocvalidate")
        open(exe, "wb").write(tool)
        os.chmod(exe, 0o755)
        cfg = os.path.join(t, "config.plist")
        sample["ACPI"]["Add"] += acpi["Add"]
        sample["ACPI"]["Patch"] += acpi["Patch"]
        open(cfg, "wb").write(plistlib.dumps(sample))
        before = subprocess.run([exe, cfg], capture_output=True, text=True, timeout=30)
        # the sample alone has issues unrelated to ACPI; only ACPI lines count
        acpi_lines = [l for l in (before.stdout + before.stderr).splitlines() if "ACPI" in l]
        self.assertEqual(acpi_lines, [], acpi_lines)


if __name__ == "__main__":
    unittest.main()
