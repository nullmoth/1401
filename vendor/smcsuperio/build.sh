#!/bin/bash
# build.sh <new work dir> <out dir>: VirtualSMC and its sensor plugins (SMCSuperIO: fan speeds from the board's Super I/O
# chip; SMCProcessor, SMCBatteryManager, SMCLightSensor, SMCDellSensors) built from source as one set, for the EFI 1401
# writes; a plugin must match the VirtualSMC it loads into, so the whole set comes from the same commit. Upstream is acidanthera/VirtualSMC (BSD-3-Clause, LICENSE-VirtualSMC.txt); Lilu and MacKernelSDK are
# built from source too, so nothing prebuilt goes into the kext. smcsuperio-29.patch adds the ITE IT8696E and IT8698E (the
# IT8689E feature set, per Linux it87's device table) and the early IT87952E id, and fixes three model checks that used
# strcmp as if it returned true on a match (every ITE chip took the extended-register and alternate-PWM paths).
# Needs Xcode. x86_64 only: the EFI targets Intel and AMD PCs. The work dir must be new or hold these exact commits.
set -euo pipefail
W=${1:?work dir}; OUT=${2:?out dir}
VSMC=b5c62c2311540c529c00996d0d9cec33f8e571c9 LILU=0249c3a918c68a43891350f35fded615b1575776 SDK=3f750085caa17ec3a7880f11c11bf4f48cd6a164
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$W" "$OUT"; W=$(cd "$W" && pwd); OUT=$(cd "$OUT" && pwd)
fetch() {   # <dir> <url> <commit>: a fresh clone at the pinned commit; an existing clone must already be exactly there
  if [ ! -d "$W/$1/.git" ]; then
    git clone -q "$2" "$W/$1"
    git -C "$W/$1" switch -q --detach "$3"
  fi
  [ "$(git -C "$W/$1" rev-parse HEAD)" = "$3" ] || { echo "STOP: $W/$1 is not at $3; use a new work dir"; exit 1; }
}
fetch MacKernelSDK https://github.com/acidanthera/MacKernelSDK.git "$SDK"
fetch Lilu https://github.com/acidanthera/Lilu.git "$LILU"
fetch VirtualSMC https://github.com/acidanthera/VirtualSMC.git "$VSMC"
ln -sfn ../MacKernelSDK "$W/Lilu/MacKernelSDK"; ln -sfn ../MacKernelSDK "$W/VirtualSMC/MacKernelSDK"
[ -d "$W/Lilu/build/Debug/Lilu.kext" ] || \
  (cd "$W/Lilu" && xcodebuild -jobs 4 -project Lilu.xcodeproj -target Lilu -configuration Debug -arch x86_64) > "$OUT/lilu.log" 2>&1
rm -rf "$W/VirtualSMC/Lilu.kext"; cp -R "$W/Lilu/build/Debug/Lilu.kext" "$W/VirtualSMC/Lilu.kext"
if git -C "$W/VirtualSMC" diff --quiet; then git -C "$W/VirtualSMC" apply "$HERE/smcsuperio-29.patch"; fi
git -C "$W/VirtualSMC" diff --quiet && { echo "STOP: the patch changed nothing"; exit 1; }
# Build settings that only quiet the build system: the project's 10.6 target is below what Xcode supports (the EFI is for
# macOS 15 and 26), the target order is fixed by -target, and the linker sees -lkmod twice from the project.
# -Wno-invalid-offsetof covers MacKernelSDK's IOSMBusController.h (Apple's header, not ours).
SET=(MACOSX_DEPLOYMENT_TARGET=10.13 DISABLE_MANUAL_TARGET_ORDER_BUILD_WARNING=YES DEBUG_INFORMATION_FORMAT=dwarf
     'OTHER_LDFLAGS=$(inherited) -Wl,-no_warn_duplicate_libraries' 'OTHER_CPLUSPLUSFLAGS=$(inherited) -Wno-invalid-offsetof')
KEXTS="VirtualSMC SMCProcessor SMCBatteryManager SMCLightSensor SMCSuperIO SMCDellSensors"
: > "$OUT/smcsuperio.log"
for t in $KEXTS; do
  (cd "$W/VirtualSMC" && xcodebuild -jobs 4 -project VirtualSMC.xcodeproj -target "$t" -configuration Release -arch x86_64 "${SET[@]}") >> "$OUT/smcsuperio.log" 2>&1 \
    || { echo "STOP: $t did not build (see $OUT/smcsuperio.log)"; exit 1; }
done
for t in $KEXTS; do
  K="$W/VirtualSMC/build/Release/$t.kext"
  [ -d "$K" ] || { echo "STOP: no $t.kext"; exit 1; }
  rm -rf "$OUT/$t.kext"; cp -R "$K" "$OUT/$t.kext"
done
grep -q 'ITE IT8696E' "$OUT/SMCSuperIO.kext/Contents/MacOS/SMCSuperIO" || { echo "STOP: SMCSuperIO does not carry the IT8696E entry"; exit 1; }
W_N=$(grep -c 'warning:' "$OUT/smcsuperio.log" || true)
(cd "$OUT" && for t in $KEXTS; do printf '%s  %s\n' "$(shasum -a 256 "$t.kext/Contents/MacOS/$t" | cut -d' ' -f1)" "$t.kext"; done) > "$OUT/SHA256SUMS"
echo "VirtualSMC set built ($(echo $KEXTS | wc -w | tr -d ' ') kexts), warnings $W_N"; cat "$OUT/SHA256SUMS"
[ "$W_N" = 0 ] || { grep 'warning:' "$OUT/smcsuperio.log" | sort -u | head -10; exit 1; }
