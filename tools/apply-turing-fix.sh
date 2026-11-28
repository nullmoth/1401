#!/bin/bash
# Optional standalone Turing (TU104/TU106/TU116) BAR1 & WindowServer stutter tool.
#
# Normal 1401 installs keep driver packages SHA-256 verified and never patch kexts
# in place; the Metal nvrm610.conf knobs live in mac/Resources/nullmoth-rules.json
# (`turing-bar1-stutter-optimization`) and are applied automatically by setup.
#
# This standalone tool applies/checks/reverts the optional NVAccel and NVRMFB
# binary patches for users hitting 256 MB BAR1 grant drops or 100 ms eviction
# hitches on verified driver 3.0 / macOS 15 builds. It validates OS version,
# driver version, GPU family, SIP status, Mach-O headers, optional SHA-256 pins,
# and exact byte patterns before modifying any file, and rolls back if kmutil fails.

set -euo pipefail
PATH=/usr/bin:/bin:/usr/sbin:/sbin; export PATH

TARGET_ACCEL="/Library/Extensions/NVAccel.kext/Contents/MacOS/NVAccel"
TARGET_FB="/Library/Extensions/NVRMFB.kext/Contents/MacOS/NVRMFB"
DRIVER_VER_FILE="/Library/NullMoth/driver-version"
BACKUP_DIR="/Library/NullMoth/turing-backup"
BACKUP_ACCEL="$BACKUP_DIR/NVAccel.orig"
BACKUP_FB="$BACKUP_DIR/NVRMFB.orig"
BACKUP_SUMS="$BACKUP_DIR/SHA256SUMS"
CONF_DIR="/Library/GPUBundles/nvmtl"
CONF_FILE="$CONF_DIR/nvrm610.conf"
CONF_START="# --- 1401 turing-fix ---"
CONF_END="# --- end 1401 turing-fix ---"
KC="/Library/KernelCollections/AuxiliaryKernelExtensions.kc"
KB="/System/Library/KernelCollections/BootKernelExtensions.kc"
KS="/System/Library/KernelCollections/SystemKernelExtensions.kc"

EXPECTED_OS_MAJOR="15"
EXPECTED_DRIVER_VERSION="3.0"
EXPECTED_ACCEL_SHA256="${EXPECTED_ACCEL_SHA256:-}"
EXPECTED_FB_SHA256="${EXPECTED_FB_SHA256:-}"
ALLOW_VERSION_MISMATCH=0
ACTION="apply"

# Verified offsets for NullMoth driver 3.0 (macOS 15 x86_64)
OFF_ACCEL_VM_STICKY="0x23f1c"
OFF_ACCEL_SURF_GPU_ON="0x251e0"
OFF_FB_VRAM_GRANT="0x21ea3"

die() {
  echo "STOP: $*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage:
  bash tools/apply-turing-fix.sh --check
  sudo bash tools/apply-turing-fix.sh [--apply] [--accel-sha256 HEX] [--fb-sha256 HEX]
  sudo bash tools/apply-turing-fix.sh --conf-only
  sudo bash tools/apply-turing-fix.sh --revert

Options:
  --check, --status        Read-only check of OS/driver version, binary patch state, and nvrm610.conf
  --apply                  Verify guards and apply optional NVAccel/NVRMFB patches + AuxKC rebuild
  --conf-only              Only write the marked Turing block into nvrm610.conf (no kext changes)
  --revert                 Verify backup SHA256SUMS, restore kext binaries, remove conf block, rebuild AuxKC
  --accel-sha256 HEX       Require NVAccel binary to match this stock SHA-256 before patching
  --fb-sha256 HEX          Require NVRMFB binary to match this stock SHA-256 before patching
  --allow-version-mismatch Allow patching if driver-version != 3.0 or macOS != 15 (exact bytes still checked)
  --help, -h               Show this help text
EOF
}

nv_device_id() {
  ioreg -r -c IOPCIDevice -l -w0 2>/dev/null | LC_ALL=C awk '
    function emit() {
      if (v && d != "") {
        id = substr(d,3,2) substr(d,1,2)
        if (c == 300 && vga == "") vga = id
        else if (c == 302 && d3d == "") d3d = id
      }
    }
    /\+-o / { emit(); v=0; c=0; d="" }
    /"vendor-id" = <de100000>/ { v=1 }
    /"class-code" = <00000300>/ { c=300 }
    /"class-code" = <00000302>/ { c=302 }
    /"device-id" = </ { if (match($0, /<[0-9a-f]+>/)) d=substr($0, RSTART+1, 4) }
    END { emit(); print (vga != "" ? vga : d3d) }'
}

is_turing_id() {
  case "${1:-}" in
    1[eEfF]??|21[89a-fA-F]?) return 0 ;;
    *) return 1 ;;
  esac
}

sip_protecting_fs() {
  local status
  status=$(csrutil status 2>/dev/null || true)
  printf '%s\n' "$status" | grep -qE 'status: enabled\.|Filesystem Protections: enabled'
}

read_driver_version() {
  if [ -f "$DRIVER_VER_FILE" ]; then
    tr -d '[:space:]' < "$DRIVER_VER_FILE" 2>/dev/null || true
    return
  fi
  plutil -extract CFBundleShortVersionString raw -o - /Library/Extensions/NVRMFB.kext/Contents/Info.plist 2>/dev/null || true
}

inspect_accel_state() {
  /usr/bin/perl -e '
    use strict; use warnings;
    my ($file, $off1, $off2) = @ARGV;
    open(my $fh, "<", $file) or die "cannot open $file: $!\n";
    binmode $fh;
    my $size = -s $file;
    die "file too small ($size bytes)\n" if !defined($size) || $size <= ($off2 + 4);
    read($fh, my $magic, 4) == 4 or die "short read magic\n";
    die "not 64-bit Mach-O\n" if $magic ne "\xcf\xfa\xed\xfe";
    seek($fh, $off1, 0) or die "seek $off1 failed\n";
    read($fh, my $b1, 4) == 4 or die "short read $off1\n";
    seek($fh, $off2, 0) or die "seek $off2 failed\n";
    read($fh, my $b2, 4) == 4 or die "short read $off2\n";
    close($fh);
    my $v1 = unpack("V", $b1);
    my $v2 = unpack("V", $b2);
    print "$v1 $v2\n";
  ' "$1" "$(($OFF_ACCEL_VM_STICKY))" "$(($OFF_ACCEL_SURF_GPU_ON))"
}

inspect_fb_state() {
  /usr/bin/perl -e '
    use strict; use warnings;
    my ($file, $off) = @ARGV;
    open(my $fh, "<", $file) or die "cannot open $file: $!\n";
    binmode $fh;
    my $size = -s $file;
    die "file too small ($size bytes)\n" if !defined($size) || $size <= ($off + 6);
    read($fh, my $magic, 4) == 4 or die "short read magic\n";
    die "not 64-bit Mach-O\n" if $magic ne "\xcf\xfa\xed\xfe";
    seek($fh, $off, 0) or die "seek $off failed\n";
    read($fh, my $buf, 6) == 6 or die "short read $off\n";
    close($fh);
    if ($buf eq "\xe9\x6e\x01\x00\x00\x90") { print "patched\n"; }
    elsif ($buf eq "\x0f\x8e\x6d\x01\x00\x00") { print "stock\n"; }
    else { print "unknown\n"; }
  ' "$1" "$(($OFF_FB_VRAM_GRANT))"
}

write_conf_block() {
  mkdir -p "$CONF_DIR"
  local tmp
  tmp=$(mktemp "$CONF_DIR/.nvrm610.XXXXXX") || die "could not create temporary file in $CONF_DIR"
  if [ -f "$CONF_FILE" ]; then
    awk -v start="$CONF_START" -v end="$CONF_END" '
      $0 == start { skip=1; next }
      $0 == end { skip=0; next }
      !skip { print }
    ' "$CONF_FILE" > "$tmp" || { rm -f "$tmp"; die "could not preserve existing $CONF_FILE"; }
  fi
  {
    echo "$CONF_START"
    cat <<'EOF'
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
NVMTL_NO_BUFREUSE=1
NVMTL_IMAGE_POOL=0
NVMTL_PRIVATE_POOL=0
NVMTL_BUFFER_GRACE=0
NVMTL_IMAGE_GRACE=0
NVMTL_SURF_IMPORT_CACHE=0
NVMTL_POOL_POLL_MS=0
NVMTL_CMD_POOL_MAX_CHUNKS=256
NVMTL_SURFACE_DEFER_FREE_MS=0
EOF
    echo "$CONF_END"
  } >> "$tmp"
  chmod 644 "$tmp" && chown root:wheel "$tmp" && mv -f "$tmp" "$CONF_FILE" || {
    rm -f "$tmp"
    die "could not update $CONF_FILE"
  }
  rm -rf "$CONF_DIR/aircache"/* "$CONF_DIR/spvcache"/* 2>/dev/null || true
  mkdir -p "$CONF_DIR/aircache" "$CONF_DIR/spvcache"
  chmod 777 "$CONF_DIR/aircache" "$CONF_DIR/spvcache"
  echo "[+] Updated marked Turing block in $CONF_FILE (existing settings preserved)"
}

remove_conf_block() {
  [ -f "$CONF_FILE" ] || return 0
  local tmp
  tmp=$(mktemp "$CONF_DIR/.nvrm610.XXXXXX") || die "could not create temporary file in $CONF_DIR"
  awk -v start="$CONF_START" -v end="$CONF_END" '
    $0 == start { skip=1; next }
    $0 == end { skip=0; next }
    !skip { print }
  ' "$CONF_FILE" > "$tmp" || { rm -f "$tmp"; die "could not clean $CONF_FILE"; }
  chmod 644 "$tmp" && chown root:wheel "$tmp" && mv -f "$tmp" "$CONF_FILE" || {
    rm -f "$tmp"
    die "could not save cleaned $CONF_FILE"
  }
  echo "[+] Removed marked Turing block from $CONF_FILE"
}

rebuild_and_verify_kc() {
  echo "[*] Rebuilding Auxiliary Kernel Collection..."
  local K=/System/Library/Kernels/kernel
  local KARG=(--allow-missing-kdk)
  [ -f "$K" ] && KARG+=(--kernel "$K")

  local new_kc="$KC.nullmoth-turing-new"
  rm -f "$new_kc"
  kmutil create -n aux --volume-root / "${KARG[@]}" \
    -B "$KB" -S "$KS" --repository /Library/Extensions \
    -A "$new_kc" -z || {
      rm -f "$new_kc"
      return 1
    }
  [ -s "$new_kc" ] || { rm -f "$new_kc"; return 1; }

  local ins
  ins=$(kmutil inspect -a x86_64 -A "$new_kc" 2>/dev/null || true)
  printf '%s\n' "$ins" | grep -q "com\.nullmoth\.NVAccel" || { rm -f "$new_kc"; return 1; }
  printf '%s\n' "$ins" | grep -q "com\.nullmoth\.NVRMFB" || { rm -f "$new_kc"; return 1; }

  mv -f "$new_kc" "$KC" || { rm -f "$new_kc"; return 1; }
  echo "[+] Auxiliary Kernel Collection rebuilt and verified (NVAccel + NVRMFB present)"
}

preflight_binary_checks() {
  [ "$(id -u)" -eq 0 ] || die "root privileges required (run with sudo)"
  ! sip_protecting_fs || die "System Integrity Protection protects /Library/Extensions or /Library/KernelCollections; disable filesystem protection via OpenCore first"

  local os_ver os_major drv_ver nvdev
  os_ver=$(sw_vers -productVersion 2>/dev/null || true)
  os_major=${os_ver%%.*}
  drv_ver=$(read_driver_version)
  nvdev=$(nv_device_id)

  if [ "$ALLOW_VERSION_MISMATCH" != 1 ]; then
    [ "$os_major" = "$EXPECTED_OS_MAJOR" ] || die "macOS major is '${os_major:-unknown}'; offsets apply only to macOS $EXPECTED_OS_MAJOR (pass --allow-version-mismatch to override byte-checked)"
    [ -n "$drv_ver" ] || die "cannot determine NullMoth driver version ($DRIVER_VER_FILE missing); pass --allow-version-mismatch if you verified the target binary"
    [ "$drv_ver" = "$EXPECTED_DRIVER_VERSION" ] || die "installed driver version is '$drv_ver'; offsets were verified only for $EXPECTED_DRIVER_VERSION (driver 3.1+ uses different offsets)"
  fi

  is_turing_id "$nvdev" || die "detected NVIDIA PCI device '${nvdev:-none}' is not Turing (1e00..21ff); refusing to patch"

  [ -f "$TARGET_ACCEL" ] && [ ! -L "$TARGET_ACCEL" ] || die "missing or symlinked binary: $TARGET_ACCEL"
  [ -f "$TARGET_FB" ] && [ ! -L "$TARGET_FB" ] || die "missing or symlinked binary: $TARGET_FB"

  LC_ALL=C grep -q "nvaccel_vm_sticky" "$TARGET_ACCEL" || die "$TARGET_ACCEL lacks nvaccel_vm_sticky symbol string"
  LC_ALL=C grep -q "nvaccel_surface_gpu_on" "$TARGET_ACCEL" || die "$TARGET_ACCEL lacks nvaccel_surface_gpu_on symbol string"

  local accel_state fb_state
  accel_state=$(inspect_accel_state "$TARGET_ACCEL") || die "NVAccel preflight failed"
  fb_state=$(inspect_fb_state "$TARGET_FB") || die "NVRMFB preflight failed"

  local v_sticky v_evict
  v_sticky=${accel_state%% *}
  v_evict=${accel_state##* }

  if [ "$v_sticky" != "0" ] && [ "$v_sticky" != "1" ]; then
    die "NVAccel $OFF_ACCEL_VM_STICKY has unexpected value '$v_sticky' (expected 0 or 1); nothing changed"
  fi
  if [ "$v_evict" != "0" ] && [ "$v_evict" != "1" ]; then
    die "NVAccel $OFF_ACCEL_SURF_GPU_ON has unexpected value '$v_evict' (expected 0 or 1); nothing changed"
  fi
  if [ "$fb_state" != "stock" ] && [ "$fb_state" != "patched" ]; then
    die "NVRMFB $OFF_FB_VRAM_GRANT has unrecognized bytes (driver build mismatch); nothing changed"
  fi

  if [ -n "$EXPECTED_ACCEL_SHA256" ]; then
    EXPECTED_ACCEL_SHA256=$(printf '%s' "$EXPECTED_ACCEL_SHA256" | tr 'A-Z' 'a-z')
    local check_a="$TARGET_ACCEL"
    [ "$v_sticky" = "0" ] && [ "$v_evict" = "0" ] && [ -f "$BACKUP_ACCEL" ] && check_a="$BACKUP_ACCEL"
    local got_a
    got_a=$(shasum -a 256 "$check_a" | awk '{print $1}')
    [ "$got_a" = "$EXPECTED_ACCEL_SHA256" ] || die "NVAccel SHA-256 '$got_a' does not match expected '$EXPECTED_ACCEL_SHA256'"
  fi
  if [ -n "$EXPECTED_FB_SHA256" ]; then
    EXPECTED_FB_SHA256=$(printf '%s' "$EXPECTED_FB_SHA256" | tr 'A-Z' 'a-z')
    local check_f="$TARGET_FB"
    [ "$fb_state" = "patched" ] && [ -f "$BACKUP_FB" ] && check_f="$BACKUP_FB"
    local got_f
    got_f=$(shasum -a 256 "$check_f" | awk '{print $1}')
    [ "$got_f" = "$EXPECTED_FB_SHA256" ] || die "NVRMFB SHA-256 '$got_f' does not match expected '$EXPECTED_FB_SHA256'"
  fi
}

check_status() {
  echo "=== Turing Fix Status Check ==="
  local os_ver drv_ver nvdev ok=1
  os_ver=$(sw_vers -productVersion 2>/dev/null || echo "unknown")
  drv_ver=$(read_driver_version)
  nvdev=$(nv_device_id)
  echo "[*] macOS: $os_ver | Driver: ${drv_ver:-unknown} | NVIDIA GPU: ${nvdev:-none}"

  if [ -f "$TARGET_ACCEL" ]; then
    local accel_state v_sticky v_evict
    if accel_state=$(inspect_accel_state "$TARGET_ACCEL" 2>/dev/null); then
      v_sticky=${accel_state%% *}
      v_evict=${accel_state##* }
      echo "[*] NVAccel gVmSticky ($OFF_ACCEL_VM_STICKY): $v_sticky (0 = patched, 1 = stock)"
      echo "[*] NVAccel gSurfGpuOn ($OFF_ACCEL_SURF_GPU_ON): $v_evict (0 = patched, 1 = stock)"
      if [ "$v_sticky" != "0" ] || [ "$v_evict" != "0" ]; then ok=0; fi
    else
      echo "[-] NVAccel failed Mach-O/bounds inspection"
      ok=0
    fi
  else
    echo "[-] NVAccel binary not found at $TARGET_ACCEL"
    ok=0
  fi

  if [ -f "$TARGET_FB" ]; then
    local s_fb
    s_fb=$(inspect_fb_state "$TARGET_FB" 2>/dev/null || echo "error")
    echo "[*] NVRMFB vramGrant budget check ($OFF_FB_VRAM_GRANT): $s_fb"
    if [ "$s_fb" != "patched" ]; then ok=0; fi
  else
    echo "[-] NVRMFB binary not found at $TARGET_FB"
    ok=0
  fi

  if [ -f "$CONF_FILE" ] && grep -q "NVMTL_VRAM_HEADROOM_MB=48" "$CONF_FILE"; then
    echo "[*] Metal nvrm610.conf: NVMTL_VRAM_HEADROOM_MB=48 present"
  else
    echo "[-] Metal nvrm610.conf: Turing BAR1 headroom rule not present"
    ok=0
  fi

  if [ -f "$BACKUP_SUMS" ]; then
    echo "[*] Verified backup manifest present at $BACKUP_SUMS"
  fi

  if [ "$ok" -eq 1 ]; then
    echo "[+] Overall: all checked Turing optimizations are active"
    exit 0
  else
    echo "[!] Overall: one or more checks are inactive or mismatched"
    exit 1
  fi
}

revert_patches() {
  [ "$(id -u)" -eq 0 ] || die "root privileges required to revert patches (run with sudo)"
  ! sip_protecting_fs || die "System Integrity Protection is enabled; cannot restore /Library/Extensions"
  [ -f "$BACKUP_SUMS" ] || die "backup checksum manifest missing at $BACKUP_SUMS; nothing restored"

  echo "=== Reverting Turing Patches ==="
  (cd "$BACKUP_DIR" && shasum -a 256 --strict -c SHA256SUMS --quiet) || die "backup files failed SHA-256 verification against $BACKUP_SUMS"

  [ -f "$BACKUP_ACCEL" ] && cp -p "$BACKUP_ACCEL" "$TARGET_ACCEL" && codesign -f -s - /Library/Extensions/NVAccel.kext
  [ -f "$BACKUP_FB" ] && cp -p "$BACKUP_FB" "$TARGET_FB" && codesign -f -s - /Library/Extensions/NVRMFB.kext
  remove_conf_block

  rebuild_and_verify_kc || die "kmutil rebuild/inspect failed during revert"
  rm -rf "$BACKUP_DIR"
  echo "[+] Revert complete and AuxKC verified. Restart your system."
}

rollback_on_error() {
  echo "[!] Patching or AuxKC verification failed; restoring stock binaries..." >&2
  [ -f "$BACKUP_ACCEL" ] && cp -p "$BACKUP_ACCEL" "$TARGET_ACCEL" 2>/dev/null || true
  [ -f "$BACKUP_FB" ] && cp -p "$BACKUP_FB" "$TARGET_FB" 2>/dev/null || true
  codesign -f -s - /Library/Extensions/NVAccel.kext 2>/dev/null || true
  codesign -f -s - /Library/Extensions/NVRMFB.kext 2>/dev/null || true
  rebuild_and_verify_kc >/dev/null 2>&1 || true
  die "aborted and restored original driver binaries"
}

apply_fixes() {
  preflight_binary_checks

  echo "=== Applying Optional Turing Stutter & BAR1 Kext Patches ==="
  mkdir -p "$BACKUP_DIR" && chmod 700 "$BACKUP_DIR"

  local accel_state fb_state v_sticky v_evict
  accel_state=$(inspect_accel_state "$TARGET_ACCEL")
  v_sticky=${accel_state%% *}
  v_evict=${accel_state##* }
  fb_state=$(inspect_fb_state "$TARGET_FB")

  if [ ! -f "$BACKUP_ACCEL" ]; then
    [ "$v_sticky" = "1" ] && [ "$v_evict" = "1" ] || die "cannot record clean backup: NVAccel is already modified without a backup"
    cp -p "$TARGET_ACCEL" "$BACKUP_ACCEL"
  fi
  if [ ! -f "$BACKUP_FB" ]; then
    [ "$fb_state" = "stock" ] || die "cannot record clean backup: NVRMFB is already modified without a backup"
    cp -p "$TARGET_FB" "$BACKUP_FB"
  fi
  (cd "$BACKUP_DIR" && shasum -a 256 NVAccel.orig NVRMFB.orig > SHA256SUMS.tmp && mv -f SHA256SUMS.tmp SHA256SUMS)
  chmod 600 "$BACKUP_ACCEL" "$BACKUP_FB" "$BACKUP_SUMS"

  /usr/bin/perl -e '
    use strict; use warnings;
    my ($file, $off1, $off2) = @ARGV;
    open(my $fh, "+<", $file) or die "cannot open $file: $!\n";
    binmode $fh;
    seek($fh, $off1, 0); read($fh, my $b1, 4) == 4 or die "short read\n";
    if (unpack("V", $b1) == 1) {
      seek($fh, $off1, 0); print $fh pack("V", 0);
      print "[+] Patched NVAccel gVmSticky -> 0\n";
    } else {
      print "[*] NVAccel gVmSticky already 0\n";
    }
    seek($fh, $off2, 0); read($fh, my $b2, 4) == 4 or die "short read\n";
    if (unpack("V", $b2) == 1) {
      seek($fh, $off2, 0); print $fh pack("V", 0);
      print "[+] Patched NVAccel gSurfGpuOn -> 0\n";
    } else {
      print "[*] NVAccel gSurfGpuOn already 0\n";
    }
    close($fh);
  ' "$TARGET_ACCEL" "$(($OFF_ACCEL_VM_STICKY))" "$(($OFF_ACCEL_SURF_GPU_ON))" || rollback_on_error
  codesign -f -s - /Library/Extensions/NVAccel.kext || rollback_on_error

  /usr/bin/perl -e '
    use strict; use warnings;
    my ($file, $off) = @ARGV;
    open(my $fh, "+<", $file) or die "cannot open $file: $!\n";
    binmode $fh;
    seek($fh, $off, 0); read($fh, my $buf, 6) == 6 or die "short read\n";
    if ($buf eq "\x0f\x8e\x6d\x01\x00\x00") {
      seek($fh, $off, 0); print $fh "\xe9\x6e\x01\x00\x00\x90";
      print "[+] Patched NVRMFB vramGrant branch\n";
    } elsif ($buf eq "\xe9\x6e\x01\x00\x00\x90") {
      print "[*] NVRMFB vramGrant branch already patched\n";
    } else {
      die "unexpected bytes at $off\n";
    }
    close($fh);
  ' "$TARGET_FB" "$(($OFF_FB_VRAM_GRANT))" || rollback_on_error
  codesign -f -s - /Library/Extensions/NVRMFB.kext || rollback_on_error

  rebuild_and_verify_kc || rollback_on_error

  if [ ! -f "$CONF_FILE" ] || ! grep -q "NVMTL_VRAM_HEADROOM_MB=48" "$CONF_FILE"; then
    write_conf_block
  else
    echo "[*] $CONF_FILE already contains Turing BAR1 rules; leaving existing blocks intact"
  fi

  sysctl debug.nvaccel_vm_sticky=0 debug.nvaccel_surface_gpu_on=0 >/dev/null 2>&1 || true
  echo "[+] Live sysctl overrides applied. Restart to load the updated AuxKC."
}

while [ $# -gt 0 ]; do
  case "$1" in
    --check|--status) ACTION="check" ;;
    --apply) ACTION="apply" ;;
    --conf-only) ACTION="conf" ;;
    --revert) ACTION="revert" ;;
    --accel-sha256) [ $# -ge 2 ] || die "--accel-sha256 requires a value"; EXPECTED_ACCEL_SHA256=$2; shift ;;
    --fb-sha256) [ $# -ge 2 ] || die "--fb-sha256 requires a value"; EXPECTED_FB_SHA256=$2; shift ;;
    --allow-version-mismatch) ALLOW_VERSION_MISMATCH=1 ;;
    --help|-h) usage; exit 0 ;;
    *) die "unknown option: $1 (see --help)" ;;
  esac
  shift
done

case "$ACTION" in
  check) check_status ;;
  conf) [ "$(id -u)" -eq 0 ] || die "root privileges required (run with sudo)"; write_conf_block ;;
  revert) revert_patches ;;
  apply) apply_fixes ;;
esac
