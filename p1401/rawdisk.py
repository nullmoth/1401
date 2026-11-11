"""Erases a USB stick the way Rufus does, without diskpart: lock + dismount every volume on the disk, zero the partition
tables at both ends, write a fresh MBR layout with one bootable FAT32 partition through the disk driver, refresh.
diskpart clean can fail on a stick that Windows still has mounted ("Access is denied", "volume not valid", "device is not ready",
hung retries) because Windows still held the stick's mounted volume. Locking the volumes first is what makes this reliable."""
import ctypes
import os
import struct
import time
from ctypes import wintypes

GENERIC_READ = 0x80000000
GENERIC_RW = 0x80000000 | 0x40000000
SHARE_RW = 0x1 | 0x2
OPEN_EXISTING = 3
FSCTL_LOCK_VOLUME = 0x90018
FSCTL_DISMOUNT_VOLUME = 0x90020
IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS = 0x560000
IOCTL_DISK_DELETE_DRIVE_LAYOUT = 0x7C100
IOCTL_DISK_SET_DISK_ATTRIBUTES = 0x7C0F4
DISK_ATTRIBUTE_OFFLINE = 0x1
IOCTL_DISK_CREATE_DISK = 0x7C058
IOCTL_DISK_SET_DRIVE_LAYOUT_EX = 0x7C054
IOCTL_DISK_UPDATE_PROPERTIES = 0x70140
IOCTL_STORAGE_QUERY_PROPERTY = 0x2D1400
IOCTL_DISK_GET_DRIVE_GEOMETRY_EX = 0x000700A0
STORAGE_DEVICE_PROPERTY = 0
MiB = 1 << 20
FAT32_LBA = 0x0C


class DiskError(RuntimeError):
    pass


def _k32():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateFileW.restype = wintypes.HANDLE
    k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                              wintypes.DWORD, wintypes.HANDLE]
    k.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
                                  wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    k.FindFirstVolumeW.restype = wintypes.HANDLE
    k.FindFirstVolumeW.argtypes = [wintypes.LPWSTR, wintypes.DWORD]
    # without argtypes ctypes passes a 64-bit HANDLE as a C int -> "OverflowError: int too long to convert"
    k.FindNextVolumeW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD]
    k.FindVolumeClose.argtypes = [wintypes.HANDLE]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    k.SetFilePointerEx.argtypes = [wintypes.HANDLE, ctypes.c_longlong, ctypes.c_void_p, wintypes.DWORD]
    k.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    return k


def _open(k, path, access=GENERIC_RW):
    h = k.CreateFileW(path, access, SHARE_RW, None, OPEN_EXISTING, 0, None)
    if h in (None, wintypes.HANDLE(-1).value):
        raise DiskError(f"cannot open {path} (Windows error {ctypes.get_last_error()})")
    return h


def _ioctl(k, h, code, inbuf=b"", outsize=0):
    out = ctypes.create_string_buffer(outsize) if outsize else None
    ib = ctypes.create_string_buffer(inbuf, len(inbuf)) if inbuf else None
    n = wintypes.DWORD(0)
    ok = k.DeviceIoControl(h, code, ib, len(inbuf), out, outsize, ctypes.byref(n), None)
    return bool(ok), (out.raw[:n.value] if out else b""), ctypes.get_last_error()


def _volumes_on(k, disk):
    """Volume GUID paths whose extents sit on PhysicalDrive<disk> (lettered or not)."""
    found, buf = [], ctypes.create_unicode_buffer(260)
    hf = k.FindFirstVolumeW(buf, 260)
    if hf in (None, wintypes.HANDLE(-1).value):
        return found
    try:
        while True:
            name = buf.value.rstrip("\\")
            h = k.CreateFileW(name, 0, SHARE_RW, None, OPEN_EXISTING, 0, None)
            if h not in (None, wintypes.HANDLE(-1).value):
                ok, out, _ = _ioctl(k, h, IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS, outsize=1024)
                k.CloseHandle(h)
                if ok and len(out) >= 32:
                    count = struct.unpack_from("<I", out, 0)[0]
                    if any(struct.unpack_from("<I", out, 8 + 24 * i)[0] == disk for i in range(count)):
                        found.append(name)
            if not k.FindNextVolumeW(hf, buf, 260):
                break
    finally:
        k.FindVolumeClose(hf)
    return found



def _lock_volume(k, h, tries=40, after_dismount=20, sleep=time.sleep):
    """Exclusive lock on an open volume handle. Rufus retries the lock first (Explorer and indexers let go within
    seconds). If something still holds the volume - a write failure seen on 11 machines in one day with an Explorer
    window, an antivirus scan or a previous step's open file on the stick - Rufus forces a dismount, which invalidates
    every other open handle on the volume, and locks again. The stick is about to be erased, so nothing those handles
    could still write is kept anyway."""
    for _ in range(tries):
        if _ioctl(k, h, FSCTL_LOCK_VOLUME)[0]:
            return True
        sleep(0.25)
    _ioctl(k, h, FSCTL_DISMOUNT_VOLUME)
    for _ in range(after_dismount):
        if _ioctl(k, h, FSCTL_LOCK_VOLUME)[0]:
            return True
        sleep(0.25)
    return False

def _disk_offline(k, d, offline):
    """SET_DISK_ATTRIBUTES (40 bytes: Version, Persist, Attributes, AttributesMask): not persisted across reboots."""
    return _ioctl(k, d, IOCTL_DISK_SET_DISK_ATTRIBUTES,
                  struct.pack("<I?3xQQ16x", 40, False, DISK_ATTRIBUTE_OFFLINE if offline else 0, DISK_ATTRIBUTE_OFFLINE))[0]


WRITE_HELP = {  # what the user can do, per Windows error from the raw write
    433: "The stick disconnected while it was being written: use a USB port on the back of the PC (not a hub or front "
         "panel) and try again.",
    0: "This stick refuses direct writes even with nothing else using it. Use another USB stick (16 GB or more, a "
       "known brand) - some sticks report a size they do not have or are read-only by design.",
}


def failure_line(err, off, length, disk_size, sector=None, offline=None, via_volume=None):
    """One line that says where a raw write failed (Windows error, byte offset as a share of the disk, size, and what the
    caller knows), for the stop message and the write log. SD cards in USB readers (SDXC, 1401 #18, error 5) differ from
    sticks in exactly these facts: a reader that reports 512-byte sectors on a card with 4096-byte allocation units, a
    write protect switch, or a write at the very end of the disk. 'sector' and 'offline' are None when not known."""
    where = "start" if off == 0 else "end" if disk_size and off + length >= disk_size - (2 << 20) else "middle"
    pct = f"{100.0 * off / disk_size:.2f}%" if disk_size else "?"
    aligned = (off % sector == 0 and length % sector == 0) if sector else None
    return (f"raw write failed: Windows error {err}, {length} bytes at offset {off} ({where} of the disk, {pct}), disk {disk_size} bytes, "
            f"sector {sector if sector else 'unknown'}, aligned {aligned if aligned is not None else 'unknown'}, "
            f"offline {offline if offline is not None else 'unknown'}, through volume {via_volume if via_volume is not None else 'unknown'}")


def _sector_size(k, h):
    """Bytes per sector from IOCTL_DISK_GET_DRIVE_GEOMETRY_EX, or None."""
    ok, out, _ = _ioctl(k, h, 0x000700A0, b"", 64)   # IOCTL_DISK_GET_DRIVE_GEOMETRY_EX: DISK_GEOMETRY.BytesPerSector at byte 20
    return struct.unpack_from("<I", out, 20)[0] if ok and len(out) >= 24 else None


def _ascii_field(out, offset):
    """A NUL-terminated ASCII field inside a STORAGE_DEVICE_DESCRIPTOR, or ""."""
    if not offset or offset >= len(out):
        return ""
    end = out.find(b"\0", offset)
    if end < 0:
        end = len(out)
    return out[offset:end].decode("ascii", "replace").strip()


def _device_identity(k, h):
    """What the open disk handle says it is: serial number, vendor+product and byte size. Read-only.

    This is deliberately read from the handle that is about to be erased, not from a list Windows returned earlier: a
    stick that dropped off and came back under another disk number must not let the number's new owner be erased."""
    serial = model = ""
    ok, out, _ = _ioctl(k, h, IOCTL_STORAGE_QUERY_PROPERTY,
                        struct.pack("<II", STORAGE_DEVICE_PROPERTY, 0), 1024)
    if ok and len(out) >= 36:
        serial = _ascii_field(out, struct.unpack_from("<I", out, 24)[0])
        vendor = _ascii_field(out, struct.unpack_from("<I", out, 12)[0])
        product = _ascii_field(out, struct.unpack_from("<I", out, 16)[0])
        model = " ".join(x for x in (vendor, product) if x).strip()
    ok, geo, _ = _ioctl(k, h, IOCTL_DISK_GET_DRIVE_GEOMETRY_EX, b"", 64)
    # DISK_GEOMETRY_EX = DISK_GEOMETRY (24 bytes) followed by DiskSize (8 bytes)
    size = struct.unpack_from("<Q", geo, 24)[0] if ok and len(geo) >= 32 else 0
    return {"SerialNumber": serial, "Model": model, "Size": size}


def _norm(value):
    return " ".join((value or "").split()).casefold()


def _identity_matches(expected, actual):
    """(ok, reason): is the open disk the USB stick the user picked?

    The serial number is the strongest identity. Some USB bridges report a new (or no) serial on every read, which the
    writer already had to live with, so the model and the exact byte size are accepted as the fallback. A different size
    is always a refusal, whatever else matches."""
    want_size, have_size = int(expected.get("Size") or 0), int(actual.get("Size") or 0)
    if want_size and have_size and want_size != have_size:
        return False, f"its size is {have_size} bytes and the picked stick is {want_size}"
    want_serial, have_serial = _norm(expected.get("SerialNumber")), _norm(actual.get("SerialNumber"))
    if want_serial and have_serial and want_serial == have_serial:
        return True, "the serial number matches"
    want_model, have_model = _norm(expected.get("FriendlyName")), _norm(actual.get("Model"))
    if want_model and have_model and (want_model == have_model or want_model in have_model or have_model in want_model):
        return True, "the model and size match"
    if want_serial and not have_serial:
        return False, "its serial number could not be read"
    return False, "its serial number and model are not the picked stick's"


def read_identity(disk):
    """Read-only: the serial number, model and byte size Windows reports for PhysicalDrive<disk>."""
    k = _k32()
    h = _open(k, rf"\\.\PhysicalDrive{int(disk)}", access=GENERIC_READ)
    try:
        return _device_identity(k, h)
    finally:
        k.CloseHandle(h)



def _write_at(k, h, off, data):
    """Writes data at byte offset off. 0 = written, else the Windows error (the seek is checked: a failed seek used to
    send the write to the wrong place)."""
    if not k.SetFilePointerEx(h, off, None, 0):
        return ctypes.get_last_error() or -1
    n = wintypes.DWORD(0)
    buf = ctypes.create_string_buffer(data, len(data))
    if not k.WriteFile(h, buf, len(data), ctypes.byref(n), None) or n.value != len(data):
        return ctypes.get_last_error() or -1
    return 0


def wipe_mbr_fat32(disk, size, part_size, say=print, expected=None):
    """disk = PhysicalDrive number, size = disk bytes. Leaves one empty MBR partition (type 0x0C, active) of part_size bytes.

    expected: the disk dict the user picked (SerialNumber/Size/FriendlyName). When given, the open handle itself is
    queried before the first destructive call and the erase is refused unless it is that stick."""
    k = _k32()
    held = []
    offline = None
    try:
        for v in _volumes_on(k, disk):
            try:
                h = _open(k, v)
            except DiskError as e:
                # A 2.0.2 write log: "cannot open \\?\Volume{...} (Windows error 2)". The volume was listed and was gone a
                # moment later (Windows remounting the stick). A volume that no longer exists holds nothing to lock.
                if "Windows error 2" not in str(e):
                    raise
                say(f"(a volume on the stick went away before it was locked: {v}; nothing to lock)")
                continue
            held.append(h)
            if not _lock_volume(k, h):
                # Still held after the lock retries and a forced dismount (18 machines on 1.1-1.2: Explorer, antivirus,
                # a sync client). Taking the whole disk offline closes every volume handle Windows has on it, and raw
                # writes to an offline disk are allowed (diskpart clean does the same). Online again in finally.
                offline = _open(k, rf"\\.\PhysicalDrive{int(disk)}")
                if not _disk_offline(k, offline, True):
                    raise DiskError(f"another program is using the stick ({v}); close Explorer windows on it and try again")
                say("OK another program held the stick; took it offline to free it")
                break
            _ioctl(k, h, FSCTL_DISMOUNT_VOLUME)
        say(f"OK locked {len(held)} volume(s) on the stick")
        d = offline or _open(k, rf"\\.\PhysicalDrive{int(disk)}")
        if d is not offline:
            held.append(d)
        if expected is not None:
            # The list the user picked from was read in a different process, before the volumes were locked. Windows can
            # renumber a USB disk in that window, and the number then belongs to another disk. Ask the handle that is
            # about to be destroyed what it is, and refuse before the partition table is touched.
            actual = _device_identity(k, d)
            ok, why = _identity_matches(expected, actual)
            if not ok:
                raise DiskError(f"refusing: PhysicalDrive{int(disk)} is not the USB stick that was picked ({why}). "
                                f"Nothing was erased. Unplug the stick, plug it in again and press Write again.")
            say(f"OK PhysicalDrive{int(disk)} is the picked stick ({why})")
        # Rufus order: drop the partition table first, so no volume covers the sectors written next (Windows refuses
        # raw writes inside a mounted volume: error 5, and error 1 on some USB bridges - 34 uploads through 1.2.0).
        _ioctl(k, d, IOCTL_DISK_DELETE_DRIVE_LAYOUT)
        _ioctl(k, d, IOCTL_DISK_UPDATE_PROPERTIES)
        zero = bytes(MiB)
        for off in (0, (size // MiB - 1) * MiB):  # both ends: MBR/GPT header and the GPT backup
            err = _write_at(k, d, off, zero)
            if err and offline is None:
                # still refused: offline the disk (closes every handle Windows has on it) and write once more
                offline = _open(k, rf"\\.\PhysicalDrive{int(disk)}")
                if _disk_offline(k, offline, True):
                    say("OK Windows refused the write; took the stick offline and wrote again")
                    d = offline
                    err = _write_at(k, d, off, zero)
            if err:
                line = failure_line(err, off, len(zero), size, _sector_size(k, d), offline is not None, len(held))
                say(line)
                raise DiskError(f"could not write to the stick (Windows error {err}). " + WRITE_HELP.get(err, WRITE_HELP[0]) + " [" + line + "]")
        sig = struct.unpack("<I", os.urandom(4))[0] or 1
        ok, _, err = _ioctl(k, d, IOCTL_DISK_CREATE_DISK, struct.pack("<II16x", 0, sig))
        if not ok:
            raise DiskError(f"could not create a new partition table (Windows error {err})")
        start = MiB
        length = min(part_size, (size // MiB - 2) * MiB)
        layout = struct.pack("<IIII32x", 0, 4, sig, 0)
        entry1 = struct.pack("<I4xqqIBB2xBBBxI16s88x", 0, start, length, 1, 1, 0, FAT32_LBA, 1, 1, start // 512, bytes(16))
        empty = struct.pack("<I4xqqIBB2x112x", 0, 0, 0, 0, 1, 0)
        ok, _, err = _ioctl(k, d, IOCTL_DISK_SET_DRIVE_LAYOUT_EX, layout + entry1 + empty * 3)
        if not ok:
            raise DiskError(f"could not write the partition (Windows error {err})")
        _ioctl(k, d, IOCTL_DISK_UPDATE_PROPERTIES)
        say("OK erased the stick and made one FAT32 partition")
    finally:
        if offline:
            _disk_offline(k, offline, False)
            k.CloseHandle(offline)
        for h in reversed(held):
            k.CloseHandle(h)
