#!/usr/bin/env python3
"""ipa2mac: turn an unencrypted iPhone/iPad app (.ipa) into a Mac Catalyst app bundle for an Apple-silicon Mac, ready for
the ARM translator.

An .ipa is a zip holding Payload/<Name>.app, a flat bundle whose executable and frameworks are arm64 binaries stamped
for iOS. A Mac will not load that: dyld refuses an iOS-platform image, and UIKit lives under /System/iOSSupport on a
Mac. The route Apple's own tools take to make an iOS app run on a Mac (Mac Catalyst) is mechanical, and this does the
same steps to a finished binary:

  1. lay the flat bundle out as a Mac bundle: Contents/MacOS, Contents/Resources, Contents/Frameworks (frameworks
     become versioned bundles, which macOS code signing requires);
  2. stamp every Mach-O LC_BUILD_VERSION with platform 6 (Mac Catalyst); an old LC_VERSION_MIN_IPHONEOS becomes one;
  3. point every dependency on a framework that Mac Catalyst keeps under /System/iOSSupport at that path, and fix
     the @executable_path rpath for the deeper executable location;
  4. write a Mac Info.plist and sign ad hoc.

It refuses, with the reason, an app whose binary is FairPlay-encrypted (cryptid is not 0): that is the App Store's
copy protection, and removing it is not something this tool will do. Apps you built yourself, enterprise or ad hoc
builds, and open-source apps are unencrypted.

usage: ipa2mac.py <app.ipa> <output folder> [--no-sign]      exit 0 done, 2 refused (reason on stderr), 1 error
"""
import os
import plistlib
import shutil
import stat
import struct
import subprocess
import sys
import zipfile

IOS_SUPPORT_FRAMEWORKS = frozenset("""
_AdAttributionKit_StoreKit _AppIntents_SwiftUI _AppIntents_UIKit _AuthenticationServices_SwiftUI
_AVKit_SwiftUI _CoreLocationUI_SwiftUI _CoreNFC_UIKit _DeviceActivity_SwiftUI _GameController_SwiftUI
_GroupActivities_AppKit _GroupActivities_UIKit _HomeKit_SwiftUI _Intents_TipKit _LinkPresentation_AppIntents
_MapKit_SwiftUI _MusicKit_SwiftUI _PassKit_SwiftUI _PermissionKit_SwiftUI _PermissionKit_UIKit
_PhotosUI_SwiftUI _QuickLook_SwiftUI _RealityKit_SwiftUI _SceneKit_SwiftUI _SecureElementCredential_SwiftUI
_SecureElementCredential_UIKit _SpriteKit_SwiftUI _StoreKit_SwiftUI _SwiftData_SwiftUI _Translation_SwiftUI
_WebKit_SwiftUI AccessoryLiveActivities AccessoryNotifications AccessorySetupKit AccessoryTransportExtension
ActivityKit AdAttributionKit AddressBook AddressBookUI AlarmKit AppClip ARKit AssetsLibrary Assignables
AuthenticationServices AVKit BrowserKit BusinessChat CarPlay Charts Cinematic ClockKit ContactsUI CoreAudioKit
CoreLocationUI CoreNFC DeclaredAgeRange DeviceActivity EnergyKit EventKitUI ExtensionKit FamilyControls
FinanceKitUI GameController GameKit GameplayKit GameSave GroupActivities HealthKit HealthKitUI HomeKit iAd
IdentityDocumentServicesUI IdentityLookupUI ImagePlayground IntentsUI JavaScriptCore LinkPresentation
LockedCameraCapture ManagedSettingsUI MapKit MarketplaceKit MediaPlayer MediaSetup Messages MessageUI MetalKit
MobileCoreServices MultipeerConnectivity MusicKit NetworkExtensioniOSSupport OpenAL PaperKit PassKit PDFKit
PencilKit PermissionKit PhotosUI ProximityReader QuickLook RealityFoundation RealityKit ReplayKit RoomPlan
SafariServices SceneKit ScreenCaptureKit ScreenTime SecureElementCredential SharedWithYou Social SpriteKit
StoreKit SwiftData SwiftUI TipKit TouchController Twitter UIKit UserNotificationsUI VisionKit
WatchConnectivity WebKit WidgetKit
""".split())
IOS_SUPPORT_SWIFT = frozenset("""
ARKit AssetsLibrary CarPlay CoreNFC ExtensionKit GameplayKit HomeKit MapKit MediaPlayer MetalKit PassKit
PencilKit PhotosUI QuickLook SafariServices SceneKit SpriteKit UIKit
""".split())

# The frameworks Mac Catalyst links under /System/iOSSupport rather than /System/Library: the listing of
# System/iOSSupport/System/Library/Frameworks in the macOS 26.5 SDK (and its usr/lib/swift for the Swift overlays). The
# private ones are the three in that SDK's PrivateFrameworks folder.
IOS_SUPPORT_PRIVATE = frozenset(["MobileTimer", "PencilKit", "WebKit"])
PREFIX = "/System/iOSSupport"

MH_MAGIC_64, FAT_MAGIC = 0xFEEDFACF, 0xCAFEBABE
CPU_ARM64 = 0x0100000C
LC_SEGMENT_64, LC_BUILD_VERSION, LC_VERSION_MIN_IPHONEOS, LC_RPATH = 0x19, 0x32, 0x25, 0x8000001C
LC_ENCRYPTION_INFO, LC_ENCRYPTION_INFO_64 = 0x21, 0x2C
DYLIB_CMDS = {0xC, 0x80000018, 0x8000001F, 0x20, 0x80000023}
PLATFORM_IOS, PLATFORM_IOSSIMULATOR, PLATFORM_MACCATALYST = 2, 7, 6
MIN_CATALYST_OS = (13 << 16) | (1 << 8)          # iOS 13.1 is the first Catalyst
MAX_BYTES = 6 << 30
MAX_FILES = 200000


class Refused(Exception):
    """The app cannot be converted, and the message says why in words for the person who picked it."""


def remap_dylib(path):
    """The install name Mac Catalyst uses for a dependency that an iOS binary names, or the same name."""
    for root, names, suffix in (("/System/Library/Frameworks/", IOS_SUPPORT_FRAMEWORKS, ".framework/"),
                                ("/System/Library/PrivateFrameworks/", IOS_SUPPORT_PRIVATE, ".framework/")):
        if path.startswith(root):
            name = path[len(root):].split(".framework/")[0]
            if name in names and path[len(root) + len(name):].startswith(suffix):
                return PREFIX + path
    if path.startswith("/usr/lib/swift/libswift") and path.endswith(".dylib"):
        if path[len("/usr/lib/swift/libswift"):-len(".dylib")] in IOS_SUPPORT_SWIFT:
            return PREFIX + path
    return path


def _cstr(data, off):
    end = data.index(b"\0", off)
    return data[off:end].decode()


def _pad8(n):
    return (n + 7) & ~7


def convert_macho(data, name="binary"):
    """Returns the converted thin arm64 Mach-O (bytes). Raises Refused for anything it will not convert."""
    data = bytes(data)
    if len(data) < 32:
        raise Refused(f"{name} is not a program")
    magic = struct.unpack(">I", data[:4])[0]
    if magic == FAT_MAGIC:
        n = struct.unpack(">I", data[4:8])[0]
        pick = None
        for i in range(n):
            cpu, _sub, off, size, _al = struct.unpack(">iiIII", data[8 + 20 * i:28 + 20 * i])
            if cpu & 0xFFFFFFFF == CPU_ARM64:
                pick = (off, size)
        if pick is None:
            raise Refused(f"{name} has no arm64 part, so it is not an iPhone or iPad app")
        data = data[pick[0]:pick[0] + pick[1]]
    if struct.unpack("<I", data[:4])[0] != MH_MAGIC_64:
        raise Refused(f"{name} is not a 64-bit Mach-O program")
    cpu, _sub, filetype, ncmds, sizeofcmds, flags, reserved = struct.unpack("<iiIIIII", data[4:32])
    if cpu & 0xFFFFFFFF != CPU_ARM64:
        raise Refused(f"{name} is not an arm64 program: this tool converts iPhone and iPad apps")
    cmds, off, limit = [], 32, len(data)
    for _ in range(ncmds):
        cmd, size = struct.unpack("<II", data[off:off + 8])
        body = data[off:off + size]
        if cmd == LC_SEGMENT_64:
            nsects = struct.unpack("<I", body[64:68])[0]
            for s in range(nsects):
                soff = struct.unpack("<I", body[72 + 80 * s + 48:72 + 80 * s + 52])[0]
                if soff:
                    limit = min(limit, soff)
        cmds.append((cmd, body))
        off += size
    if off - 32 != sizeofcmds:
        raise Refused(f"{name}: the load commands do not add up")
    out, saw_platform = [], False
    for cmd, body in cmds:
        if cmd in (LC_ENCRYPTION_INFO, LC_ENCRYPTION_INFO_64):
            if struct.unpack("<I", body[16:20])[0] != 0:
                raise Refused(f"{name} is encrypted with the App Store's copy protection (FairPlay), which this tool "
                              "does not remove. Use an app you built yourself, or an enterprise, ad hoc or open-source build.")
        if cmd == LC_BUILD_VERSION:
            platform, minos, sdk, ntools = struct.unpack("<IIII", body[8:24])
            if platform == PLATFORM_IOSSIMULATOR:
                raise Refused(f"{name} is built for the iOS Simulator")
            if platform not in (PLATFORM_IOS, PLATFORM_MACCATALYST):
                raise Refused(f"{name} is not an iPhone or iPad app (platform {platform})")
            body = body[:8] + struct.pack("<IIII", PLATFORM_MACCATALYST, max(minos, MIN_CATALYST_OS), max(sdk, MIN_CATALYST_OS), ntools) + body[24:]
            saw_platform = True
        elif cmd == LC_VERSION_MIN_IPHONEOS:
            version, sdk = struct.unpack("<II", body[8:16])
            body = struct.pack("<IIIIII", LC_BUILD_VERSION, 24, PLATFORM_MACCATALYST, max(version, MIN_CATALYST_OS),
                               max(sdk, MIN_CATALYST_OS), 0)
            saw_platform = True
        elif cmd in DYLIB_CMDS:
            nameoff = struct.unpack("<I", body[8:12])[0]
            old = _cstr(body, nameoff)
            new = remap_dylib(old)
            if new != old:
                raw = new.encode() + b"\0"
                size = _pad8(nameoff + len(raw))
                body = struct.pack("<II", cmd, size) + body[8:nameoff] + raw + b"\0" * (size - nameoff - len(raw))
        elif cmd == LC_RPATH:
            nameoff = struct.unpack("<I", body[8:12])[0]
            old = _cstr(body, nameoff)
            if old == "@executable_path/Frameworks":
                new = "@executable_path/../Frameworks"
                raw = new.encode() + b"\0"
                size = _pad8(nameoff + len(raw))
                body = struct.pack("<II", cmd, size) + body[8:nameoff] + raw + b"\0" * (size - nameoff - len(raw))
        out.append(body)
    if not saw_platform:
        raise Refused(f"{name} carries no platform stamp, so it is not an iOS binary this tool can convert")
    new_cmds = b"".join(out)
    if 32 + len(new_cmds) > limit:
        raise Refused(f"{name} has no room in its header for the longer dependency paths "
                      f"({32 + len(new_cmds)} bytes needed, {limit} available)")
    if any(data[32 + sizeofcmds:limit]):
        raise Refused(f"{name}: the space after the load commands is not empty, so it cannot be used")
    head = struct.pack("<IiiIIIII", MH_MAGIC_64, cpu, _sub, filetype, len(out), len(new_cmds), flags, reserved)
    return head + new_cmds + b"\0" * (limit - 32 - len(new_cmds)) + data[limit:]


def is_macho(path):
    try:
        with open(path, "rb") as f:
            m = f.read(4)
    except OSError:
        return False
    return m in (struct.pack("<I", MH_MAGIC_64), struct.pack(">I", FAT_MAGIC))


def _safe_members(z):
    """Names of the Payload/<App>.app entries, checked: nothing outside the app, no links, bounded size."""
    infos = z.infolist()
    if len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_BYTES:
        raise Refused("the .ipa is larger than this tool will unpack")
    apps = {i.filename.split("/")[1] for i in infos if i.filename.startswith("Payload/") and i.filename.count("/") >= 2
            and i.filename.split("/")[1].endswith(".app")}
    if len(apps) != 1:
        raise Refused("the .ipa does not hold exactly one app in Payload/")
    for i in infos:
        n = i.filename
        parts = n.split("/")
        if n.startswith("/") or ".." in parts or "\\" in n or "\0" in n:
            raise Refused(f"the .ipa holds an unsafe path: {n!r}")
        if (i.external_attr >> 16) & 0o170000 == stat.S_IFLNK:
            raise Refused(f"the .ipa holds a symbolic link ({n}), which this tool does not unpack")
    return apps.pop(), [i for i in infos if i.filename.startswith("Payload/")]


def _write(path, data, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    os.chmod(path, mode)


def _versionize(fw_dir, binary_name):
    """Flat iOS framework -> versioned macOS framework bundle, in place."""
    ver = os.path.join(fw_dir, "Versions", "A")
    os.makedirs(os.path.join(ver, "Resources"))
    for item in sorted(os.listdir(fw_dir)):
        if item == "Versions":
            continue
        src = os.path.join(fw_dir, item)
        if item == binary_name:
            os.rename(src, os.path.join(ver, item))
        elif item == "Info.plist":
            os.rename(src, os.path.join(ver, "Resources", item))
        elif item == "_CodeSignature":
            shutil.rmtree(src)
        else:
            os.rename(src, os.path.join(ver, "Resources", item))
    os.symlink("A", os.path.join(fw_dir, "Versions", "Current"))
    os.symlink(os.path.join("Versions", "Current", binary_name), os.path.join(fw_dir, binary_name))
    os.symlink(os.path.join("Versions", "Current", "Resources"), os.path.join(fw_dir, "Resources"))


def mac_info_plist(info):
    info = dict(info)
    for key in ("LSRequiresIPhoneOS", "UIRequiredDeviceCapabilities", "DTPlatformVersion", "DTPlatformBuild", "DTSDKName",
                "DTSDKBuild", "MinimumOSVersion", "DTXcode", "DTXcodeBuild", "CFBundleSupportedPlatforms"):
        info.pop(key, None)
    info.update({"CFBundleSupportedPlatforms": ["MacOSX"], "DTPlatformName": "macosx", "LSMinimumSystemVersion": "15.0",
                 "CFBundlePackageType": "APPL"})
    return info


def convert(ipa, out_dir, sign=True, log=print):
    """Unpacks, converts and (optionally) signs. Returns the path of the .app made. Raises Refused."""
    with zipfile.ZipFile(ipa) as z:
        app_name, members = _safe_members(z)
        stage = os.path.join(out_dir, ".stage-" + str(os.getpid()))
        shutil.rmtree(stage, ignore_errors=True)
        try:
            for i in members:
                if i.is_dir():
                    continue
                rel = i.filename.split("/", 2)[2]
                mode = 0o755 if (i.external_attr >> 16) & 0o111 else 0o644
                _write(os.path.join(stage, rel), z.read(i), mode)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
    try:
        with open(os.path.join(stage, "Info.plist"), "rb") as f:
            info = plistlib.load(f)
        exe = info.get("CFBundleExecutable")
        if not exe or "/" in exe or not os.path.isfile(os.path.join(stage, exe)):
            raise Refused("the app has no executable named in its Info.plist")
        log("laying out the Mac bundle")
        name = app_name[:-4]
        app = os.path.join(out_dir, name + ".app")
        if os.path.exists(app):
            raise Refused(f"{app} already exists")
        try:
            return _lay_out(stage, info, exe, app, sign, log)
        except BaseException:
            shutil.rmtree(app, ignore_errors=True)
            raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def _lay_out(stage, info, exe, app, sign, log):
    contents = os.path.join(app, "Contents")
    os.makedirs(os.path.join(contents, "MacOS"))
    res = os.path.join(contents, "Resources")
    os.makedirs(res)
    macho = []
    for item in sorted(os.listdir(stage)):
        src = os.path.join(stage, item)
        if item == exe:
            os.rename(src, os.path.join(contents, "MacOS", exe))
            macho.append(os.path.join(contents, "MacOS", exe))
        elif item in ("Info.plist", "_CodeSignature", "embedded.mobileprovision", "PkgInfo"):
            continue
        elif item == "Frameworks":
            os.rename(src, os.path.join(contents, "Frameworks"))
        elif item == "PlugIns":
            os.rename(src, os.path.join(contents, "PlugIns"))
        else:
            os.rename(src, os.path.join(res, item))
    fwdir = os.path.join(contents, "Frameworks")
    if os.path.isdir(fwdir):
        for item in sorted(os.listdir(fwdir)):
            path = os.path.join(fwdir, item)
            if item.endswith(".framework") and os.path.isdir(path):
                with open(os.path.join(path, "Info.plist"), "rb") as f:
                    fexe = plistlib.load(f).get("CFBundleExecutable") or item[:-10]
                if os.path.isfile(os.path.join(path, fexe)):
                    _versionize(path, fexe)
                    macho.append(os.path.join(path, "Versions", "A", fexe))
            elif item.endswith(".dylib"):
                macho.append(path)
    if os.path.isdir(os.path.join(contents, "PlugIns")):
        raise Refused("this app has app extensions (PlugIns), which this tool does not convert yet")
    log(f"converting {len(macho)} program(s)")
    for path in macho:
        if not is_macho(path):
            raise Refused(f"{os.path.basename(path)} is not a Mach-O program")
        with open(path, "rb") as f:
            new = convert_macho(f.read(), os.path.basename(path))
        _write(path, new, 0o755)
    _write(os.path.join(contents, "Info.plist"), plistlib.dumps(mac_info_plist(info)))
    _write(os.path.join(contents, "PkgInfo"), b"APPL????")
    if sign:
        codesign = shutil.which("codesign") or "/usr/bin/codesign"
        if os.path.exists(codesign):
            log("signing")
            for path in reversed(macho):
                subprocess.run([codesign, "--force", "-s", "-", path], check=True, capture_output=True)
            for item in sorted(os.listdir(fwdir)) if os.path.isdir(fwdir) else []:
                if item.endswith(".framework"):
                    subprocess.run([codesign, "--force", "-s", "-", os.path.join(fwdir, item)], check=True, capture_output=True)
            subprocess.run([codesign, "--force", "-s", "-", app], check=True, capture_output=True)
        else:
            log("codesign is not available; the app is unsigned")
    return app


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        sys.stderr.write(__doc__.split("usage:")[1].strip() + "\n")
        return 1
    try:
        os.makedirs(args[1], exist_ok=True)
        print(convert(args[0], args[1], sign="--no-sign" not in argv))
        return 0
    except Refused as why:
        sys.stderr.write(f"not converted: {why}\n")
        return 2
    except (OSError, zipfile.BadZipFile, subprocess.CalledProcessError, KeyError, ValueError, plistlib.InvalidFileException) as err:
        sys.stderr.write(f"error: {type(err).__name__}: {err}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
