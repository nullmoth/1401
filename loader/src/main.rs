//! 1401 loader, the boot side of reverse Boot Camp. On a Mac the firmware itself finds macOS and Windows, and Boot
//! Camp relies on that. A PC's firmware doesn't, so this does it instead. It replaces OpenCore, so there's no
//! config.plist to get wrong: 1401 works out everything it needs from the machine on the Windows side.
//!
//! For now: find every bootable OS on every filesystem the firmware exposes and chain-load one by its real device
//! path. Windows Boot Manager has to be started that way, since it finds its BCD store relative to its own path and
//! can't when it's loaded from a bare buffer.
//!
//! Nothing here writes to disk or NVRAM yet, so the loader can't break an existing Windows install.
#![no_main]
#![no_std]

extern crate alloc;

mod apfs;

use alloc::vec::Vec;
use uefi::boot::{self, LoadImageSource, SearchType};
use uefi::prelude::*;
use uefi::proto::BootPolicy;
use uefi::proto::device_path::DevicePath;
use uefi::proto::device_path::build::{self, DevicePathBuilder};
use uefi::proto::media::file::{File, FileAttribute, FileMode};
use uefi::proto::media::fs::SimpleFileSystem;
use uefi::runtime::ResetType;
use uefi::{CStr16, Identify, cstr16, println};

/// What the picker looks for, in the order it prefers them. The probe is 1401's own test payload (the QEMU suite
/// puts it there); on a real machine it never exists.
const CANDIDATES: &[(&str, &CStr16)] = &[
    ("1401 probe", cstr16!("\\EFI\\1401\\next.efi")),
    ("macOS", cstr16!("\\System\\Library\\CoreServices\\boot.efi")),
    ("Windows", cstr16!("\\EFI\\Microsoft\\Boot\\bootmgfw.efi")),
];

struct Found {
    rank: usize,
    handle: Handle,
    fs_index: usize,
    name: &'static str,
    path: &'static CStr16,
}

fn has_file(handle: Handle, path: &CStr16) -> bool {
    // Scoped: the exclusive open is dropped before anything else touches this device.
    let Ok(mut fs) = boot::open_protocol_exclusive::<SimpleFileSystem>(handle) else { return false };
    let Ok(mut root) = fs.open_volume() else { return false };
    root.open(path, FileMode::Read, FileAttribute::empty()).is_ok()
}

fn scan() -> Vec<Found> {
    let mut found = Vec::new();
    let Ok(handles) = boot::locate_handle_buffer(SearchType::ByProtocol(&SimpleFileSystem::GUID)) else {
        println!("1401: firmware reports no filesystems");
        return found;
    };
    println!("1401: {} filesystem(s)", handles.len());
    for (i, &h) in handles.iter().enumerate() {
        for (rank, &(name, path)) in CANDIDATES.iter().enumerate() {
            if has_file(h, path) {
                println!("1401: fs{}: {} at {}", i, name, path);
                found.push(Found { rank, handle: h, fs_index: i, name, path });
            }
        }
    }
    found
}

fn chainload(f: &Found) -> uefi::Result {
    // The full path = the filesystem's device path + a FilePath node, built into our own buffer.
    let mut buf = Vec::new();
    let full: &DevicePath = {
        let dp = boot::open_protocol_exclusive::<DevicePath>(f.handle)?;
        let mut b = DevicePathBuilder::with_vec(&mut buf);
        for node in dp.node_iter() {
            b = b.push(&node).map_err(|_| Status::BUFFER_TOO_SMALL)?;
        }
        b = b.push(&build::media::FilePath { path_name: f.path }).map_err(|_| Status::BUFFER_TOO_SMALL)?;
        b.finalize().map_err(|_| Status::BUFFER_TOO_SMALL)?
    };
    println!("1401: loading {} from fs{}", f.name, f.fs_index);
    let image = boot::load_image(
        boot::image_handle(),
        LoadImageSource::FromDevicePath { device_path: full, boot_policy: BootPolicy::ExactMatch },
    )?;
    boot::start_image(image)
}

#[entry]
fn main() -> Status {
    uefi::helpers::init().unwrap();
    println!("1401 loader {} - reverse Boot Camp", env!("CARGO_PKG_VERSION"));
    // APFS first: macOS volumes only exist as filesystems once their container's own driver is running.
    let drivers = apfs::jumpstart();
    println!("1401: {} APFS driver(s) started", drivers);
    let found = scan();
    // Pick by CANDIDATES order, not disk order; the firmware numbers filesystems in whatever order it finds them.
    let status = match found.iter().min_by_key(|f| f.rank) {
        None => {
            println!("1401: no bootable OS found");
            Status::NOT_FOUND
        }
        Some(f) => match chainload(f) {
            Ok(()) => {
                println!("1401: {} returned to the loader", f.name);
                Status::SUCCESS
            }
            Err(e) => {
                println!("1401: {} failed to start: {:?}", f.name, e.status());
                e.status()
            }
        },
    };
    println!("1401: done ({:?}); powering off", status);
    // A returned OS (only the probe returns) ends the run; on hardware this becomes "back to the picker".
    uefi::runtime::reset(ResetType::SHUTDOWN, status, None)
}
