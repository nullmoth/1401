#!/bin/bash
# Reproducible build of the SimpleMtkWlan (MediaTek Wi-Fi) kext that 1401 hosts on its mirror.
#
#   tools/build_mtkwlan.sh <work dir>
#
# SimpleMtkWlan publishes no release, so 1401 builds it from a pinned commit against acidanthera's MacKernelSDK
# (the kext's own project configuration; that SDK carries IONetworkController::outputStart, which Apple dropped from
# the public macOS SDK headers). Needs the macOS 15 SDK (Command Line Tools provide it) and Xcode's xcodebuild.
# Prints the kext archive and matching GPL-2.0 source tarball with their sizes and SHA-256 - those are the values
# pinned in p1401/netsupport.py and p1401/mirror.json. Upload both files to nullmothsystems.com/mirror/<sha256>.
set -euo pipefail
WLAN_SHA=37ba676ad18273b7e622ec6db45afc25db238109
D=${1:?usage: build_mtkwlan.sh <work dir>}
mkdir -p "$D"; cd "$D"
[ -d src/.git ] || git clone --quiet https://github.com/laobamac/SimpleMtkWlan.git src
cd src
git fetch --quiet origin "$WLAN_SHA" 2>/dev/null || git fetch --quiet --all 2>/dev/null || true
git checkout -q "$WLAN_SHA"
[ -d MacKernelSDK/.git ] || git clone --quiet https://github.com/acidanthera/MacKernelSDK.git MacKernelSDK
echo "MacKernelSDK $(git -C MacKernelSDK rev-parse HEAD)"
rm -rf "$D/out" "$D/stage"
xcodebuild -project SimpleMtkWlan.xcodeproj -scheme SimpleMtkWlan -configuration Release \
  SYMROOT="$D/out" MACOSX_DEPLOYMENT_TARGET=15.0 CODE_SIGNING_ALLOWED=NO CODE_SIGN_IDENTITY="" build >"$D/xcodebuild.log" 2>&1
KEXT=$(find "$D/out" -name SimpleMtkWlan.kext -type d | grep -vi debug | head -1)
[ -n "$KEXT" ] || { echo "no kext built; see $D/xcodebuild.log"; exit 3; }
mkdir -p "$D/stage/SimpleMtkWlan-$WLAN_SHA"
cp -R "$KEXT" "$D/stage/SimpleMtkWlan-$WLAN_SHA/"
( cd "$D/stage" && rm -f "$D/SimpleMtkWlan-$WLAN_SHA.zip" && zip -q -r -X "$D/SimpleMtkWlan-$WLAN_SHA.zip" "SimpleMtkWlan-$WLAN_SHA" )
( cd "$D/src" && git archive --format=tar.gz --prefix="SimpleMtkWlan-$WLAN_SHA/" -o "$D/SimpleMtkWlan-src-$WLAN_SHA.tar.gz" "$WLAN_SHA" )
for f in "$D/SimpleMtkWlan-$WLAN_SHA.zip" "$D/SimpleMtkWlan-src-$WLAN_SHA.tar.gz"; do
  printf "%s\n  size=%s sha256=%s\n" "$(basename "$f")" "$(stat -f%z "$f")" "$(shasum -a 256 "$f" | awk '{print $1}')"
done
