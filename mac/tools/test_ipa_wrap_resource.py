#!/usr/bin/env python3
"""The Mac app's copy of ipa2mac (Resources/nullmoth-ipa2mac.py) turns an unencrypted iOS app into a Mac Catalyst bundle. The arms build small arm64 Mach-O files and .ipa
archives in memory, so they run anywhere and need no Xcode."""
import io
import os
import plistlib
import struct
import sys
import tempfile
import unittest
import zipfile

import importlib.util
_spec = importlib.util.spec_from_file_location("nullmoth_ipa2mac", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Resources", "nullmoth-ipa2mac.py"))
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


def dylib_cmd(cmd, path):
    raw = path.encode() + b"\0"
    size = m._pad8(24 + len(raw))
    return struct.pack("<IIIIII", cmd, size, 24, 2, 0x10000, 0x10000) + raw + b"\0" * (size - 24 - len(raw))


def rpath_cmd(path):
    raw = path.encode() + b"\0"
    size = m._pad8(12 + len(raw))
    return struct.pack("<III", m.LC_RPATH, size, 12) + raw + b"\0" * (size - 12 - len(raw))


def make_macho(platform=2, dylibs=("/System/Library/Frameworks/UIKit.framework/UIKit",
                                   "/System/Library/Frameworks/Foundation.framework/Foundation",
                                   "/usr/lib/libSystem.B.dylib"),
               cryptid=None, old_min=False, rpath=None, text_offset=0x4000, cpu=m.CPU_ARM64, minos=(12 << 16)):
    seg = struct.pack("<II16sQQQQiiII", m.LC_SEGMENT_64, 72 + 80, b"__TEXT", 0, 0x4000, 0, 0x8000, 5, 5, 1, 0)
    sect = struct.pack("<16s16sQQIIIIIIII", b"__text", b"__TEXT", 0x1000, 8, text_offset, 2, 0, 0, 0x80000400, 0, 0, 0)
    cmds = [seg + sect]
    cmds += [dylib_cmd(0xC, d) for d in dylibs]
    if old_min:
        cmds.append(struct.pack("<IIII", m.LC_VERSION_MIN_IPHONEOS, 16, minos, minos))
    else:
        cmds.append(struct.pack("<IIIIII", m.LC_BUILD_VERSION, 24, platform, minos, minos, 0))
    if rpath:
        cmds.append(rpath_cmd(rpath))
    if cryptid is not None:
        cmds.append(struct.pack("<IIIIII", m.LC_ENCRYPTION_INFO_64, 24, 0x4000, 0x1000, cryptid, 0))
    blob = b"".join(cmds)
    head = struct.pack("<IiiIIIII", m.MH_MAGIC_64, cpu, 0, 2, len(cmds), len(blob), 0, 0)
    body = head + blob
    return body + b"\0" * (text_offset - len(body)) + b"\xAA" * 8 + b"\0" * 64


def load_cmds(data):
    ncmds = struct.unpack("<I", data[16:20])[0]
    off, out = 32, []
    for _ in range(ncmds):
        cmd, size = struct.unpack("<II", data[off:off + 8])
        out.append((cmd, data[off:off + size]))
        off += size
    return out


def names(data):
    out = []
    for cmd, body in load_cmds(data):
        if cmd in m.DYLIB_CMDS:
            out.append(m._cstr(body, struct.unpack("<I", body[8:12])[0]))
    return out


def platform_of(data):
    for cmd, body in load_cmds(data):
        if cmd == m.LC_BUILD_VERSION:
            return struct.unpack("<I", body[8:12])[0]


def make_ipa(path, exe=b"", info=None, frameworks=True, extra=None):
    info = info or {"CFBundleExecutable": "Demo", "CFBundleIdentifier": "com.example.demo", "CFBundleName": "Demo",
                    "MinimumOSVersion": "13.0", "LSRequiresIPhoneOS": True, "UIDeviceFamily": [1, 2]}
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Payload/Demo.app/Demo", exe or make_macho())
        z.writestr("Payload/Demo.app/Info.plist", plistlib.dumps(info))
        z.writestr("Payload/Demo.app/Assets.car", b"assets")
        z.writestr("Payload/Demo.app/_CodeSignature/CodeResources", b"sig")
        if frameworks:
            z.writestr("Payload/Demo.app/Frameworks/Lib.framework/Lib", make_macho(rpath="@loader_path/Frameworks"))
            z.writestr("Payload/Demo.app/Frameworks/Lib.framework/Info.plist", plistlib.dumps({"CFBundleExecutable": "Lib"}))
        for k, v in (extra or {}).items():
            z.writestr(k, v)


class Macho(unittest.TestCase):
    def test_an_ios_binary_becomes_a_catalyst_binary(self):
        out = m.convert_macho(make_macho())
        self.assertEqual(platform_of(out), m.PLATFORM_MACCATALYST)

    def test_catalyst_minimum_os_is_never_below_ios_13_1(self):
        out = m.convert_macho(make_macho(minos=12 << 16))
        for cmd, body in load_cmds(out):
            if cmd == m.LC_BUILD_VERSION:
                self.assertEqual(struct.unpack("<I", body[12:16])[0], m.MIN_CATALYST_OS)

    def test_uikit_moves_under_iossupport_and_foundation_and_libsystem_stay(self):
        out = names(m.convert_macho(make_macho()))
        self.assertEqual(out, ["/System/iOSSupport/System/Library/Frameworks/UIKit.framework/UIKit",
                               "/System/Library/Frameworks/Foundation.framework/Foundation", "/usr/lib/libSystem.B.dylib"])

    def test_the_swift_overlay_and_a_private_framework_move_too(self):
        out = names(m.convert_macho(make_macho(dylibs=("/usr/lib/swift/libswiftUIKit.dylib", "/usr/lib/swift/libswiftCore.dylib",
                                                       "/System/Library/PrivateFrameworks/PencilKit.framework/PencilKit"))))
        self.assertEqual(out, ["/System/iOSSupport/usr/lib/swift/libswiftUIKit.dylib", "/usr/lib/swift/libswiftCore.dylib",
                               "/System/iOSSupport/System/Library/PrivateFrameworks/PencilKit.framework/PencilKit"])

    def test_a_framework_whose_name_only_starts_like_a_listed_one_is_left_alone(self):
        self.assertEqual(m.remap_dylib("/System/Library/Frameworks/UIKitFoo.framework/UIKitFoo"),
                         "/System/Library/Frameworks/UIKitFoo.framework/UIKitFoo")

    def test_the_executable_rpath_is_fixed_for_the_deeper_location(self):
        out = m.convert_macho(make_macho(rpath="@executable_path/Frameworks"))
        paths = [m._cstr(b, struct.unpack("<I", b[8:12])[0]) for c, b in load_cmds(out) if c == m.LC_RPATH]
        self.assertEqual(paths, ["@executable_path/../Frameworks"])

    def test_an_old_style_version_command_becomes_a_build_version(self):
        out = m.convert_macho(make_macho(old_min=True))
        self.assertEqual(platform_of(out), m.PLATFORM_MACCATALYST)
        self.assertNotIn(m.LC_VERSION_MIN_IPHONEOS, [c for c, _ in load_cmds(out)])

    def test_code_after_the_header_is_untouched(self):
        src = make_macho()
        out = m.convert_macho(src)
        self.assertEqual(out[0x4000:], src[0x4000:])
        self.assertEqual(len(out), len(src))

    def test_a_fairplay_encrypted_binary_is_refused_and_an_unencrypted_one_is_not(self):
        with self.assertRaises(m.Refused) as r:
            m.convert_macho(make_macho(cryptid=1))
        self.assertIn("copy protection", str(r.exception))
        m.convert_macho(make_macho(cryptid=0))

    def test_a_simulator_binary_and_an_intel_binary_are_refused(self):
        with self.assertRaises(m.Refused):
            m.convert_macho(make_macho(platform=m.PLATFORM_IOSSIMULATOR))
        with self.assertRaises(m.Refused):
            m.convert_macho(make_macho(cpu=0x01000007))

    def test_no_room_in_the_header_fails_loudly_instead_of_corrupting(self):
        tight = make_macho(text_offset=0x4000)
        used = 32 + struct.unpack("<I", tight[20:24])[0]
        with self.assertRaises(m.Refused) as r:
            m.convert_macho(make_macho(text_offset=used + 8))
        self.assertIn("no room", str(r.exception))
        m.convert_macho(make_macho(text_offset=used + 64))

    def test_a_fat_file_is_reduced_to_its_arm64_part(self):
        thin = make_macho()
        fat = struct.pack(">II", m.FAT_MAGIC, 2) + struct.pack(">iiIII", 0x01000007, 3, 0x1000, 8, 12) \
            + struct.pack(">iiIII", m.CPU_ARM64, 0, 0x2000, len(thin), 14)
        fat = fat + b"\0" * (0x1000 - len(fat)) + b"x" * 8 + b"\0" * (0x2000 - 0x1008) + thin
        self.assertEqual(platform_of(m.convert_macho(fat)), m.PLATFORM_MACCATALYST)


class Bundle(unittest.TestCase):
    def convert(self, **kw):
        d = tempfile.mkdtemp()
        ipa = os.path.join(d, "Demo.ipa")
        make_ipa(ipa, **kw)
        return m.convert(ipa, os.path.join(d, "out"), sign=False, log=lambda *_: None)

    def test_the_bundle_has_the_mac_layout(self):
        app = self.convert()
        self.assertTrue(os.path.isfile(os.path.join(app, "Contents", "MacOS", "Demo")))
        self.assertTrue(os.path.isfile(os.path.join(app, "Contents", "Resources", "Assets.car")))
        self.assertFalse(os.path.exists(os.path.join(app, "Contents", "_CodeSignature")))
        fw = os.path.join(app, "Contents", "Frameworks", "Lib.framework")
        self.assertTrue(os.path.isfile(os.path.join(fw, "Versions", "A", "Lib")))
        self.assertTrue(os.path.islink(os.path.join(fw, "Lib")))
        self.assertTrue(os.path.isfile(os.path.join(fw, "Versions", "A", "Resources", "Info.plist")))

    def test_every_program_in_the_bundle_is_stamped_catalyst(self):
        app = self.convert()
        for rel in ("Contents/MacOS/Demo", "Contents/Frameworks/Lib.framework/Versions/A/Lib"):
            with open(os.path.join(app, rel), "rb") as f:
                self.assertEqual(platform_of(f.read()), m.PLATFORM_MACCATALYST, rel)

    def test_the_info_plist_is_a_mac_one(self):
        app = self.convert()
        with open(os.path.join(app, "Contents", "Info.plist"), "rb") as f:
            info = plistlib.load(f)
        self.assertNotIn("LSRequiresIPhoneOS", info)
        self.assertEqual(info["CFBundleSupportedPlatforms"], ["MacOSX"])
        self.assertEqual(info["CFBundleExecutable"], "Demo")

    def test_an_encrypted_app_is_refused_and_leaves_no_bundle(self):
        d = tempfile.mkdtemp()
        make_ipa(os.path.join(d, "a.ipa"), exe=make_macho(cryptid=1))
        with self.assertRaises(m.Refused):
            m.convert(os.path.join(d, "a.ipa"), os.path.join(d, "out"), sign=False, log=lambda *_: None)
        self.assertFalse(any(n.endswith(".app") for n in os.listdir(os.path.join(d, "out"))))

    def test_a_zip_with_a_path_that_escapes_is_refused(self):
        d = tempfile.mkdtemp()
        make_ipa(os.path.join(d, "a.ipa"), extra={"Payload/Demo.app/../../evil": b"x"})
        with self.assertRaises(m.Refused):
            m.convert(os.path.join(d, "a.ipa"), os.path.join(d, "out"), sign=False, log=lambda *_: None)
        self.assertFalse(os.path.exists(os.path.join(d, "evil")))

    def test_an_app_with_extensions_is_refused_with_the_reason(self):
        d = tempfile.mkdtemp()
        make_ipa(os.path.join(d, "a.ipa"), extra={"Payload/Demo.app/PlugIns/W.appex/W": make_macho()})
        with self.assertRaises(m.Refused) as r:
            m.convert(os.path.join(d, "a.ipa"), os.path.join(d, "out"), sign=False, log=lambda *_: None)
        self.assertIn("extensions", str(r.exception))

    def test_the_command_line_exits_2_with_the_reason_for_a_refusal(self):
        d = tempfile.mkdtemp()
        make_ipa(os.path.join(d, "a.ipa"), exe=make_macho(cryptid=1))
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Resources", "nullmoth-ipa2mac.py"),
                            os.path.join(d, "a.ipa"), os.path.join(d, "out"), "--no-sign"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("not converted", r.stderr)


if __name__ == "__main__":
    unittest.main()
