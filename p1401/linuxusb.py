"""Writes the 1401 installer USB on Linux.

Same layout as the Windows writer: an MBR disk with one small FAT32 partition carrying EFI/ and
com.apple.recovery.boot/. The macOS image is downloaded from Apple and checked chunk by chunk, the EFI is copied and
read back, and the optional full installer gets a second exFAT partition. The Windows module still owns the payload
stage; this one does the disk work with Linux' own tools.

The destructive part is deliberately small: the partition table is replaced through the block device, then mkfs.vfat
formats the new partition. Nothing here calls parted or sfdisk, because both change their command lines between the
versions that ship on LTS distributions.

    python3 -m p1401.linuxusb list
    python3 -m p1401.linuxusb write /dev/sdX <EFI build> 24 [options]

Everything below `write` runs as root, normally through `pkexec p1401/linuxroot.py usb ...`. The list command does not:
it only reads lsblk and /dev/disk/by-id.
"""
import json
import os
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time

GiB = 1 << 30
MiB = 1 << 20
MIN_DISK = 2 * GiB
MAX_DISK = 256 * GiB
PART_CAP = 16 * GiB
LABEL = "1401"
SECOND_LABEL = "NMINSTALL"
FAT32_LBA = 0x0C
EXFAT = 0x07
MBR_BOOT = 0x80

APPLE_APFS = "7c3457ef-0000-11aa-aa11-00306543ecac"
APPLE_HFS = "48465300-0000-11aa-aa11-00306543ecac"
WINDOWS_RECOVERY = "de94bba4-06d1-4d40-a16a-bfd50179d6ac"
LINUX_FS_GUID = "0fc63daf-8483-4772-8e79-3d69d8477de4"

SYSTEM_ROOTS = ("/", "/boot", "/boot/efi", "/home", "/usr", "/etc", "/var", "/opt", "/srv", "/root", "/nix", "/snap")
BUS_NAMES = {"usb": "USB", "sata": "SATA", "ata": "ATA", "nvme": "NVMe", "mmc": "MMC", "sd": "SD", "sas": "SAS"}

RECOVERY_DIR = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share"),
                            "nullmoth", "1401", "Recovery")


class UsbError(RuntimeError):
    pass


def _run(command, timeout=120, check=True):
    try:
        p = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise UsbError(f"{command[0]} is not installed") from None
    except subprocess.TimeoutExpired:
        raise UsbError(f"{command[0]} did not finish within {timeout} seconds") from None
    if check and p.returncode != 0:
        detail = " ".join((p.stderr or p.stdout or "").split())[-500:]
        raise UsbError(f"{' '.join(command)} failed: {detail or f'exit {p.returncode}'}")
    return p


def size_text(value):
    if value >= GiB:
        return f"{value / GiB:.0f} GB" if value >= 10 * GiB else f"{value / GiB:.1f} GB"
    return f"{value / (1 << 20):.0f} MB"


def _sha256(path, block=1 << 20):
    import hashlib  # noqa: PLC0415
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(block), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_driver(efi_build_dir, say=print):
    """Download the pinned NVIDIA packages into the build's cache while still the user.

    The writer itself may run as root; if it fetched these, the build folder would end up with root-owned files and
    the next ordinary build could not clear it. Returns the paths prepared (empty when this build needs no driver).
    An experimental target has a kit per macOS release instead of the 15/26 package.
    """
    from . import legacy, nullmoth, usbwriter  # noqa: PLC0415
    if not usbwriter.needs_nullmoth(efi_build_dir):
        say("OK no NVIDIA driver package is needed for this build")
        return []
    older = legacy.read_marker(efi_build_dir)
    if older:
        package = legacy.kit(older)
        if not package.get("sha256"):
            raise UsbError(f"the NVIDIA driver kit for {legacy.NAME[older]} has no pinned SHA-256 yet, so 1401 will "
                           "not put an unchecked package on the stick")
        packages = [package]
    else:
        packages = [nullmoth.PACKAGE, nullmoth.FIRMWARE_RUN]
    cache = os.path.join(efi_build_dir, ".cache")
    os.makedirs(cache, exist_ok=True)
    prepared = []
    for package in packages:
        target = os.path.join(cache, package["name"])
        if os.path.isfile(target) and _sha256(target) == package["sha256"]:
            say(f"OK {package['name']} is already downloaded and checked")
            prepared.append(target)
            continue
        say(f"STEP downloading {package['name']}")
        part = target + ".part"
        if os.path.exists(part):
            os.remove(part)
        try:
            usbwriter._fetch(package["url"], part)
        except Exception as error:  # noqa: BLE001 - the mirror is the second chance the writer uses too
            mirror = nullmoth.mirror_of(package["url"])
            if not mirror:
                raise UsbError(f"could not download {package['name']}: {error}") from None
            say(f"(GitHub download failed: {error}; trying the NullMoth mirror)")
            usbwriter._fetch(mirror, part)
        if _sha256(part) != package["sha256"]:
            os.remove(part)
            raise UsbError(f"{package['name']} does not match its pinned SHA-256 - nothing will be put on the stick")
        os.replace(part, target)
        _give_back(target, efi_build_dir)
        say(f"OK downloaded and checked {package['name']}")
        prepared.append(target)
    return prepared


def _mountpoints(part):
    raw = part.get("mountpoints")
    if raw is None:
        # util-linux before 2.37 has no MOUNTPOINTS column and calls it MOUNTPOINT instead.
        raw = [part.get("mountpoint")] if part.get("mountpoint") else []
    return [p for p in raw if p and not p.startswith("[")]


def _system_mount(path):
    # "/" is a root of its own; matching every absolute path against it would make every mounted stick a system disk.
    return any(path == root or (root != "/" and path.startswith(root.rstrip("/") + "/")) for root in SYSTEM_ROOTS)


def _nodes(block):
    for node in block or []:
        yield node
        yield from _nodes(node.get("children"))


def _block_devices():
    columns = "NAME,PATH,TYPE,SIZE,RO,RM,TRAN,MODEL,SERIAL,VENDOR,ROTA,MOUNTPOINTS,PARTTYPE,FSTYPE,LABEL"
    command = ["lsblk", "-J", "-b", "-o", columns]
    try:
        p = _run(command, timeout=30)
    except UsbError:
        # MOUNTPOINTS arrived in util-linux 2.37. A distribution still on 2.36 answers "unknown column"; the single
        # MOUNTPOINT it does have is enough to recognise the running system's disk.
        p = _run(["lsblk", "-J", "-b", "-o", columns.replace("MOUNTPOINTS", "MOUNTPOINT")], timeout=30)
    try:
        return json.loads(p.stdout or "{}").get("blockdevices") or []
    except ValueError as error:
        raise UsbError(f"lsblk returned something other than JSON ({error})") from None


def _identity_links(device):
    folder = "/dev/disk/by-id"
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    found = []
    for name in names:
        path = os.path.join(folder, name)
        try:
            if os.path.realpath(path) == os.path.realpath(device):
                found.append(name)
        except OSError:
            continue
    return sorted(found)


def _disk(node):
    name = (node.get("name") or "").strip()
    device = (node.get("path") or ("/dev/" + name)).strip()
    model = " ".join(x for x in ((node.get("vendor") or "").strip(), (node.get("model") or "").strip()) if x)
    bus = BUS_NAMES.get((node.get("tran") or "").lower(), (node.get("tran") or "unknown").upper())
    parts = []
    for child in node.get("children") or []:
        if (child.get("type") or "") != "part":
            continue
        parts.append({"Path": child.get("path") or ("/dev/" + (child.get("name") or "")),
                      "Size": int(child.get("size") or 0),
                      "FSType": (child.get("fstype") or "").lower(),
                      "PartType": (child.get("parttype") or "").lower(),
                      "Label": child.get("label") or "",
                      "Mountpoints": _mountpoints(child)})
    mounts = [m for child in _nodes(node.get("children")) for m in _mountpoints(child)]
    system = any(_system_mount(m) for m in mounts)
    stacked = [{"Name": child.get("name") or "", "Type": child.get("type") or ""}
               for child in _nodes(node.get("children")) if (child.get("type") or "") not in ("part", "disk")]
    links = _identity_links(device)
    uid = (node.get("serial") or "").strip()
    if not uid:
        uid = next((n for n in links if not n.startswith("wwn-")), device)
    return {"Number": 0, "Path": device, "Name": name, "FriendlyName": model or name or device,
            "SerialNumber": (node.get("serial") or "").strip(), "UniqueId": uid, "BusType": bus,
            "Size": int(node.get("size") or 0), "IsBoot": system, "IsSystem": system,
            "IsOffline": False, "IsReadOnly": bool(node.get("ro")),
            "Removable": bool(node.get("rm")), "Rotational": bool(node.get("rota")),
            "Partitions": parts, "Mountpoints": mounts, "Byid": links, "PartitionStyle": "unknown",
            "Stacked": stacked}


def list_disks():
    """Every whole disk lsblk reports, system disk included. The GUI and eligibility() decide what is writable."""
    disks = []
    for node in _block_devices():
        if (node.get("type") or "") != "disk":
            continue
        if (node.get("name") or "").startswith("zram"):
            continue
        disk = _disk(node)
        disk["Number"] = len(disks)
        disks.append(disk)
    return disks


def storage_rows():
    """The scan's Storage Drives section, shaped like the Windows Get-Disk rows."""
    rows = []
    for disk in list_disks():
        rows.append({"Number": disk["Number"], "Model": disk["FriendlyName"], "BusType": disk["BusType"],
                     "MediaType": "SSD" if not disk["Rotational"] else "HDD", "Size": disk["Size"],
                     "IsBoot": disk["IsBoot"], "IsSystem": disk["IsSystem"]})
    return rows


def stick_name(disk):
    return f"{disk.get('FriendlyName') or 'the USB stick'} ({size_text(int(disk.get('Size') or 0))})"


def eligible(disk, allow_large=False):
    """Every reason this disk cannot be erased, worded for the person who picked it."""
    why = []
    if disk.get("BusType") != "USB":
        why.append(f"not a USB disk (bus: {disk.get('BusType')})")
    if disk.get("IsSystem"):
        why.append("this disk holds the running system's partitions")
    if disk.get("IsReadOnly"):
        why.append("the stick is read-only (check the lock switch, or use another stick)")
    if disk.get("Stacked"):
        kinds = sorted({str(item.get("Type") or "device") for item in disk["Stacked"]})
        why.append(f"Linux is still using this disk through {', '.join(kinds)}; close or unlock that first")
    size = int(disk.get("Size") or 0)
    if size < MIN_DISK:
        why.append(f"too small ({size / GiB:.1f} GB; the installer needs 2)")
    if size > MAX_DISK and not allow_large:
        why.append(f"{size / GiB:.0f} GB is larger than a USB stick 1401 expects - confirm it is not a backup drive")
    return not why, why


def os_partitions(disk):
    """What on this stick looks like an operating system, as short labels. Empty for a normal installer stick."""
    found = []
    for part in disk.get("Partitions") or []:
        kind = part.get("PartType") or ""
        fstype = part.get("FSType") or ""
        label = ""
        if kind == APPLE_APFS or fstype == "apfs":
            label = "Mac APFS"
        elif kind == APPLE_HFS or fstype in ("hfsplus", "hfs"):
            label = "Mac HFS+"
        elif kind == WINDOWS_RECOVERY:
            label = "Windows recovery"
        elif kind == LINUX_FS_GUID or fstype in ("ext2", "ext3", "ext4", "btrfs", "xfs", "f2fs", "zfs_member",
                                                  "crypto_luks", "lvm2_member"):
            label = "Linux"
        if label:
            found.append(f"{label} {size_text(int(part.get('Size') or 0))}")
    return found


def find_same(disks, uid, size, name, path=None):
    """The stick that was picked, found again by what it is instead of the device node it had.

    USB storage can come back as /dev/sdc after a replug, and a different stick can take /dev/sdb. The serial is
    checked first; controllers that invent a new serial on every read fall back to size and model, and only when
    exactly one USB disk matches. `path` is the last resort for a stick with neither a serial nor a model.
    """
    uid = (uid or "").strip()
    if uid:
        hit = [d for d in disks if (d.get("UniqueId") or "").strip() == uid]
        if len(hit) == 1:
            return hit[0]
    want = int(size or -1)
    hit = [d for d in disks if d.get("BusType") == "USB" and int(d.get("Size") or 0) == want
           and (d.get("FriendlyName") or "").strip() == (name or "").strip()]
    if len(hit) == 1:
        return hit[0]
    if path:
        hit = [d for d in disks if d.get("Path") == path and int(d.get("Size") or 0) == want
               and (d.get("FriendlyName") or "").strip() == (name or "").strip()]
    return hit[0] if len(hit) == 1 else None


def partition_path(device, number=1):
    """sda1, but nvme0n1p1 and mmcblk0p1: the kernel adds p after a name that ends in a digit."""
    return device + ("p" if device[-1:].isdigit() else "") + str(int(number))


def _chs(lba):
    heads, sectors = 255, 63
    cylinder, rest = divmod(lba, heads * sectors)
    if cylinder > 1023:
        return b"\xfe\xff\xff"
    head, sector = divmod(rest, sectors)
    return bytes((head, ((cylinder >> 2) & 0xC0) | (sector + 1), cylinder & 0xFF))


def mbr_bytes(parts, signature=None):
    """A 512-byte MBR. parts is [(type, start_lba, sector_count, boot)]; boot is a bool."""
    if len(parts) > 4:
        raise UsbError("an MBR holds four primary partitions")
    if signature is None:
        signature = struct.unpack("<I", os.urandom(4))[0] or 1
    table = bytearray()
    for kind, start, count, boot in parts:
        start, count = int(start), int(count)
        if start <= 0 or count <= 0:
            raise UsbError("partition start and size must be positive")
        table += bytes((MBR_BOOT if boot else 0,)) + _chs(start) + bytes((kind,)) + _chs(start + count - 1)
        table += struct.pack("<II", start, count)
    table += bytes(64 - len(table))
    sector = bytearray(440)
    sector += struct.pack("<I", signature)
    sector += b"\x00\x00"
    sector += table
    sector += b"\x55\xaa"
    if len(sector) != 512:
        raise UsbError("built an MBR that is not 512 bytes")
    return bytes(sector)


def layout(size, first_bytes, second=False):
    """[(type, start_lba, sectors, boot)] for a disk of `size` bytes. Both partitions start on a 1 MiB boundary."""
    start = MiB // 512
    if size < 4 * MiB:
        raise UsbError("this disk is too small to hold a partition table")
    first = min(int(first_bytes), ((size - 2 * MiB) // 512) * 512)
    if first <= 0:
        raise UsbError("this disk is too small for the installer partition")
    parts = [(FAT32_LBA, start, first // 512, True)]
    if second:
        second_start = ((start * 512 + first + MiB - 1) // MiB) * (MiB // 512)
        left = ((size - MiB - second_start * 512) // 512) * 512
        if left <= 0:
            raise UsbError("this disk has no room for a second partition")
        parts.append((EXFAT, second_start, left // 512, False))
    return parts


def _unmount(disk):
    for part in disk.get("Partitions") or []:
        if (part.get("FSType") or "") == "swap" and os.path.exists(part["Path"]):
            _run(["swapoff", part["Path"]], check=False)
        for mountpoint in part.get("Mountpoints") or []:
            p = _run(["umount", mountpoint], check=False, timeout=60)
            if p.returncode != 0:
                # A lazy unmount leaves the stick detached from the tree while the old superblock is still in use;
                # the write replaces that superblock, so a busy mount cannot be allowed to stay.
                p = _run(["umount", "-l", mountpoint], check=False, timeout=60)
                if p.returncode != 0:
                    raise UsbError(f"cannot unmount {mountpoint}: close programs using the stick and try again")


def _settle(device, partition):
    for command in (["blockdev", "--rereadpt", device], ["partprobe", device], ["udevadm", "settle", "--timeout=10"]):
        if shutil.which(command[0]):
            _run(command, check=False, timeout=30)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if os.path.exists(partition):
            return
        time.sleep(0.25)
    raise UsbError(f"the kernel did not create {partition} after the partition table was written. "
                   "Unplug the stick, plug it into another USB port and try again")


def _wipe(device, size, parts, say=print):
    """Zero both ends of the disk and write the MBR. The disk must already be unmounted."""
    try:
        mode = os.stat(device).st_mode
    except OSError as error:
        raise UsbError(f"cannot open {device}: {error.strerror}") from None
    if not stat.S_ISBLK(mode):
        raise UsbError(f"{device} is not a block device")
    zero = bytes(MiB)
    try:
        fd = os.open(device, os.O_RDWR | os.O_CLOEXEC)
    except PermissionError:
        raise UsbError(f"root is needed to write {device}; start the app through pkexec") from None
    try:
        tail = ((size - MiB) // 512) * 512
        os.pwrite(fd, zero, 0)
        if tail > 0:
            os.pwrite(fd, zero, tail)
        os.pwrite(fd, mbr_bytes(parts), 0)
        os.fsync(fd)
        say(f"OK erased {device} and wrote a new partition table")
    except OSError as error:
        raise UsbError(f"writing to {device} failed: {error.strerror}") from None
    finally:
        try:
            import fcntl  # noqa: PLC0415 - only needed here
            fcntl.ioctl(fd, 0x125F)   # BLKRRPART: ask the kernel to read the table just written
        except OSError:
            pass
        os.close(fd)


def _mkfs(device, label=LABEL, fat=True):
    if fat:
        tool = shutil.which("mkfs.vfat") or shutil.which("mkfs.fat")
        if not tool:
            raise UsbError("mkfs.vfat is missing. Install dosfstools and try again.")
        _run([tool, "-F", "32", "-n", label, device], timeout=300)
    else:
        tool = shutil.which("mkfs.exfat")
        if not tool:
            raise UsbError("mkfs.exfat is missing. Install exfatprogs (or exfat-utils) to use the full installer option.")
        _run([tool, "-n", label, device], timeout=300)


def _mount(device, mountpoint):
    os.makedirs(mountpoint, exist_ok=True)
    _run(["mount", device, mountpoint], timeout=60)
    return mountpoint


def _unmount_path(path):
    # The payload is verified before this runs. umount waits for the kernel to write it out, and a slow stick can
    # take minutes for 1.5 GB: a verified Sequoia stick was reported failed because the old 90-second limit ran out
    # while the kernel was still flushing it. Flush the filesystem first, then give umount room for slow media.
    _run(["sync", "-f", path], check=False, timeout=600)
    p = _run(["umount", path], check=False, timeout=300)
    if p.returncode != 0:
        p = _run(["umount", "-l", path], check=False, timeout=60)
        if p.returncode != 0:
            raise UsbError(f"cannot unmount {path}; close programs using the stick and try again")


def write(disk, efi_build_dir, recovery_info, allow_large=False, progress=None, machine_profile=None,
          erase_os=False, opt_in=None, full_pkg=None, extras=()):
    """Erases the stick, then writes the recovery image and the EFI. Returns the payload result."""
    from . import fullinstaller, usbwriter, validate  # noqa: PLC0415

    ok, why = eligible(disk, allow_large)
    if not ok:
        raise UsbError("refusing: " + "; ".join(why))
    checked = validate.validate(efi_build_dir)
    if not checked.get("ok"):
        reasons = checked.get("invariants") or [checked.get("error") or "The OpenCore configuration did not pass validation."]
        raise UsbError("The EFI must be rebuilt before erasing the stick: " + "; ".join(reasons)
                       + usbwriter.gone_hint(reasons))
    if machine_profile is not None:
        from . import machine_handoff  # noqa: PLC0415
        if machine_handoff.verified(efi_build_dir) != machine_profile:
            raise UsbError("The machine profile changed before erasing the stick. Rebuild the EFI.")
    found = find_same(list_disks(), disk.get("UniqueId"), disk.get("Size"), disk.get("FriendlyName"), disk.get("Path"))
    if found is None:
        raise UsbError("1401-DISK-RENUMBERED: the stick is not attached any more, or another disk has taken its "
                       "place. Nothing was erased. Press Refresh, pick the stick again and write.")
    ok, why = eligible(found, allow_large)
    if not ok:
        raise UsbError("refusing: " + "; ".join(why))
    disk = found
    if not erase_os:
        held = os_partitions(disk)
        if held:
            raise UsbError(f"1401-OS-PARTITIONS: {stick_name(disk)} holds {', '.join(held)}. Nothing was erased.")
    if full_pkg:
        try:
            fullinstaller.check_stick(int(disk.get("Size") or 0))
            fullinstaller.verify_xar(full_pkg)
        except (fullinstaller.FullInstallerError, OSError) as error:
            raise UsbError(f"1401-FULL-INSTALLER: {error}") from None
    device = disk["Path"]
    first = fullinstaller.FIRST_PARTITION if full_pkg else PART_CAP
    parts = layout(int(disk["Size"]), first, second=bool(full_pkg))
    _unmount(disk)
    _wipe(device, int(disk["Size"]), parts, say=lambda m: print(m, flush=True))
    first_device = partition_path(device, 1)
    _settle(device, first_device)
    _mkfs(first_device)
    second_device = None
    if full_pkg:
        second_device = partition_path(device, 2)
        _settle(device, second_device)
        _mkfs(second_device, SECOND_LABEL, fat=False)

    work = tempfile.mkdtemp(prefix="1401-usb-")
    mounted = []
    try:
        root = _mount(first_device, os.path.join(work, "first"))
        mounted.append(root)
        result = usbwriter._write_payload(os.path.join(root, ""), efi_build_dir, recovery_info, progress,
                                          machine_profile, usbwriter.stick_name(disk), opt_in)
        for extra in extras:
            folder = os.path.join(root, "NullMoth")
            os.makedirs(folder, exist_ok=True)
            shutil.copyfile(extra, os.path.join(folder, os.path.basename(extra)))
            print(f"OK copied {os.path.basename(extra)} to the stick", flush=True)
        if full_pkg:
            _unmount_path(root)
            mounted.remove(root)
            second_root = _mount(second_device, os.path.join(work, "second"))
            mounted.append(second_root)
            print("STEP copying the full macOS installer to the second partition", flush=True)
            try:
                fullinstaller.place(os.path.join(second_root, ""), full_pkg, {"title": "macOS", "version": ""},
                                    progress=lambda done, total: print(
                                        f"PROGRESS {int(done * 100 / total) if total else 0} copying the full macOS "
                                        f"installer to the stick", flush=True))
            except (fullinstaller.FullInstallerError, OSError) as error:
                raise UsbError(f"1401-FULL-INSTALLER: {error}. The first partition is a working online installer at "
                               f"{first_device}; only the full installer is missing.") from None
            print(f"OK the full macOS installer is on the stick ({fullinstaller.LABEL})", flush=True)
        result["root"] = first_device
        print("STEP flushing the stick to flash; a slow USB stick can take a few minutes", flush=True)
        return result
    finally:
        for path in reversed(mounted):
            _unmount_path(path)
        shutil.rmtree(work, ignore_errors=True)


def _owner_of(path):
    try:
        info = os.stat(path)
        return info.st_uid, info.st_gid
    except OSError:
        return None


def _give_back(path, reference):
    """The writer runs as root; a driver copied into the user's build folder should stay the user's."""
    owner = _owner_of(reference)
    if owner and os.geteuid() == 0:
        try:
            os.chown(path, owner[0], owner[1])
        except OSError:
            pass


def _stage_driver(efi, driver):
    from . import usbwriter  # noqa: PLC0415
    if not driver or not usbwriter.needs_nullmoth(efi):
        return
    package = usbwriter._pinned_package(driver)
    cache = os.path.join(efi, ".cache")
    os.makedirs(cache, exist_ok=True)
    target = os.path.join(cache, os.path.basename(package))
    shutil.copyfile(package, target)
    _give_back(target, efi)


def _recovery(efi, darwin, recovery_dir):
    from . import apple, netsupport  # noqa: PLC0415
    if netsupport.needs_local_image(efi):
        print("NOTE " + netsupport.OFFLINE_INSTALLER_MESSAGE, flush=True)
    info = apple.local_image(recovery_dir) if recovery_dir else None
    if info:
        print(f"OK using {info['name']} from {recovery_dir} (checked against Apple's signed chunklist while copying)",
              flush=True)
        return info
    print("STEP asking Apple for the macOS recovery image", flush=True)
    try:
        info = apple.image_info(darwin)
    except apple.AppleError as error:
        if "403" in str(error):
            raise UsbError("Apple's recovery server refused this network (HTTP 403). Connect through a VPN or another "
                           f"network and try again, or put BaseSystem.dmg and BaseSystem.chunklist into {recovery_dir} "
                           "and try again.") from None
        raise
    print(f"OK {info['name']} ({info['product']})", flush=True)
    print("STEP checking that Apple will serve the download (nothing is erased yet)", flush=True)
    try:
        ready = apple.preflight(info)
    except apple.AppleError as error:
        raise UsbError(f"1401-APPLE-REFUSED: {error}. Your USB stick was not touched.") from None
    print(f"OK Apple is serving {info['name']} ({ready['bytes'] / GiB:.2f} GB in {ready['chunks']} parts, "
          f"signed chunklist verified)", flush=True)
    return info


def cli_write(argv):
    """write <device> <EFI build> <darwin major> [--profile Report.json] [--driver tar.gz] [--extra file]...
    [--recovery-dir dir] [--full-installer InstallAssistant.pkg] [--allow-large] [--erase-os-partitions]
    [--stick-id id] [--stick-size bytes] [--stick-name name] [--arm-apps]
    """
    from . import legacy, machine_handoff, usbwriter  # noqa: PLC0415
    if len(argv) < 3:
        raise UsbError("write needs a device, an EFI build directory and the Darwin major version")
    device, efi, darwin = argv[0], argv[1], int(argv[2])
    older = legacy.read_marker(efi)
    if older and older != darwin:
        print(f"STOP this EFI was built for {legacy.NAME[older]}; build again for the macOS you want to write, or write "
              f"{legacy.NAME[older]}. Nothing was erased.", flush=True)
        return 2

    def opt(name):
        return [argv[i + 1] for i, value in enumerate(argv) if value == name and i + 1 < len(argv)]

    disks = list_disks()
    disk = next((d for d in disks if d["Path"] == device), None)
    ident = ((opt("--stick-id") or [""])[0], (opt("--stick-size") or [""])[0], (opt("--stick-name") or [""])[0])
    if any(ident):
        size = int(ident[1]) if ident[1].isdigit() else 0
        found = find_same(disks, ident[0], size, ident[2], device)
        if found is not None:
            if found["Path"] != device:
                print(f"OK the stick is {found['Path']} now (it was {device} when it was picked)", flush=True)
            disk = found
    if not disks:
        print("STOP 1401-DISK-LIST-EMPTY: lsblk listed no disks. Nothing was erased.", flush=True)
        return 1
    if disk is None:
        print(f"STOP 1401-DISK-RENUMBERED: {device} is not attached any more. Nothing was erased. "
              "Press Refresh, pick the stick again and write.", flush=True)
        return 1
    ok, why = eligible(disk, "--allow-large" in argv)
    if not ok:
        print("STOP " + "; ".join(why), flush=True)
        return 1
    profiles = opt("--profile")
    if len(profiles) > 1:
        raise UsbError("Select one current scan before writing the installer.")
    handoff = machine_handoff.verified(efi, profiles[0] if profiles else None)
    prepare_driver(efi)
    _stage_driver(efi, (opt("--driver") or [""])[0])
    recovery_dir = (opt("--recovery-dir") or [RECOVERY_DIR])[0]
    info = _recovery(efi, darwin, recovery_dir)
    full_pkg = (opt("--full-installer") or [""])[0] or None

    last = [-1]

    def progress(done, total, *_):
        percent = int(done * 100 / total) if total else 0
        if percent != last[0]:
            last[0] = percent
            print(f"PROGRESS {percent} downloading macOS recovery from Apple", flush=True)

    print(f"STEP erasing and writing {disk['Path']} ({usbwriter.stick_name(disk)})", flush=True)
    opt_in = machine_handoff.opt_in(arm_apps="--arm-apps" in argv)
    result = write(disk, efi, info, allow_large="--allow-large" in argv, progress=progress, machine_profile=handoff,
                   erase_os="--erase-os-partitions" in argv, opt_in=opt_in, full_pkg=full_pkg, extras=opt("--extra"))
    print("OK verified build profile written to the stick (live identity remains unverified)", flush=True)
    if opt_in:
        print("OK ARM apps requested: after macOS starts, the 1401 Mac app offers to finish setting them up, if this "
              "Mac can run them", flush=True)
    print(f"OK the stick is ready at {result['root']}" + (" (NVIDIA driver included)" if result.get("nullmoth") else ""),
          flush=True)
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("list", "disks"):
        try:
            print(json.dumps(list_disks(), indent=2))
            return 0
        except UsbError as error:
            print(f"STOP {error}", file=sys.stderr)
            return 1
    if argv[0] == "write":
        try:
            return cli_write(argv[1:])
        except (UsbError, OSError, RuntimeError) as error:
            print(f"STOP {type(error).__name__}: {error}", flush=True)
            return 1
    if argv[0] == "prepare-driver":
        try:
            prepare_driver(argv[1] if len(argv) > 1 else "")
            return 0
        except (UsbError, OSError, RuntimeError) as error:
            print(f"STOP {type(error).__name__}: {error}", flush=True)
            return 1
    print("usage: python3 -m p1401.linuxusb [list | write <device> <EFI build> <darwin major> [options]]",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
