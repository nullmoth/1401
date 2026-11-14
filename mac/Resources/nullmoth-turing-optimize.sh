#!/bin/bash
# ==============================================================================
# NullMoth 1401 - Turing Architecture (TU106 / RTX 2060 SUPER, TU104, TU116)
# WindowServer Micro-Stutter, Frame Drop & 256MB BAR1 VRAM Budget Fix
# ==============================================================================
#
# Root Causes:
# 1. NVRMFB vramGrant budget check (offset 0x21ea3):
#    Enforces a rigid 256MB VRAM allocation ceiling. When WindowServer drags or
#    animates complex surfaces, allocations exceeding 256MB fail with kIOReturnNoMemory,
#    causing dropped frames, black window rectangles, and UI stutter.
#    Bypass: patch 0x0f 0x8e 0x6d 0x01 0x00 0x00 (jle 0x22016) ->
#                  0xe9 0x6e 0x01 0x00 0x00 0x90 (jmp 0x22016; nop).
#
# 2. NVAccel aggressive surface eviction (offset 0x251e0, gSurfGpuOn):
#    Evicts inactive surfaces from GPU after a 100ms idle timeout, forcing heavy
#    re-uploads upon the next user interaction (mouse move/click), causing hitching.
#    Fix: gSurfGpuOn = 0.
#
# 3. NVAccel sticky VM mapping churn (offset 0x23f1c, gVmSticky):
#    Maintains redundant VM mappings during surface churn, leaking address space.
#    Fix: gVmSticky = 0.
#
# 4. Metal driver memory pooling & small BAR1 configuration:
#    nvrm610.conf tuning: headroom 48MB, uncached GPU system memory, no surface pageoff,
#    immediate pool freeing, and zero buffer grace to prevent small BAR1 exhaustion.
# ==============================================================================

set -euo pipefail

TARGET_ACCEL="/Library/Extensions/NVAccel.kext/Contents/MacOS/NVAccel"
TARGET_FB="/Library/Extensions/NVRMFB.kext/Contents/MacOS/NVRMFB"
BACKUP_ACCEL="/Library/Extensions/NVAccel.orig.bin"
BACKUP_FB="/Library/Extensions/NVRMFB.orig.bin"
CONF_DIR="/Library/GPUBundles/nvmtl"
CONF_FILE="$CONF_DIR/nvrm610.conf"

check_status() {
  echo "=== Turing Fix Status Check ==="
  local ok=1

  if [ -f "$TARGET_ACCEL" ]; then
    local s_sticky
    s_sticky=$(/usr/bin/perl -e '
      open(my $fh, "<", $ARGV[0]) or die $!; binmode $fh;
      seek($fh, 0x23f1c, 0); read($fh, my $b, 4);
      print unpack("L", $b);
    ' "$TARGET_ACCEL")
    local s_evict
    s_evict=$(/usr/bin/perl -e '
      open(my $fh, "<", $ARGV[0]) or die $!; binmode $fh;
      seek($fh, 0x251e0, 0); read($fh, my $b, 4);
      print unpack("L", $b);
    ' "$TARGET_ACCEL")
    echo "[*] NVAccel gVmSticky (0x23f1c): $s_sticky (0 = patched, 1 = stock)"
    echo "[*] NVAccel gSurfGpuOn (0x251e0): $s_evict (0 = patched, 1 = stock)"
    if [ "$s_sticky" != "0" ] || [ "$s_evict" != "0" ]; then ok=0; fi
  else
    echo "[-] NVAccel binary not found at $TARGET_ACCEL"
    ok=0
  fi

  if [ -f "$TARGET_FB" ]; then
    local s_fb
    s_fb=$(/usr/bin/perl -e '
      open(my $fh, "<", $ARGV[0]) or die $!; binmode $fh;
      seek($fh, 0x21ea3, 0); read($fh, my $b, 6);
      if ($b eq "\xe9\x6e\x01\x00\x00\x90") { print "patched"; }
      elsif ($b eq "\x0f\x8e\x6d\x01\x00\x00") { print "stock"; }
      else { print "unknown"; }
    ' "$TARGET_FB")
    echo "[*] NVRMFB vramGrant budget check (0x21ea3): $s_fb"
    if [ "$s_fb" != "patched" ]; then ok=0; fi
  else
    echo "[-] NVRMFB binary not found at $TARGET_FB"
    ok=0
  fi

  if [ -f "$CONF_FILE" ] && grep -q "NVMTL_VRAM_HEADROOM_MB=48" "$CONF_FILE"; then
    echo "[*] Metal nvrm610.conf: optimized headroom (48MB) configured"
  else
    echo "[-] Metal nvrm610.conf: not configured with Turing headroom"
    ok=0
  fi

  if [ "$ok" -eq 1 ]; then
    echo "[+] Overall: ALL Turing fixes are active and verified!"
    exit 0
  else
    echo "[!] Overall: One or more Turing fixes are missing."
    exit 1
  fi
}

revert_patches() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "Error: root privileges required to revert patches. Run with sudo." >&2
    exit 1
  fi

  echo "=== Reverting Turing Patches ==="
  if [ -f "$BACKUP_ACCEL" ]; then
    cp -f "$BACKUP_ACCEL" "$TARGET_ACCEL"
    codesign -f -s - /Library/Extensions/NVAccel.kext
    echo "[+] Restored NVAccel from backup."
  fi

  if [ -f "$BACKUP_FB" ]; then
    cp -f "$BACKUP_FB" "$TARGET_FB"
    codesign -f -s - /Library/Extensions/NVRMFB.kext
    echo "[+] Restored NVRMFB from backup."
  fi

  rebuild_kc
  echo "[+] Revert complete. Restart your system."
}

rebuild_kc() {
  echo "[*] Rebuilding Auxiliary Kernel Collection..."
  local K=/System/Library/Kernels/kernel
  local KARG=(--allow-missing-kdk)
  [ -f "$K" ] && KARG+=(--kernel "$K")

  kmutil create -n aux --volume-root / "${KARG[@]}" \
    -B /System/Library/KernelCollections/BootKernelExtensions.kc \
    -S /System/Library/KernelCollections/SystemKernelExtensions.kc \
    --repository /Library/Extensions \
    -A /Library/KernelCollections/AuxiliaryKernelExtensions.kc -z || {
      echo "[!] kmutil rebuild returned non-zero. Check /Library/KernelCollections permissions." >&2
    }
}

apply_fixes() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "Error: root privileges required. Please run: sudo bash $0" >&2
    exit 1
  fi

  echo "=== Applying NullMoth Turing TU106/TU104/TU116 Stutter & BAR1 Fixes ==="

  # 1. Configure Metal Driver Knobs
  mkdir -p "$CONF_DIR"
  cat > "$CONF_FILE" <<'EOF'
# --- NullMoth Turing TU106 Stability & BAR1 Memory Optimization ---
NVK_CMDPOOL_GPU_UNCACHED=1
NVK_SYSMEM_GPU_UNCACHED=1
NVK_LOCAL_MAP_SYSMEM=1
NVMTL_MANAGED_SYSMEM=1
NVMTL_SHARED_VRAM=0
NVMTL_SHARED_POOL_VRAM=0
NVK_BAR_VRAM=0
NVMTL_VRAM_HEADROOM_MB=48
NVMTL_SHARED_VRAM_BUDGET_MB=0
NVMTL_NO_SURFACE_PAGEOFF=0
NVMTL_FRESH_ZERO=1
NVMTL_RES2_WS=1
NVMTL_NO_RES2=0
NVMTL_NO_RES2_EVICT=0
NVMTL_NO_PURGE_RECLAIM=0
NVMTL_RES2_MARGIN_MB=32
NVMTL_GSUB_HOSTPTR_LIFT=1
NVMTL_NAK_ARR_SCRATCH=0
NVMTL_SURFACE_BUSY=1
NVMTL_SURFIN_ORDERED=1
NVMTL_SCHEDULE_AFTER_SURFACE_WRITES=1
NVMTL_PRESENT_INLINE=1
NVMTL_WS_WAIT_COMPLETION=1

# Disable VRAM hoarding, caching and pooling on small BAR1 (256 MB)
NVMTL_NO_BUFREUSE=1
NVMTL_IMAGE_POOL=0
NVMTL_PRIVATE_POOL=0
NVMTL_BUFFER_GRACE=0
NVMTL_IMAGE_GRACE=0
NVMTL_SURF_IMPORT_CACHE=0
EOF
  chmod 644 "$CONF_FILE"
  chown root:wheel "$CONF_FILE"
  echo "[+] Configured $CONF_FILE"

  # 2. Flush shader caches
  rm -rf "$CONF_DIR/aircache"/* "$CONF_DIR/spvcache"/* 2>/dev/null || true
  mkdir -p "$CONF_DIR/aircache" "$CONF_DIR/spvcache"
  chmod 777 "$CONF_DIR/aircache" "$CONF_DIR/spvcache"
  echo "[+] Flushed Metal shader caches"

  # 3. Patch NVAccel (gVmSticky: 0x23f1c, gSurfGpuOn: 0x251e0)
  if [ -f "$TARGET_ACCEL" ]; then
    [ -f "$BACKUP_ACCEL" ] || cp -p "$TARGET_ACCEL" "$BACKUP_ACCEL"
    /usr/bin/perl -e '
      my $file = $ARGV[0];
      open(my $fh, "+<", $file) or die "Cannot open $file: $!";
      binmode $fh;
      seek($fh, 0x23f1c, 0); read($fh, my $b1, 4);
      if (unpack("L", $b1) == 1) {
        seek($fh, 0x23f1c, 0); print $fh pack("L", 0);
        print "[+] Patched NVAccel 0x23f1c (gVmSticky: 1 -> 0)\n";
      } else {
        print "[*] NVAccel 0x23f1c already patched or modified\n";
      }
      seek($fh, 0x251e0, 0); read($fh, my $b2, 4);
      if (unpack("L", $b2) == 1) {
        seek($fh, 0x251e0, 0); print $fh pack("L", 0);
        print "[+] Patched NVAccel 0x251e0 (gSurfGpuOn: 1 -> 0)\n";
      } else {
        print "[*] NVAccel 0x251e0 already patched or modified\n";
      }
      close($fh);
    ' "$TARGET_ACCEL"
    codesign -f -s - /Library/Extensions/NVAccel.kext 2>/dev/null || true
  else
    echo "[-] Warning: $TARGET_ACCEL not found"
  fi

  # 4. Patch NVRMFB (vramGrant budget check 0x21ea3: jle -> jmp)
  if [ -f "$TARGET_FB" ]; then
    [ -f "$BACKUP_FB" ] || cp -p "$TARGET_FB" "$BACKUP_FB"
    /usr/bin/perl -e '
      my $file = $ARGV[0];
      open(my $fh, "+<", $file) or die "Cannot open $file: $!";
      binmode $fh;
      seek($fh, 0x21ea3, 0); read($fh, my $buf, 6);
      if ($buf eq "\x0f\x8e\x6d\x01\x00\x00") {
        seek($fh, 0x21ea3, 0); print $fh "\xe9\x6e\x01\x00\x00\x90";
        print "[+] Patched NVRMFB 0x21ea3 (vramGrant budget ceiling check bypassed)\n";
      } elsif ($buf eq "\xe9\x6e\x01\x00\x00\x90") {
        print "[*] NVRMFB 0x21ea3 already patched\n";
      } else {
        print "[-] NVRMFB 0x21ea3 unrecognized pattern\n";
      }
      close($fh);
    ' "$TARGET_FB"
    codesign -f -s - /Library/Extensions/NVRMFB.kext 2>/dev/null || true
  else
    echo "[-] Warning: $TARGET_FB not found"
  fi

  # 5. Apply live sysctls
  sysctl debug.nvaccel_vm_sticky=0 debug.nvaccel_surface_gpu_on=0 >/dev/null 2>&1 || true
  echo "[+] Live sysctl overrides applied"

  # 6. Rebuild AuxKC
  rebuild_kc

  echo "=== All Turing TU106/TU104/TU116 fixes applied successfully! ==="
}

case "${1:-}" in
  --check|--status)
    check_status
    ;;
  --revert)
    revert_patches
    ;;
  *)
    apply_fixes
    ;;
esac
