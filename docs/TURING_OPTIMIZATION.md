# Turing (TU104 / TU106 / TU116) WindowServer Stutter & 256 MB BAR1 Fix

## Overview

On macOS 15 running NVIDIA Turing GPUs (RTX 2060 SUPER / TU106, RTX 2070 / TU104, GTX 1660 / TU116) with a 256 MB BAR1 aperture, desktop interaction can exhibit:
- UI micro-stutters when dragging windows or resuming interaction after brief idle periods.
- WindowServer surface allocation drops or black window contents under rapid compositing.

## Root Causes

1. **Metal Small-BAR1 Pooling & Headroom (`nvrm610.conf`)**
   Default Metal pooling and buffer grace settings hoard GPU allocations and exhaust a 256 MB BAR1 window under WindowServer load. Setting `NVMTL_VRAM_HEADROOM_MB=48`, enabling `NVMTL_NO_SURFACE_PAGEOFF=0`, disabling buffer reuse/grace pools (`NVMTL_NO_BUFREUSE=1`, `NVMTL_IMAGE_POOL=0`, `NVMTL_PRIVATE_POOL=0`, `NVMTL_BUFFER_GRACE=0`, `NVMTL_IMAGE_GRACE=0`), and enabling `NVMTL_GSUB_HOSTPTR_LIFT=1` stabilizes surface allocation.

2. **Framebuffer 256 MB VRAM Grant Ceiling (`NVRMFB.kext`)**
   On driver `3.0` (macOS 15), `vramGrant` in `NVRMFB` checks an internal 256 MB grant ceiling at file offset `0x21ea3` (`0f 8e 6d 01 00 00` -> `e9 6e 01 00 00 90`), returning `kIOReturnNoMemory` under heavy WindowServer surface turnover.

3. **Inactivity Surface Eviction & Sticky VM Churn (`NVAccel.kext`)**
   On driver `3.0` (macOS 15), `gSurfGpuOn` (`0x251e0`) and `gVmSticky` (`0x23f1c`) evict idle surfaces and retain sticky VM mappings (`debug.nvaccel_surface_gpu_on`, `debug.nvaccel_vm_sticky`).

## Architecture Split in 1401

1. **Main Installation Path (Safe Metal Rules — `mac/Resources/nullmoth-rules.json`)**
   `turing-bar1-stutter-optimization` matches `{"arch": ["turing"]}` and passes its `NVMTL_*` / `NVK_*` knobs through `nullmoth-setup.sh` into `# --- 1401 per-system rules ---` inside `/Library/GPUBundles/nvmtl/nvrm610.conf`.
   `nullmoth-setup.sh` never modifies kext binaries in place, preserving SHA-256 package verification, per-OS kext manifests (`/Library/NullMoth/kexts/{15,26}`), and audited uninstallation.

2. **Optional Standalone Kext Tool (`tools/apply-turing-fix.sh`)**
   Users who still hit `NVRMFB`/`NVAccel` drops on verified driver `3.0` / macOS `15` builds can run `tools/apply-turing-fix.sh` manually. Before touching any kext binary, it verifies:
   - Root privileges and disabled SIP filesystem protections.
   - macOS major `15`, installed driver version `3.0`, and a Turing PCI device ID (`1e00..21ff`).
   - 64-bit Mach-O magic, bounds, expected `NVAccel` sysctl symbol strings, optional `--accel-sha256` / `--fb-sha256` pins, and exact expected bytes at each offset.
   - SHA-256-recorded backups under `/Library/NullMoth/turing-backup/` and `kmutil inspect` verification with automatic rollback on failure.
   - Non-destructive marked `# --- 1401 turing-fix ---` block updates in `nvrm610.conf` (preserving existing rules and user settings).

### Usage

```bash
# Inspect status without modifying files
bash tools/apply-turing-fix.sh --check

# Apply optional kext patches (driver 3.0 / macOS 15)
sudo bash tools/apply-turing-fix.sh --apply

# Apply only the marked Metal nvrm610.conf block
sudo bash tools/apply-turing-fix.sh --conf-only

# Verify backup SHA256SUMS and restore stock binaries + AuxKC
sudo bash tools/apply-turing-fix.sh --revert
```

## Hardware Tested

- **CPU**: AMD Ryzen 5 5600
- **GPU**: NVIDIA GeForce RTX 2060 SUPER 8 GB (`10de:1f06`, Turing TU106, 256 MB BAR1)
- **OS**: macOS Sequoia 15.8.3 (x86_64)
- **Observed**: Smooth 60 FPS window dragging with no black surfaces or WindowServer hitches; NVENC remains active.
