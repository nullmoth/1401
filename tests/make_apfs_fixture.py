"""Builds the positive APFS fixture: an Apple-made APFS container carrying Apple's real EFI jumpstart.

    python3 tests/make_apfs_fixture.py <base.cdr> <jsdr.bin> <driver.efi> <out.cdr>

All inputs come from Apple's tools. base.cdr is made with hdiutil + bless on an Intel Mac (Sequoia 15.7.3): a
container with a blessed CoreServices/boot.efi but nx_efi_jumpstart = 0 (bless stops at its Preboot step before
embedding). jsdr.bin and driver.efi are read-only extracts from an installed Intel Mac's boot container (disk0s2).

This script only moves them into place: the driver goes into the container's all-zero tail, the JSDR's one extent
is pointed at it, block 0's nx_efi_jumpstart points at the JSDR, and both Fletcher-64 checksums are recomputed.
Offsets are the ones seen on a real container (magic @32, type @24, len @40, extent count @44, extents @176).

The output contains Apple's code, so it goes to ~/.cache/1401/fixtures, never into the repo. Refuses if the tail
isn't all zero.
"""
import os
import struct
import sys


def fletcher64(b):
    m = 0xFFFFFFFF
    s1 = s2 = 0
    for (w,) in struct.iter_unpack("<I", b[8:]):
        s1 = (s1 + w) % m
        s2 = (s2 + s1) % m
    c1 = m - ((s1 + s2) % m)
    c2 = m - ((s1 + c1) % m)
    return (c2 << 32) | c1


def seal(block):
    block[0:8] = struct.pack("<Q", fletcher64(bytes(block)))


def main(base, jsdr, driver, out):
    img = bytearray(open(base, "rb").read())
    js = bytearray(open(jsdr, "rb").read())
    drv = open(driver, "rb").read()
    assert img[512:520] == b"EFI PART", "base has no GPT"
    ent = struct.unpack_from("<Q", img, 512 + 72)[0] * 512
    first, last = struct.unpack_from("<QQ", img, ent + 32)
    p0 = first * 512
    assert img[p0 + 32:p0 + 36] == b"NXSB", "first partition is not an APFS container"
    bs, nblocks = struct.unpack_from("<IQ", img, p0 + 36)
    assert struct.unpack_from("<Q", img, p0 + 1272)[0] == 0, "base already has a jumpstart"
    assert js[32:36] == b"JSDR" and struct.unpack_from("<I", js, 24)[0] & 0xFFFF == 0x14 and len(js) == bs
    assert struct.unpack_from("<I", js, 40)[0] == len(drv), "driver length does not match its JSDR"
    k = -(-len(drv) // bs)
    nblocks = min(nblocks, ((last + 1) * 512 - p0) // bs)
    js_paddr, drv_paddr = nblocks - k - 1, nblocks - k
    tail = img[p0 + js_paddr * bs:p0 + nblocks * bs]
    if any(tail):
        raise SystemExit(f"refusing: container tail blocks {js_paddr}..{nblocks - 1} are not all zero")
    img[p0 + drv_paddr * bs:p0 + drv_paddr * bs + len(drv)] = drv
    struct.pack_into("<IQQ", js, 44, 1, 0, 0)  # count = 1 (nej_reserved[0] zeroed with it)
    js[176:bs] = bytes(bs - 176)
    struct.pack_into("<QQ", js, 176, drv_paddr, k)
    seal(js)
    img[p0 + js_paddr * bs:p0 + (js_paddr + 1) * bs] = js
    sb = img[p0:p0 + bs]
    struct.pack_into("<Q", sb, 1272, js_paddr)
    seal(sb)
    img[p0:p0 + bs] = sb
    with open(out + ".tmp", "wb") as fh:
        fh.write(img)
    os.replace(out + ".tmp", out)
    print(f"fixture: JSDR at paddr {js_paddr}, driver {len(drv)} B in {k} blocks at {drv_paddr} -> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:5])
