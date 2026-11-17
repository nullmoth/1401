"""The Linux stick writer decides which disk may be erased and builds the partition table itself, so the parts that can
be checked without a stick are checked here: lsblk parsing, eligibility, the MBR bytes and the layout around them."""
import os
import struct
import tempfile
import unittest
from unittest import mock

from p1401 import linuxusb

GiB = linuxusb.GiB


def node(children=(), name="sdb", size=32 * GiB, tran="usb", ro=False, rm=True, serial="0123456789",
         vendor="Kingston", model="DataTraveler 3.0", rota=False):
    return {"name": name, "path": "/dev/" + name, "type": "disk", "size": size, "ro": ro, "rm": rm, "tran": tran,
            "model": model, "vendor": vendor, "serial": serial, "rota": rota, "children": list(children)}


def part_node(name="sdb1", size=16 * GiB, fstype="vfat", parttype="0x0c", label="1401", mounts=()):
    return {"name": name, "path": "/dev/" + name, "type": "part", "size": size, "fstype": fstype,
            "parttype": parttype, "label": label, "mountpoints": list(mounts)}


def part(size=16 * GiB, fstype="vfat", parttype="0x0c"):
    """A partition the way _disk hands it to the rest of the writer."""
    return {"Path": "/dev/sdb1", "Size": size, "FSType": fstype, "PartType": parttype, "Label": "1401",
            "Mountpoints": []}


def disk(**kw):
    args = dict(node())
    args.update(kw)
    with mock.patch.object(linuxusb, "_identity_links", lambda device: []):
        return linuxusb._disk(args)


class PartitionTable(unittest.TestCase):
    def test_the_first_entry_is_bootable_and_points_at_the_fat_partition(self):
        sector = linuxusb.mbr_bytes([(linuxusb.FAT32_LBA, 2048, 4194304, True)], signature=0x1234ABCD)
        self.assertEqual(len(sector), 512)
        self.assertEqual(sector[440:444], struct.pack("<I", 0x1234ABCD))
        entry = sector[446:462]
        self.assertEqual(entry[0], 0x80)
        self.assertEqual(entry[4], linuxusb.FAT32_LBA)
        self.assertEqual(struct.unpack("<II", entry[8:16]), (2048, 4194304))
        self.assertNotEqual(entry[1:4], b"\0\0\0")
        self.assertEqual(sector[510:], b"\x55\xaa")

    def test_an_unbootable_second_partition_has_no_boot_flag(self):
        sector = linuxusb.mbr_bytes([(linuxusb.FAT32_LBA, 2048, 1000, True), (linuxusb.EXFAT, 4096, 2000, False)])
        self.assertEqual(sector[446 + 16], 0)
        self.assertEqual(sector[446 + 16 + 4], linuxusb.EXFAT)

    def test_a_table_that_cannot_exist_is_refused(self):
        with self.assertRaises(linuxusb.UsbError):
            linuxusb.mbr_bytes([(linuxusb.FAT32_LBA, 0, 100, True)])
        with self.assertRaises(linuxusb.UsbError):
            linuxusb.mbr_bytes([(linuxusb.FAT32_LBA, 2048, 0, True)])
        with self.assertRaises(linuxusb.UsbError):
            linuxusb.mbr_bytes([(linuxusb.FAT32_LBA, 2048, 100, True)] * 5)

    def test_both_partitions_start_on_a_mebibyte_boundary(self):
        size = 32 * GiB
        parts = linuxusb.layout(size, linuxusb.PART_CAP, second=True)
        self.assertEqual(parts[0][1] * 512, linuxusb.MiB)
        self.assertEqual(parts[0][2] * 512, linuxusb.PART_CAP)
        self.assertEqual(parts[1][1] * 512 % linuxusb.MiB, 0)
        self.assertGreaterEqual(parts[1][1], parts[0][1] + parts[0][2])
        end = (parts[1][1] + parts[1][2]) * 512
        self.assertLessEqual(end, size - linuxusb.MiB)

    def test_the_installer_partition_never_runs_past_a_small_disk(self):
        parts = linuxusb.layout(4 * GiB, linuxusb.PART_CAP)
        self.assertLessEqual((parts[0][1] + parts[0][2]) * 512, 4 * GiB - linuxusb.MiB)

    def test_a_disk_too_small_for_the_requested_parts_is_refused(self):
        with self.assertRaises(linuxusb.UsbError):
            linuxusb.layout(3 * linuxusb.MiB, linuxusb.PART_CAP)
        with self.assertRaises(linuxusb.UsbError):
            linuxusb.layout(4 * GiB, linuxusb.PART_CAP, second=True)

    def test_kernel_names_get_p_before_the_partition_number_only_after_a_digit(self):
        self.assertEqual(linuxusb.partition_path("/dev/sda", 1), "/dev/sda1")
        self.assertEqual(linuxusb.partition_path("/dev/nvme0n1", 2), "/dev/nvme0n1p2")
        self.assertEqual(linuxusb.partition_path("/dev/mmcblk0", 1), "/dev/mmcblk0p1")


class Lsblk(unittest.TestCase):
    def test_a_usb_node_keeps_the_values_the_window_shows(self):
        d = disk(size=64 * GiB, serial="ABC", children=[part_node()])
        self.assertEqual(d["Path"], "/dev/sdb")
        self.assertEqual(d["FriendlyName"], "Kingston DataTraveler 3.0")
        self.assertEqual(d["BusType"], "USB")
        self.assertEqual(d["Size"], 64 * GiB)
        self.assertTrue(d["Removable"])
        self.assertFalse(d["IsSystem"])
        self.assertEqual(d["Partitions"][0]["FSType"], "vfat")
        self.assertEqual(d["Partitions"][0]["Mountpoints"], [])

    def test_a_mounted_root_makes_the_disk_a_system_disk(self):
        d = disk(children=[part_node(mounts=["/", "/home"])])
        self.assertTrue(d["IsSystem"])

    def test_a_system_behind_luks_or_lvm_is_still_the_system_disk(self):
        crypt = {"name": "cryptroot", "type": "crypt", "mountpoints": ["/"]}
        d = disk(children=[{**part_node(), "children": [crypt]}])
        self.assertTrue(d["IsSystem"])
        self.assertEqual(d["Mountpoints"], ["/"])

    def test_lsblk_before_2_37_reports_one_mountpoint(self):
        old = part_node(mounts=["/"])
        old.pop("mountpoints")
        old["mountpoint"] = "/"
        d = disk(children=[old])
        self.assertTrue(d["IsSystem"])

    def test_a_system_mount_is_matched_by_path_not_by_prefix(self):
        self.assertTrue(linuxusb._system_mount("/boot/efi"))
        self.assertFalse(linuxusb._system_mount("/mnt/boot"))
        self.assertFalse(linuxusb._system_mount("/run/media/user/1401"))

    def test_an_unknown_bus_is_shown_as_what_lsblk_said(self):
        self.assertEqual(disk(tran="")["BusType"], "UNKNOWN")
        self.assertEqual(disk(tran="sata")["BusType"], "SATA")
        self.assertEqual(disk(tran="nvme")["BusType"], "NVMe")

    def test_only_whole_disks_are_listed_and_zram_is_dropped(self):
        wait = {"name": "sda", "path": "/dev/sda", "type": "disk", "size": 500 * GiB, "tran": "sata",
                "children": [part_node(name="sda1")]}
        loop = {"name": "loop0", "path": "/dev/loop0", "type": "loop", "size": 10 * linuxusb.MiB}
        zram = {"name": "zram0", "path": "/dev/zram0", "type": "disk", "size": 8 * GiB}
        usb = node(children=[part_node()])
        with mock.patch.object(linuxusb, "_block_devices", lambda: [wait, loop, zram, usb]), \
                mock.patch.object(linuxusb, "_identity_links", lambda device: []):
            disks = linuxusb.list_disks()
        self.assertEqual([d["Path"] for d in disks], ["/dev/sda", "/dev/sdb"])
        self.assertEqual([d["Number"] for d in disks], [0, 1])

    def test_storage_rows_name_the_bus_and_the_media(self):
        with mock.patch.object(linuxusb, "list_disks", lambda: [
                {**disk(size=500 * GiB, tran="nvme", rota=False, vendor="Samsung", model="990 PRO"),
                 "Number": 0, "IsBoot": True, "IsSystem": True},
                {**disk(size=4 * 1000 ** 3, rota=True), "Number": 1, "IsBoot": False, "IsSystem": False}]):
            rows = linuxusb.storage_rows()
        self.assertEqual(rows[0]["Model"], "Samsung 990 PRO")
        self.assertEqual(rows[0]["BusType"], "NVMe")
        self.assertEqual(rows[0]["MediaType"], "SSD")
        self.assertTrue(rows[0]["IsSystem"])
        self.assertEqual(rows[1]["MediaType"], "HDD")


class Eligible(unittest.TestCase):
    def test_a_normal_usb_stick_is_accepted(self):
        self.assertTrue(linuxusb.eligible(disk())[0])

    def test_each_reason_is_named_for_the_person_who_picked_the_disk(self):
        cases = [
            ({"BusType": "SATA"}, "not a USB disk"),
            ({"IsSystem": True}, "running system"),
            ({"IsReadOnly": True}, "read-only"),
            ({"Size": 1 * GiB}, "too small"),
            ({"Size": 512 * GiB}, "larger than a USB stick"),
        ]
        for change, expected in cases:
            ok, why = linuxusb.eligible({**disk(), **change})
            self.assertFalse(ok, change)
            self.assertIn(expected, "; ".join(why))

    def test_a_large_drive_can_still_be_confirmed(self):
        big = {**disk(), "Size": 512 * GiB}
        self.assertFalse(linuxusb.eligible(big)[0])
        self.assertTrue(linuxusb.eligible(big, allow_large=True)[0])

    def test_a_disk_luks_or_lvm_still_holds_is_not_erased_under_it(self):
        crypt = {"name": "cryptroot", "type": "crypt", "mountpoints": []}
        d = disk(children=[{**part_node(), "children": [crypt]}])
        ok, why = linuxusb.eligible(d)
        self.assertFalse(ok)
        self.assertIn("crypt", "; ".join(why))


class WhatIsOnTheStick(unittest.TestCase):
    def test_mac_windows_and_linux_partitions_are_named(self):
        found = linuxusb.os_partitions({**disk(), "Partitions": [
            part(size=16 * GiB, parttype=linuxusb.APPLE_APFS, fstype="apfs"),
            part(size=32 * GiB, parttype=linuxusb.APPLE_HFS, fstype="hfsplus"),
            part(size=1 * GiB, parttype=linuxusb.WINDOWS_RECOVERY, fstype="ntfs"),
            part(size=64 * GiB, parttype=linuxusb.LINUX_FS_GUID, fstype="ext4")]})
        self.assertEqual([x.split()[0] for x in found], ["Mac", "Mac", "Windows", "Linux"])

    def test_an_ordinary_installer_stick_holds_nothing_the_user_must_confirm(self):
        plain = {**disk(), "Partitions": [part(), part(fstype="exfat", parttype="0x07")]}
        self.assertEqual(linuxusb.os_partitions(plain), [])

    def test_a_fat_partition_with_a_linux_type_is_still_linux(self):
        found = linuxusb.os_partitions({**disk(), "Partitions": [part(fstype="ext4")]})
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].startswith("Linux"))

    def test_an_encrypted_or_lvm_backup_is_named_before_it_is_erased(self):
        for fstype in ("crypto_luks", "lvm2_member"):
            found = linuxusb.os_partitions({**disk(), "Partitions": [part(fstype=fstype)]})
            self.assertEqual(len(found), 1)
            self.assertTrue(found[0].startswith("Linux"))


class SameStickAgain(unittest.TestCase):
    def test_the_serial_wins_over_a_new_device_node(self):
        first = {**disk(), "UniqueId": "OLD", "Path": "/dev/sdb"}
        again = {**disk(), "UniqueId": "NEW", "Path": "/dev/sdc"}
        self.assertIs(linuxusb.find_same([first, again], "NEW", 0, "other"), again)

    def test_a_controller_that_forgets_its_serial_falls_back_to_size_and_model(self):
        again = {**disk(), "UniqueId": "NEW", "Path": "/dev/sdc"}
        self.assertIs(linuxusb.find_same([again], "OLD", 32 * GiB, "Kingston DataTraveler 3.0"), again)

    def test_two_identical_sticks_are_not_guessed_between(self):
        one = {**disk(), "UniqueId": "A", "Path": "/dev/sdb"}
        two = {**disk(), "UniqueId": "B", "Path": "/dev/sdc"}
        self.assertIsNone(linuxusb.find_same([one, two], "", 32 * GiB, "Kingston DataTraveler 3.0"))

    def test_the_device_node_is_the_last_resort_only_with_the_same_size_and_name(self):
        one = {**disk(), "UniqueId": "", "Path": "/dev/sdb"}
        two = {**disk(), "UniqueId": "", "Path": "/dev/sdc"}
        self.assertIs(linuxusb.find_same([one, two], "", 32 * GiB, "Kingston DataTraveler 3.0", "/dev/sdc"), two)
        self.assertIsNone(linuxusb.find_same([one, two], "", 32 * GiB, "Kingston DataTraveler 3.0", "/dev/sdd"))


class WriteSafety(unittest.TestCase):
    def test_a_stick_holding_an_os_partition_is_refused_before_anything_is_erased(self):
        stick = {**disk(), "Partitions": [part(size=16 * GiB, parttype=linuxusb.APPLE_APFS, fstype="apfs")]}
        with mock.patch.object(linuxusb, "list_disks", return_value=[stick]), \
                mock.patch("p1401.validate.validate", return_value={"ok": True}), \
                mock.patch.object(linuxusb, "_wipe") as wipe:
            with self.assertRaises(linuxusb.UsbError) as cm:
                linuxusb.write(stick, "/build", {"local": True})
        self.assertIn("1401-OS-PARTITIONS", str(cm.exception))
        wipe.assert_not_called()

    def test_a_rebuilt_efi_that_no_longer_validates_stops_before_the_erase(self):
        with mock.patch("p1401.validate.validate", return_value={"ok": False, "invariants": ["bad config"]}), \
                mock.patch.object(linuxusb, "list_disks") as disks, \
                mock.patch.object(linuxusb, "_wipe") as wipe:
            with self.assertRaises(linuxusb.UsbError) as cm:
                linuxusb.write(disk(), "/build", {"local": True})
        self.assertIn("bad config", str(cm.exception))
        disks.assert_not_called()
        wipe.assert_not_called()


class DriverPrep(unittest.TestCase):
    def prepare(self, older, kit=None):
        kit = kit or {"name": "nullmoth-nvidia-legacy-14.tar.gz", "url": "https://example.invalid/kit.tar.gz",
                      "sha256": "a" * 64}
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)

        def fetch(url, path):
            with open(path, "wb") as fh:
                fh.write(b"package")

        with mock.patch("p1401.usbwriter.needs_nullmoth", return_value=True), \
                mock.patch("p1401.legacy.read_marker", return_value=older), \
                mock.patch("p1401.legacy.kit", return_value=kit), \
                mock.patch.object(linuxusb, "_sha256", return_value=kit["sha256"]), \
                mock.patch("p1401.usbwriter._fetch", side_effect=fetch) as fetch_mock:
            prepared = linuxusb.prepare_driver(temp.name, say=lambda message: None)
        return prepared, fetch_mock

    def test_an_experimental_target_gets_its_own_kit(self):
        prepared, fetch = self.prepare(23)
        self.assertEqual([os.path.basename(p) for p in prepared], ["nullmoth-nvidia-legacy-14.tar.gz"])
        self.assertEqual(fetch.call_args[0][0], "https://example.invalid/kit.tar.gz")

    def test_a_kit_without_a_pin_is_not_downloaded(self):
        with self.assertRaises(linuxusb.UsbError):
            self.prepare(23, {"name": "unreleased.tar.gz", "url": "https://example.invalid/kit.tar.gz", "sha256": ""})


class SmallText(unittest.TestCase):
    def test_sizes_are_shown_the_way_the_windows_writer_shows_them(self):
        self.assertEqual(linuxusb.size_text(16 * GiB), "16 GB")
        self.assertEqual(linuxusb.size_text(512 * linuxusb.MiB), "512 MB")
        self.assertEqual(linuxusb.stick_name(disk()), "Kingston DataTraveler 3.0 (32 GB)")


if __name__ == "__main__":
    unittest.main()
