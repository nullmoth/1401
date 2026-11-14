# Turing Architecture (TU106 / RTX 2060 SUPER, TU104, TU116) Stutter & BAR1 Fix

## 1. Problem Overview

On macOS Sequoia (and Sonoma) running NVIDIA Turing architecture GPUs (e.g. GeForce RTX 2060 SUPER / TU106, RTX 2070 / TU104, GTX 1660 / TU116) via the NullMoth 1401 driver stack, systems frequently experience:
- Severe UI stuttering and micro-freezes when moving or dragging windows.
- Windows turning pitch black or dropping rendering surfaces during movement.
- Hitching during user interactions after moments of inactivity.
- Frame drops in desktop applications (Discord, Safari, Terminal, Electron apps).

---

## 2. Root Causes Identified & Reverse Engineered

### Root Cause A: Framebuffer VRAM Grant 256MB Budget Limit (`NVRMFB.kext`)
- **Location**: `NVRMFB` binary, function `vramGrant`, file offset `0x21ea3`.
- **Mechanism**: The framebuffer driver enforces a hardcoded 256MB VRAM allocation ceiling intended for small BAR1 windows. When WindowServer allocates backing stores or animated surfaces that exceed 256MB in total active VRAM grants, the conditional branch at `0x21ea3` triggers an error return (`kIOReturnNoMemory`).
- **Symptom**: WindowServer fails to allocate the surface buffer, resulting in black window rectangles and frame skips.
- **Binary Patch**:
  - Stock bytes: `0f 8e 6d 01 00 00` (`jle 0x22016`)
  - Patched bytes: `e9 6e 01 00 00 90` (`jmp 0x22016; nop`)
  - Bypasses the 256MB ceiling rejection, allowing the driver to handle allocations smoothly across system memory.

### Root Cause B: Aggressive Inactivity Surface Eviction (`NVAccel.kext`)
- **Location**: `NVAccel` binary, global variable `gSurfGpuOn`, file offset `0x251e0`.
- **Mechanism**: NVAccel implements an aggressive 100ms idle timer. If a window surface is untouched for 100ms, it is immediately evicted from GPU memory. The instant the mouse moves over the window or the user interacts with it, the driver is forced to stall the render pipeline while re-uploading the entire surface to VRAM.
- **Symptom**: Constant micro-stutters every time interaction resumes after brief pauses.
- **Binary Patch**:
  - Change `gSurfGpuOn` from `1` (`01 00 00 00`) to `0` (`00 00 00 00`).
  - Sysctl equivalent: `debug.nvaccel_surface_gpu_on=0`.

### Root Cause C: Sticky Virtual Memory Churn (`NVAccel.kext`)
- **Location**: `NVAccel` binary, global variable `gVmSticky`, file offset `0x23f1c`.
- **Mechanism**: NVAccel retains sticky VM mappings across surface reallocations. During dynamic resizing or dragging across screens, this causes address space churn and memory thrashing.
- **Binary Patch**:
  - Change `gVmSticky` from `1` (`01 00 00 00`) to `0` (`00 00 00 00`).
  - Sysctl equivalent: `debug.nvaccel_vm_sticky=0`.

### Root Cause D: Metal Small-BAR1 Driver Misconfiguration (`nvrm610.conf`)
- **Location**: `/Library/GPUBundles/nvmtl/nvrm610.conf` (managed via `mac/Resources/nullmoth-rules.json`).
- **Mechanism**: Default driver configuration hoards large chunk pools and enables buffer grace periods designed for GPUs with large BAR (e.g. 8GB+). On small 256MB BAR1 Turing cards, this exhausts BAR1 aperture almost instantly.
- **Fix**:
  - `NVMTL_VRAM_HEADROOM_MB=48`: Prevents out-of-memory stalls while maintaining sufficient headroom.
  - `NVMTL_NO_SURFACE_PAGEOFF=0`: Keeps active desktop surfaces responsive.
  - `NVMTL_POOL_POLL_MS=0` & `NVMTL_CMD_POOL_MAX_CHUNKS=256`: Streamlines command buffer scheduling.
  - `NVMTL_NO_BUFREUSE=1`, `NVMTL_IMAGE_POOL=0`, `NVMTL_PRIVATE_POOL=0`: Disables memory hoarding on constrained apertures.
  - `NVMTL_GSUB_HOSTPTR_LIFT=1`: Bypasses slow HostPtr bounce buffers.

---

## 3. How Fixes are Integrated into 1401

1. **Automatic Rule Activation**:
   Added `turing-bar1-stutter-optimization` to `mac/Resources/nullmoth-rules.json`. When 1401 installs on any Turing GPU (`arch: ["turing"]`), these optimized knobs are written to `/Library/GPUBundles/nvmtl/nvrm610.conf`.

2. **Automated Kernel Extension Patching**:
   Added `patch_turing_stutter()` to `mac/Resources/nullmoth-setup.sh`. It automatically inspects `NVRMFB` and `NVAccel`, applies the hex patches, updates ad-hoc signatures, and rebuilds `/Library/KernelCollections/AuxiliaryKernelExtensions.kc`.

3. **Standalone Diagnostics & Utility Script**:
   Located at `tools/apply-turing-fix.sh` (and `mac/Resources/nullmoth-turing-optimize.sh`):
   - Check patch status:
     ```bash
     bash tools/apply-turing-fix.sh --check
     ```
   - Apply fixes manually:
     ```bash
     sudo bash tools/apply-turing-fix.sh
     ```
   - Revert to stock backups:
     ```bash
     sudo bash tools/apply-turing-fix.sh --revert
     ```

---

## 4. Verification & Results

Verified on hardware:
- **CPU**: AMD Ryzen 5 5600 6-Core Processor
- **GPU**: NVIDIA GeForce RTX 2060 SUPER 8GB (Device ID `10de:1f06`, Turing TU106)
- **OS**: macOS Sequoia 15.8.3 (Kernel Darwin 24.6.0 x86_64)

### Benchmarks / Observations:
- **Window Dragging**: 60 FPS smooth, zero surface drops, zero black frames.
- **Metal Performance**: Metal 3 API acceleration fully functional with responsive WindowServer.
- **Voice/Video Stability**: Zero audio/video pipeline interference. Hardware encoders (NVENC) remain fully operational.
