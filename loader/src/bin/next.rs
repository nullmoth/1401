//! The QEMU suite's chain-load target: proves the loader started a second image from its real device path, and
//! that the second image can see where it was loaded from (what Windows Boot Manager needs to find its BCD).
#![no_main]
#![no_std]

use uefi::prelude::*;
use uefi::println;
use uefi::proto::loaded_image::LoadedImage;

#[entry]
fn main() -> Status {
    uefi::helpers::init().unwrap();
    let me = boot::open_protocol_exclusive::<LoadedImage>(boot::image_handle());
    let has_path = me.map(|li| li.file_path().is_some()).unwrap_or(false);
    println!("1401 probe: chainload ok, own file path {}", if has_path { "present" } else { "MISSING" });
    Status::SUCCESS
}
