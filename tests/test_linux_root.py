"""The Linux scan reads the firmware tables through pkexec and hands them to the builder under the names it expects
(`DSDT.aml`, not the `DSDT` sysfs uses). A root-only read that silently produced an empty ACPI folder would build a
Mac setup without the machine's own tables, so the copy checks the DSDT before saying it worked."""
import os
import tempfile
import unittest
from unittest import mock

from p1401 import linuxroot


def table_tree(root):
    os.makedirs(os.path.join(root, "dynamic"))
    files = {"DSDT": b"DSDT" + b"\0" * 60, "SSDT1": b"SSDT" + b"\0" * 60,
             "dynamic/SSDT2": b"SSDT" + b"\1" * 60, "FACP": b"FACP" + b"\2" * 60}
    for name, data in files.items():
        path = os.path.join(root, *name.split("/"))
        with open(path, "wb") as fh:
            fh.write(data)
    return files


class CopyTables(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = os.path.join(self.temp.name, "sysfs")
        self.dest = os.path.join(self.temp.name, "ACPI")
        self.files = table_tree(self.source)
        os.makedirs(self.dest)

    def test_every_table_is_written_with_an_aml_suffix(self):
        written = linuxroot.copy_tables(self.source, self.dest)
        self.assertEqual(sorted(os.path.basename(p) for p in written),
                         ["DSDT.aml", "FACP.aml", "SSDT1.aml", "SSDT2.aml"])
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "DYNAMIC", "SSDT2.aml")))
        with open(os.path.join(self.dest, "DSDT.aml"), "rb") as fh:
            self.assertEqual(fh.read(), self.files["DSDT"])

    def test_the_copied_tables_are_readable_by_the_user_who_runs_the_scan(self):
        written = linuxroot.copy_tables(self.source, self.dest)
        for path in written:
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o644)

    def test_a_directory_without_a_dsdt_is_a_failed_read_not_an_empty_result(self):
        os.remove(os.path.join(self.source, "DSDT"))
        with self.assertRaises(linuxroot.RootError) as cm:
            linuxroot.copy_tables(self.source, self.dest)
        self.assertIn("no DSDT", str(cm.exception))

    def test_a_dsdt_that_is_not_a_dsdt_is_refused(self):
        with open(os.path.join(self.source, "DSDT"), "wb") as fh:
            fh.write(b"XXXX" + b"\0" * 32)
        with self.assertRaises(linuxroot.RootError):
            linuxroot.copy_tables(self.source, self.dest)

    def test_a_missing_sysfs_directory_is_a_failed_read(self):
        with self.assertRaises(linuxroot.RootError):
            linuxroot.copy_tables(os.path.join(self.temp.name, "absent"), self.dest)
        with self.assertRaises(linuxroot.RootError):
            linuxroot.copy_tables(self.source, None)

    def test_a_symlink_in_the_table_directory_is_not_followed(self):
        os.symlink(os.path.join(self.source, "DSDT"), os.path.join(self.source, "DSDT2"))
        written = linuxroot.copy_tables(self.source, self.dest)
        self.assertNotIn(os.path.join(self.dest, "DSDT2.aml"), written)


class Names(unittest.TestCase):
    def test_sysfs_names_become_the_builders_names(self):
        self.assertEqual(linuxroot._destination("DSDT"), "DSDT.aml")
        self.assertEqual(linuxroot._destination("dynamic/SSDT1"), "DYNAMIC/SSDT1.aml")

    def test_the_owner_argument_is_uid_colon_gid(self):
        self.assertEqual(linuxroot._owner("1000:1000"), (1000, 1000))
        self.assertIsNone(linuxroot._owner(None))
        with self.assertRaises(linuxroot.RootError):
            linuxroot._owner("1000")

    def test_table_has_checks_the_signature(self):
        temp = tempfile.NamedTemporaryFile(delete=False)
        self.addCleanup(os.remove, temp.name)
        temp.write(b"DSDT" + b"\0" * 8)
        temp.close()
        self.assertTrue(linuxroot.table_has(temp.name, b"DSDT"))
        self.assertFalse(linuxroot.table_has(temp.name, b"SSDT"))
        self.assertFalse(linuxroot.table_has(temp.name + ".missing", b"DSDT"))


class Elevation(unittest.TestCase):
    def test_when_already_root_the_copy_does_not_start_pkexec(self):
        with mock.patch.object(linuxroot.os, "geteuid", return_value=0), \
                mock.patch.object(linuxroot, "_write_acpi") as direct, \
                mock.patch.object(linuxroot.subprocess, "run") as run:
            self.assertIsNone(linuxroot.elevate_acpi("/tmp/acpi"))
        direct.assert_called_once_with("/tmp/acpi", None)
        run.assert_not_called()

    def test_a_dismissed_password_prompt_says_what_to_do(self):
        failed = mock.Mock(returncode=126, stdout="", stderr="Request dismissed")
        with mock.patch.object(linuxroot.os, "geteuid", return_value=1000), \
                mock.patch.object(linuxroot.shutil, "which", return_value="/usr/bin/pkexec"), \
                mock.patch.object(linuxroot.subprocess, "run", return_value=failed):
            with self.assertRaises(linuxroot.RootError) as cm:
                linuxroot.elevate_acpi("/tmp/acpi")
        self.assertIn("Approve the password prompt", str(cm.exception))

    def test_without_pkexec_the_error_names_the_package(self):
        with mock.patch.object(linuxroot.os, "geteuid", return_value=1000), \
                mock.patch.object(linuxroot.shutil, "which", return_value=None):
            with self.assertRaises(linuxroot.RootError) as cm:
                linuxroot.elevate_acpi("/tmp/acpi")
        self.assertIn("policykit", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
