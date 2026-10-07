//! APFS jumpstart: how a PC's firmware learns to read APFS without 1401 shipping Apple's driver.
//!
//! Every APFS container an Intel Mac blesses carries Apple's own EFI driver (`apfs.efi`) inside it: the container
//! superblock's `nx_efi_jumpstart` points at an `nx_efi_jumpstart_t` object whose extents hold the driver. Mac
//! firmware mounts APFS by loading that driver from the disk itself. 1401 does the same, so it ships no Apple code.
//!
//! A container formatted on Apple silicon (macOS 27 `hdiutil -fs APFS`) has `nx_efi_jumpstart = 0`, and so does a
//! plain `hdiutil` image on Intel Sequoia until a folder on it is blessed. On a PC the container is formatted by x86
//! recovery and blessed by the installer, so it has one. A container without one is reported, not guessed at.
//!
//! Nothing is written. BlockIO is opened with GET_PROTOCOL; an exclusive open would disconnect the partition's drivers.
//!
//! Layout: Apple File System Reference, `nx_superblock_t` / `nx_efi_jumpstart_t`. Checksum: APFS Fletcher-64,
//! checked against superblocks written by Apple's tools (tests/loader_qemu.py makes one with hdiutil each run).
//! TODO: verify Apple's signature on the driver (OpenCore does), and load it with Secure Boot on.

use alloc::vec;
use alloc::vec::Vec;
use uefi::boot::{self, LoadImageSource, OpenProtocolAttributes, OpenProtocolParams, SearchType};
use uefi::proto::device_path::DevicePath;
use uefi::proto::media::block::BlockIO;
use uefi::{Handle, Identify, println};

const NX_MAGIC: &[u8] = b"NXSB";
const JS_MAGIC: &[u8] = b"JSDR";
const NX_BLOCK_SIZE: usize = 36; // u32
const NX_EFI_JUMPSTART: usize = 1272; // paddr_t, after nx_counters[32], nx_blocked_out_prange, evict oid, nx_flags
const NEJ_EFI_FILE_LEN: usize = 40; // u32
const NEJ_NUM_EXTENTS: usize = 44; // u32
const NEJ_REC_EXTENTS: usize = 176; // prange_t[] {paddr u64, block_count u64}, after nej_reserved[16]
// Not 0x13 (that's OMAP_SNAPSHOT). A real boot container's jumpstart has o_type 0x40000014 (OBJ_PHYSICAL | EFI_JUMPSTART).
const OBJECT_TYPE_EFI_JUMPSTART: u32 = 0x14; // low 16 bits of o_type
const MAX_DRIVER: usize = 16 << 20; // Sequoia's apfs.efi is 713,784 bytes; 16 MiB only bounds a corrupt length

enum Container {
    NotApfs,
    NoJumpstart,
    Refused(&'static str),
    Driver { bytes: Vec<u8>, extents: usize },
}

fn fletcher64(block: &[u8]) -> u64 {
    const M: u64 = 0xFFFF_FFFF;
    let (mut s1, mut s2) = (0u64, 0u64);
    for w in block[8..].chunks_exact(4) {
        s1 = (s1 + u32::from_le_bytes([w[0], w[1], w[2], w[3]]) as u64) % M;
        s2 = (s2 + s1) % M;
    }
    let c1 = M - ((s1 + s2) % M);
    let c2 = M - ((s1 + c1) % M);
    (c2 << 32) | c1
}

fn u32_at(b: &[u8], o: usize) -> u32 {
    u32::from_le_bytes([b[o], b[o + 1], b[o + 2], b[o + 3]])
}

fn u64_at(b: &[u8], o: usize) -> u64 {
    (u32_at(b, o) as u64) | ((u32_at(b, o + 4) as u64) << 32)
}

/// An APFS object is only believed if its stored checksum matches its bytes.
fn object_ok(b: &[u8]) -> bool {
    u64_at(b, 0) == fletcher64(b)
}

struct Disk<'a> {
    bio: &'a mut BlockIO,
    media_id: u32,
    lbs: u64,
    align: usize,
    bytes: u64,
}

impl Disk<'_> {
    fn read(&mut self, off: u64, len: usize) -> Result<Vec<u8>, &'static str> {
        if off % self.lbs != 0 || len as u64 % self.lbs != 0 {
            return Err("read not aligned to the device's block size");
        }
        if off.checked_add(len as u64).is_none_or(|end| end > self.bytes) {
            return Err("extent points past the end of the partition");
        }
        // Over-allocate and slide to the device's IoAlign; the firmware refuses a misaligned buffer.
        let a = self.align.max(1);
        let mut buf = vec![0u8; len + a];
        let pad = (a - (buf.as_ptr() as usize % a)) % a;
        self.bio
            .read_blocks(self.media_id, off / self.lbs, &mut buf[pad..pad + len])
            .map_err(|_| "block read failed")?;
        buf.truncate(pad + len);
        buf.drain(..pad);
        Ok(buf)
    }
}

fn container(h: Handle) -> Container {
    // SAFETY: GET_PROTOCOL takes no ownership; the handle outlives this call and we never free the interface.
    let Ok(mut bio) = (unsafe {
        boot::open_protocol::<BlockIO>(
            OpenProtocolParams { handle: h, agent: boot::image_handle(), controller: None },
            OpenProtocolAttributes::GetProtocol,
        )
    }) else {
        return Container::NotApfs;
    };
    let m = bio.media();
    let (lbs, media_id, align, present) = (m.block_size() as u64, m.media_id(), m.io_align() as usize, m.is_media_present());
    let bytes = (m.last_block() + 1) * lbs;
    if !present || lbs == 0 || 4096 % lbs != 0 || bytes < 1 << 20 {
        return Container::NotApfs;
    }
    let mut d = Disk { bio: &mut bio, media_id, lbs, align, bytes };
    let Ok(sb) = d.read(0, 4096) else { return Container::NotApfs };
    if &sb[32..36] != NX_MAGIC {
        return Container::NotApfs;
    }
    let bs = u32_at(&sb, NX_BLOCK_SIZE) as usize;
    if !(4096..=65536).contains(&bs) || !bs.is_power_of_two() {
        return Container::Refused("container block size out of range");
    }
    let sb = if bs == 4096 { sb } else {
        match d.read(0, bs) { Ok(b) => b, Err(e) => return Container::Refused(e) }
    };
    if !object_ok(&sb) {
        return Container::Refused("container superblock checksum mismatch");
    }
    let js = u64_at(&sb, NX_EFI_JUMPSTART);
    if js == 0 {
        return Container::NoJumpstart;
    }
    let Some(js_off) = js.checked_mul(bs as u64) else { return Container::Refused("jumpstart address overflows") };
    let jb = match d.read(js_off, bs) { Ok(b) => b, Err(e) => return Container::Refused(e) };
    if !object_ok(&jb) {
        return Container::Refused("jumpstart checksum mismatch");
    }
    if &jb[32..36] != JS_MAGIC || u32_at(&jb, 24) & 0xFFFF != OBJECT_TYPE_EFI_JUMPSTART {
        return Container::Refused("jumpstart object is not JSDR");
    }
    let flen = u32_at(&jb, NEJ_EFI_FILE_LEN) as usize;
    let n = u32_at(&jb, NEJ_NUM_EXTENTS) as usize;
    if flen == 0 || flen > MAX_DRIVER {
        return Container::Refused("driver length out of range");
    }
    if n == 0 || NEJ_REC_EXTENTS + 16 * n > bs {
        return Container::Refused("extent count out of range");
    }
    let mut drv = Vec::with_capacity(flen);
    for k in 0..n {
        let (p, c) = (u64_at(&jb, NEJ_REC_EXTENTS + 16 * k), u64_at(&jb, NEJ_REC_EXTENTS + 16 * k + 8));
        let (Some(off), Some(len)) = (p.checked_mul(bs as u64), c.checked_mul(bs as u64)) else {
            return Container::Refused("extent overflows");
        };
        if drv.len() + len as usize > MAX_DRIVER + bs {
            return Container::Refused("extents larger than the driver");
        }
        match d.read(off, len as usize) { Ok(b) => drv.extend_from_slice(&b), Err(e) => return Container::Refused(e) }
    }
    if drv.len() < flen {
        return Container::Refused("extents shorter than the driver");
    }
    drv.truncate(flen);
    // An x86-64 PE, or nothing: the firmware would load anything we hand it.
    let pe = if drv.len() >= 0x40 && &drv[..2] == b"MZ" { u32_at(&drv, 0x3c) as usize } else { usize::MAX };
    if pe.checked_add(6).is_none_or(|e| e > drv.len()) || &drv[pe..pe + 4] != b"PE\0\0" || drv[pe + 4..pe + 6] != [0x64, 0x86] {
        return Container::Refused("embedded driver is not an x86-64 PE image");
    }
    Container::Driver { bytes: drv, extents: n }
}

fn start(h: Handle, drv: &[u8]) -> uefi::Result {
    // Pass the container's device path as the driver's file path, the same way Mac firmware does.
    // SAFETY: as above - GET_PROTOCOL, read-only use.
    let dp = unsafe {
        boot::open_protocol::<DevicePath>(
            OpenProtocolParams { handle: h, agent: boot::image_handle(), controller: None },
            OpenProtocolAttributes::GetProtocol,
        )
    }
    .ok();
    let img = boot::load_image(
        boot::image_handle(),
        LoadImageSource::FromBuffer { buffer: drv, file_path: dp.as_deref() },
    )?;
    boot::start_image(img)
}

/// Loads every APFS container's own driver, then reconnects so its volumes appear as filesystems.
/// Returns how many drivers started.
pub fn jumpstart() -> usize {
    let Ok(handles) = boot::locate_handle_buffer(SearchType::ByProtocol(&BlockIO::GUID)) else { return 0 };
    let mut started = 0;
    for (i, &h) in handles.iter().enumerate() {
        match container(h) {
            Container::NotApfs => {}
            Container::NoJumpstart => println!("1401: blk{}: APFS container with no EFI jumpstart (nx_efi_jumpstart = 0)", i),
            Container::Refused(why) => println!("1401: blk{}: APFS container refused: {}", i, why),
            Container::Driver { bytes, extents } => {
                println!("1401: blk{}: APFS jumpstart: {} bytes in {} extent(s)", i, bytes.len(), extents);
                match start(h, &bytes) {
                    Ok(()) => {
                        println!("1401: blk{}: apfs.efi started", i);
                        started += 1;
                    }
                    Err(e) => println!("1401: blk{}: apfs.efi failed to start: {:?}", i, e.status()),
                }
            }
        }
    }
    if started > 0 {
        // Connect every handle and let the new driver bind to the containers it recognises. NOT_FOUND on the rest
        // just means "no driver for this controller", so the per-handle result is ignored; the rescan afterwards
        // (volumes showing up as filesystems) is what tells us it worked.
        if let Ok(all) = boot::locate_handle_buffer(SearchType::AllHandles) {
            for &h in all.iter() {
                let _ = boot::connect_controller(h, &[], None, true);
            }
        }
    }
    started
}
