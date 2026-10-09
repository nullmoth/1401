"""Erases a USB stick the way Rufus does, without diskpart: lock + dismount every volume on the disk, zero the partition
tables at both ends, write a fresh MBR layout with one bootable FAT32 partition through the disk driver, refresh.
diskpart clean can fail on a stick that Windows still has mounted ("Access is denied", "volume not valid", "device is not ready",
hung retries) because Windows still held the stick's mounted volume. Locking the volumes first is what makes this reliable."""
import ctypes
import os
import struct
import time
from ctypes import wintypes

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


def _open(k, path):
    h = k.CreateFileW(path, GENERIC_RW, SHARE_RW, None, OPEN_EXISTING, 0, None)
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


def wipe_mbr_fat32(disk, size, part_size, say=print):
    """disk = PhysicalDrive number, size = disk bytes. Leaves one empty MBR partition (type 0x0C, active) of part_size bytes."""
    k = _k32()
    held = []
    offline = None
    try:
        for v in _volumes_on(k, disk):
            h = _open(k, v)
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
                raise DiskError(f"could not write to the stick (Windows error {err}). " + WRITE_HELP.get(err, WRITE_HELP[0]))
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
