"""Two 2.0.2 write failures that were not the stick: a disk number Windows had already reassigned (the write stopped
before touching anything and told the user the stick was faulty), and a volume that went away between being listed and
being opened for the lock ("cannot open \\\\?\\Volume{...} (Windows error 2)")."""
import unittest
from unittest.mock import patch

from p1401 import rawdisk, usbwriter


class StaleNumber(unittest.TestCase):
    def test_a_reassigned_number_says_so_and_does_not_blame_the_stick(self):
        with patch.object(usbwriter, "list_disks", return_value=[{"Number": 3, "BusType": "USB", "Size": 16 * 10**9}]), \
             patch("builtins.print") as out:
            rc = usbwriter.cli_write(["2", "efi", "24"])
        line = " ".join(str(c.args[0]) for c in out.call_args_list if c.args)
        self.assertEqual(rc, 1)
        self.assertIn("1401-DISK-RENUMBERED", line)
        self.assertNotIn(usbwriter.STICK_ADVICE.strip()[:40], line)
        self.assertIn("USB: 3: ? 14.9 GiB", line)   # the log names where the stick went (2.0.3 logs could not)

    def test_the_window_reloads_its_list_on_that_stop(self):
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[1] / "windows/App/MainForm.cs").read_text()
        self.assertIn('l.Contains("1401-DISK-RENUMBERED"))) FillDisks();', src)


class EmptyList(unittest.TestCase):
    """2.4.3 (10-19..21): 36 "DISK-RENUMBERED" stops came after "Windows lists 0 disk(s)" - PowerShell saw no disk at
    all, not a stick that moved. That is its own stop, with the PowerShell's context in the log."""

    def test_no_disks_at_all_is_not_called_a_renumbered_stick(self):
        with patch.object(usbwriter, "list_disks", return_value=[]), \
             patch.object(usbwriter, "_log_powershell_context") as ctx, patch("builtins.print") as out:
            rc = usbwriter.cli_write(["2", "efi", "24"] + IDENT)
        line = " ".join(str(c.args[0]) for c in out.call_args_list if c.args)
        self.assertEqual(rc, 1)
        self.assertIn("1401-DISK-LIST-EMPTY", line)
        self.assertNotIn("1401-DISK-RENUMBERED", line)
        self.assertIn("Nothing was erased", line)
        ctx.assert_called_once()

    def test_the_context_line_counts_every_other_route_to_the_disks(self):
        with patch.object(usbwriter, "_ps", return_value="PowerShell 5.1 wmi-MSFT_Disk=2 Win32_DiskDrive=2 subsystems=0 admin=True") as ps, \
             patch("builtins.print") as out:
            usbwriter._log_powershell_context()
        script = ps.call_args.args[0]
        for route in ("Get-WmiObject -Namespace root/Microsoft/Windows/Storage -Class MSFT_Disk", "Win32_DiskDrive",
                      "Get-StorageSubSystem", "WindowsBuiltInRole]::Administrator"):
            self.assertIn(route, script)
        self.assertIn("Win32_DiskDrive=2", " ".join(str(c.args[0]) for c in out.call_args_list))

    def test_the_context_line_never_raises(self):
        with patch.object(usbwriter, "_ps", side_effect=usbwriter.UsbError("blocked")), patch("builtins.print") as out:
            usbwriter._log_powershell_context()
        self.assertIn("disk list context unavailable", " ".join(str(c.args[0]) for c in out.call_args_list))


STICK = {"Number": 2, "BusType": "USB", "Size": 16 * 10**9, "FriendlyName": "SanDisk Ultra", "UniqueId": "USBSTOR-AAA"}
OTHER = {"Number": 2, "BusType": "USB", "Size": 32 * 10**9, "FriendlyName": "Kingston", "UniqueId": "USBSTOR-BBB"}
IDENT = ["--stick-id", "USBSTOR-AAA", "--stick-size", str(16 * 10**9), "--stick-name", "SanDisk Ultra"]


class Renumbered(unittest.TestCase):
    """26 PCs on 2.1.0 stopped with 1401-DISK-RENUMBERED: the window now names the stick, and the writer finds it again."""

    def test_the_stick_is_found_under_its_new_number(self):
        moved = dict(STICK, Number=5)
        self.assertEqual(usbwriter.refind([OTHER, moved], "USBSTOR-AAA", STICK["Size"], "SanDisk Ultra")["Number"], 5)

    def test_a_different_disk_that_took_the_number_is_never_chosen(self):
        self.assertIsNone(usbwriter.refind([OTHER], "USBSTOR-AAA", STICK["Size"], "SanDisk Ultra"))

    def test_size_and_model_find_it_when_the_id_changed(self):
        moved = dict(STICK, Number=4, UniqueId="USBSTOR-NEW")
        self.assertEqual(usbwriter.refind([OTHER, moved], "USBSTOR-AAA", STICK["Size"], "SanDisk Ultra")["Number"], 4)

    def test_two_identical_sticks_without_the_id_are_not_guessed(self):
        a, b = dict(STICK, Number=4, UniqueId="X1"), dict(STICK, Number=6, UniqueId="X2")
        self.assertIsNone(usbwriter.refind([a, b], "USBSTOR-AAA", STICK["Size"], "SanDisk Ultra"))

    def test_the_write_continues_on_the_new_number(self):
        moved = dict(STICK, Number=5)
        with patch.object(usbwriter, "list_disks", return_value=[moved]), \
             patch.object(usbwriter, "eligible", side_effect=lambda d, a=False: (False, [f"STOPHERE {d['Number']}"])), \
             patch("builtins.print") as out:
            rc = usbwriter.cli_write(["2", "efi", "24"] + IDENT)
        line = " ".join(str(c.args[0]) for c in out.call_args_list if c.args)
        self.assertIn("the stick is disk 5 now (it was disk 2", line)
        self.assertIn("STOPHERE 5", line)          # it went on with disk 5, not 2
        self.assertNotIn("1401-DISK-RENUMBERED", line)

    def test_the_number_now_held_by_another_disk_stops_instead_of_erasing_it(self):
        with patch.object(usbwriter, "list_disks", return_value=[OTHER]), patch("builtins.print") as out:
            rc = usbwriter.cli_write(["2", "efi", "24"] + IDENT)
        line = " ".join(str(c.args[0]) for c in out.call_args_list if c.args)
        self.assertEqual(rc, 1)
        self.assertIn("1401-DISK-RENUMBERED", line)

    def test_the_window_passes_the_stick_identity(self):
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[1] / "windows/App/MainForm.cs").read_text()
        self.assertIn('args += " --stick-id " + Engine.Q(d.UniqueId)', src)


class GetDiskEmpty(unittest.TestCase):
    """2.2.0: Get-Disk listed nothing on two PCs whose window had listed the stick through MSFT_Disk."""

    def fake_ps(self, cim):
        def ps(script):
            return "" if script.startswith("Get-Disk") else cim
        return ps

    def test_msft_disk_is_used_and_its_codes_are_named(self):
        cim = '[{"Number":5,"FriendlyName":"SanDisk Ultra","UniqueId":"USBSTOR-AAA","BusType":7,"Size":16000000000,"PartitionStyle":2}]'
        with patch.object(usbwriter, "_ps", self.fake_ps(cim)), patch("builtins.print"):
            d = usbwriter.list_disks()
        self.assertEqual(d[0]["BusType"], "USB")
        self.assertEqual(d[0]["PartitionStyle"], "GPT")

    def test_the_write_finds_the_stick_through_msft_disk(self):
        cim = '[{"Number":5,"FriendlyName":"SanDisk Ultra","UniqueId":"USBSTOR-AAA","BusType":7,"Size":16000000000}]'
        with patch.object(usbwriter, "_ps", self.fake_ps(cim)), \
             patch.object(usbwriter, "eligible", side_effect=lambda d, a=False: (False, [f"STOPHERE {d['Number']} {d['BusType']}"])), \
             patch("builtins.print") as out:
            usbwriter.cli_write(["2", "efi", "24"] + IDENT)
        line = " ".join(str(c.args[0]) for c in out.call_args_list if c.args)
        self.assertIn("STOPHERE 5 USB", line)
        self.assertNotIn("1401-DISK-RENUMBERED", line)

    def test_get_disk_results_are_used_when_present(self):
        calls = []
        def ps(script):
            calls.append(script); return '[{"Number":1,"BusType":"USB"}]'
        with patch.object(usbwriter, "_ps", ps):
            usbwriter.list_disks()
        self.assertEqual(len(calls), 1)   # no MSFT_Disk query when Get-Disk answered

    def test_no_disks_at_all_repairs_the_storage_provider_once_and_retries(self):
        # 2.3.0 write log: both queries empty ("Windows lists 0 disk(s)"); the user's fix was mofcomp storagewmi.mof
        state = {"repaired": False, "repairs": 0}
        def ps(script):
            if not state["repaired"]: return ""
            return '[{"Number":2,"BusType":"USB","UniqueId":"USBSTOR-BBB"}]' if script.startswith("Get-Disk") else ""
        def repair():
            state["repairs"] += 1; state["repaired"] = True; return True
        with patch.object(usbwriter, "_ps", ps), patch.object(usbwriter, "_repair_storage_wmi", repair), patch("builtins.print"):
            d = usbwriter.list_disks()
        self.assertEqual(state["repairs"], 1)
        self.assertEqual(d[0]["Number"], 2)

    def test_a_repair_that_does_not_help_is_tried_only_once(self):
        calls = {"repairs": 0}
        def repair():
            calls["repairs"] += 1; return True
        with patch.object(usbwriter, "_ps", lambda s: ""), patch.object(usbwriter, "_repair_storage_wmi", repair), \
             patch("builtins.print"):
            d = usbwriter.list_disks()
        self.assertEqual(d, [])
        self.assertEqual(calls["repairs"], 1)

    def test_a_working_provider_is_never_repaired(self):
        with patch.object(usbwriter, "_ps", lambda s: '[{"Number":1,"BusType":"USB"}]'), \
             patch.object(usbwriter, "_repair_storage_wmi", side_effect=AssertionError("repaired a working provider")):
            usbwriter.list_disks()


class VanishedVolume(unittest.TestCase):
    def run_wipe(self, vol_error):
        said = []

        def opener(k, p):
            if p.startswith("\\\\?\\Volume"):
                raise rawdisk.DiskError(f"cannot open {p} ({vol_error})")
            return 7
        with patch.object(rawdisk, "_k32", lambda: type("K", (), {"CloseHandle": lambda *a: None})()), \
             patch.object(rawdisk, "_volumes_on", lambda k, d: ["\\\\?\\Volume{6cff5f1e}"]), \
             patch.object(rawdisk, "_open", opener), patch.object(rawdisk, "_lock_volume", lambda k, h: True), \
             patch.object(rawdisk, "_ioctl", lambda k, h, code, inbuf=b"", outsize=0: (True, b"", 0)), \
             patch.object(rawdisk, "_write_at", lambda k, h, off, data: 0):
            rawdisk.wipe_mbr_fat32(3, 16 << 30, 1 << 30, say=said.append)
        return said

    def test_a_volume_that_went_away_is_skipped_and_the_erase_goes_on(self):
        said = self.run_wipe("Windows error 2")
        self.assertTrue(any("went away" in s for s in said), said)

    def test_any_other_open_error_still_stops(self):
        with self.assertRaises(rawdisk.DiskError):
            self.run_wipe("Windows error 5")


if __name__ == "__main__":
    unittest.main()
