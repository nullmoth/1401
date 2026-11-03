#!/usr/bin/env python3
"""hardware_map_parse_check.py: the parse rules HardwareMap.cs implements, checked against real Windows
hardware identifiers before the C# is ever compiled. The Windows app builds on a PC; this runs anywhere, so
a parsing mistake does not have to wait for a build to be found.

It mirrors the patterns and the masks in HardwareMap.cs. If that file's patterns change, change these with
them - this is a check of the RULES, not of the binary, and it says so rather than implying coverage it does
not have. In particular it does NOT prove the file compiles, that WMI answers, or that any field is present
on real hardware.

Several arms are calibrated against identifiers taken from reports users actually sent (the Realtek
ALC256 codec 10EC:0256 and the NVIDIA audio functions 10DE:10F8/22BD among them), so a pattern that
matches nothing real fails here rather than in the field.

    python3 hardware_map_parse_check.py
"""
import re
import sys

ACPI_SHAPE = re.compile(r"^(?:PNP[0-9A-F]{4}|ACPI[0-9A-F]{4}|[A-Z]{3}[0-9A-F]{4}|[A-Z]{4}[0-9A-F]{4})$")
PCI = re.compile(r"^PCI\\VEN_(?P<ven>[0-9A-F]{4})&DEV_(?P<dev>[0-9A-F]{4})"
                 r"(?:&SUBSYS_(?P<sub>[0-9A-F]{8}))?(?:&REV_(?P<rev>[0-9A-F]{2}))?")
USB = re.compile(r"^USB\\VID_(?P<ven>[0-9A-F]{4})&PID_(?P<dev>[0-9A-F]{4})"
                 r"(?:&REV_(?P<rev>[0-9A-F]{4}))?(?:&MI_(?P<mi>[0-9A-F]{2}))?")
HID = re.compile(r"^HID\\VID_(?P<ven>[0-9A-F]{4})&PID_(?P<dev>[0-9A-F]{4})")
HDAUDIO = re.compile(r"^HDAUDIO\\(?:FUNC_(?P<func>[0-9A-F]{2})&)?VEN_(?P<ven>[0-9A-F]{4})&DEV_(?P<dev>[0-9A-F]{4})"
                     r"(?:&SUBSYS_(?P<sub>[0-9A-F]{8}))?(?:&REV_(?P<rev>[0-9A-F]{4}))?")
PCI_CLASS = re.compile(r"^PCI\\(?:VEN_[0-9A-F]{4}&)?CC_(?P<cc>[0-9A-F]{4}(?:[0-9A-F]{2})?)$")
USB_CLASS = re.compile(r"^USB\\(?:DEV)?CLASS_(?P<cls>[0-9A-F]{2})"
                       r"(?:&SUBCLASS_(?P<sub>[0-9A-F]{2}))?(?:&PROT_(?P<prot>[0-9A-F]{2}))?$")
HID_USAGE = re.compile(r"^HID_DEVICE_UP:(?P<page>[0-9A-F]{4})_U:(?P<usage>[0-9A-F]{4})$")


def facts(pnp_device_id):
    """The identifier numbers of one device. The instance segment is never examined."""
    if not pnp_device_id:
        return {}
    text = pnp_device_id.upper()
    m = PCI.match(text)
    if m:
        out = {"pci_vendor": int(m.group("ven"), 16) & 0xFFFF,
               "pci_device": int(m.group("dev"), 16) & 0xFFFF}
        if m.group("sub"):
            packed = int(m.group("sub"), 16)
            out["pci_subsystem_device"] = (packed >> 16) & 0xFFFF
            out["pci_subsystem_vendor"] = packed & 0xFFFF
        if m.group("rev"):
            out["pci_revision"] = int(m.group("rev"), 16) & 0xFF
        return out
    m = HDAUDIO.match(text)
    if m:
        out = {"audio_codec_vendor_device":
               ((int(m.group("ven"), 16) & 0xFFFF) << 16) | (int(m.group("dev"), 16) & 0xFFFF)}
        if m.group("rev"):
            out["audio_codec_revision"] = int(m.group("rev"), 16) & 0xFFFFFFFF
        if m.group("func"):
            out["audio_codec_function_group"] = int(m.group("func"), 16) & 0xFF
        return out
    m = USB.match(text)
    if m:
        out = {"usb_vendor": int(m.group("ven"), 16) & 0xFFFF,
               "usb_product": int(m.group("dev"), 16) & 0xFFFF}
        if m.group("mi"):
            out["usb_interface_number"] = int(m.group("mi"), 16) & 0xFF
        return out
    m = HID.match(text)
    if m:
        return {"hid_vendor": int(m.group("ven"), 16) & 0xFFFF,
                "hid_product": int(m.group("dev"), 16) & 0xFFFF}
    return {}


def classes(compatible_ids):
    """The class, subclass and usage numbers, which Windows states in the CompatibleID list."""
    out = {}
    for raw in compatible_ids or []:
        if not raw or len(raw) > 256:
            continue
        text = raw.upper()
        m = PCI_CLASS.match(text)
        if m:
            digits = m.group("cc")
            value = int(digits, 16)
            code = ((value & 0xFFFF) << 8) if len(digits) == 4 else (value & 0xFFFFFF)
            # The widest statement wins: CC_040300 says more than CC_0403.
            if code > out.get("pci_class", -1):
                out["pci_class"] = code
            continue
        m = USB_CLASS.match(text)
        if m:
            out["usb_class"] = int(m.group("cls"), 16) & 0xFF
            if m.group("sub"):
                out["usb_subclass"] = int(m.group("sub"), 16) & 0xFF
            if m.group("prot"):
                out["usb_protocol"] = int(m.group("prot"), 16) & 0xFF
            continue
        m = HID_USAGE.match(text)
        if m:
            out["hid_usage_page"] = int(m.group("page"), 16) & 0xFFFF
            out["hid_usage"] = int(m.group("usage"), 16) & 0xFFFF
    return out


def acpi_ids(compatible_ids):
    kept = set()
    for raw in compatible_ids or []:
        if not raw or len(raw) > 256:
            continue
        text = raw.upper()
        cut = max(text.rfind("\\"), text.rfind("*"))
        if cut >= 0:
            text = text[cut + 1:]
        if ACPI_SHAPE.match(text):
            kept.add(text)
    return sorted(kept)


def merged(device_id, compatible_ids):
    """What Collect() writes for one device: the hardware-ID facts, plus any class number the hardware ID
    did not already state."""
    out = facts(device_id)
    for key, value in classes(compatible_ids).items():
        out.setdefault(key, value)
    return out


def line(fields, acpi):
    """Line() in HardwareMap.cs: field names in order, so two maps of one PC are the same text."""
    text = "device"
    for name in sorted(fields):
        text += " %s=%d" % (name, fields[name])
    if acpi:
        text += " acpi_ids=" + ",".join(acpi)
    return text


ARMS = []


def arm(name):
    def take(fn):
        ARMS.append((name, fn))
        return fn
    return take


@arm("an RTX 5060's PCI id gives vendor, device, both subsystem halves and the revision")
def _():
    # NVIDIA 0x10DE, and SUBSYS packs device in the high half: 0x1234 device, 0x10DE vendor
    got = facts(r"PCI\VEN_10DE&DEV_2503&SUBSYS_123410DE&REV_A1\4&1a2b3c4d&0&0008")
    assert got == {"pci_vendor": 0x10DE, "pci_device": 0x2503, "pci_subsystem_device": 0x1234,
                   "pci_subsystem_vendor": 0x10DE, "pci_revision": 0xA1}, got


@arm("a PCI id with no SUBSYS or REV gives only what is there, and invents neither")
def _():
    got = facts(r"PCI\VEN_8086&DEV_A70D")
    assert got == {"pci_vendor": 0x8086, "pci_device": 0xA70D}, got


@arm("THE ONE THAT MATTERS: a USB instance segment is a serial number and must not appear anywhere")
def _():
    # The third segment of a USB PNPDeviceID is frequently the device's serial.
    serial = "0123456789ABCDEF"
    got = facts(r"USB\VID_046D&PID_C52B\6&" + serial + r"&0&2")
    assert got == {"usb_vendor": 0x046D, "usb_product": 0xC52B}, got
    for key, value in got.items():
        assert serial not in str(value), (key, value)
        assert serial.lower() not in str(value).lower(), (key, value)


@arm("the same holds for the newer patterns: no HDAUDIO or interface instance tail reaches a field")
def _():
    serial = "4C530001ABCDEF"
    for ident in [r"HDAUDIO\FUNC_01&VEN_10EC&DEV_0256&SUBSYS_10EC0256&REV_1001\5&" + serial + r"&0&0001",
                  r"USB\VID_046D&PID_C52B&MI_01\8&" + serial + r"&0&0000",
                  r"HID\VID_046D&PID_C52B&MI_01\8&" + serial + r"&0&0000"]:
        got = facts(ident)
        assert got, ident                              # it must still parse the legitimate prefix
        for key, value in got.items():
            # every emitted value is an integer whose hex form is one of the captured fields, never a
            # fragment of the instance path
            assert isinstance(value, int), (ident, key, value)
            assert serial not in ("%X" % value), (ident, key, value)


@arm("a HID id gives the HID vendor and product, not the USB ones")
def _():
    got = facts(r"HID\VID_046D&PID_C52B&MI_01\8&1a2b3c4d&0&0000")
    assert got == {"hid_vendor": 0x046D, "hid_product": 0xC52B}, got


@arm("a USB interface id gives its interface number from MI_, which is part of the ID, not the instance")
def _():
    got = facts(r"USB\VID_8087&PID_0A2B&MI_03\7&abcd1234&0&0003")
    assert got == {"usb_vendor": 0x8087, "usb_product": 0x0A2B, "usb_interface_number": 3}, got


@arm("a root or software device carries no identifier and is counted, not listed")
def _():
    assert facts(r"ROOT\SYSTEM\0000") == {}
    assert facts(r"SWD\PRINTENUM\{0A2B...}") == {}
    assert facts("") == {}
    assert facts(None) == {}


@arm("lower-case identifiers parse the same: Windows is not consistent about case")
def _():
    assert facts(r"pci\ven_10de&dev_2503") == {"pci_vendor": 0x10DE, "pci_device": 0x2503}
    assert facts(r"hdaudio\func_01&ven_10ec&dev_0256")["audio_codec_vendor_device"] == 0x10EC0256


@arm("ACPI ids keep the real shapes and drop everything else")
def _():
    got = acpi_ids([r"ACPI\PNP0A08", "*PNP0C02", r"ACPI\INT34C5", "USB\\CLASS_09",
                    "NOT_AN_ID", "x" * 300, None, ""])
    assert got == ["INT34C5", "PNP0A08", "PNP0C02"], got


@arm("a vendor string that merely looks ACPI-ish is refused")
def _():
    assert acpi_ids(["PNP0A0"]) == []          # too short
    assert acpi_ids(["PNP0A088"]) == []        # too long
    assert acpi_ids(["pnp0a08"]) == ["PNP0A08"]  # case is normalised, shape still checked


@arm("CALIBRATED ON A REAL REPORT: an ALC256 codec id gives the vendor/device pair the Mac app reports")
def _():
    # 10EC:0256 is the codec a user's own report named beside "codecs 10EC:0256". The Mac app reads it as
    # one 32-bit IOHDACodecVendorID, so the two maps must agree on the packing.
    got = facts(r"HDAUDIO\FUNC_01&VEN_10EC&DEV_0256&SUBSYS_10EC0256&REV_1001\4&1a2b3c4d&0&0001")
    assert got["audio_codec_vendor_device"] == 0x10EC0256, got
    assert got["audio_codec_revision"] == 0x1001, got
    assert got["audio_codec_function_group"] == 0x01, got
    # the field the Mac app prints, rebuilt from our number, must read back as the same pair
    v, d = got["audio_codec_vendor_device"] >> 16, got["audio_codec_vendor_device"] & 0xFFFF
    assert "%04X:%04X" % (v, d) == "10EC:0256"


@arm("CALIBRATED ON A REAL REPORT: an NVIDIA audio function reads as an HD-audio controller")
def _():
    # 10DE:10F8 and 10DE:22BD are the NVIDIA audio functions in users' reports. The Mac app decides
    # "this is a sound controller" with (class-code >> 8) == 0x0403; the Windows map must give a
    # pci_class that answers the same question, or the two maps cannot be compared on audio at all.
    # The CompatibleID forms are Microsoft's documented ones for a PCI device: the class code follows the
    # vendor or stands alone, and never follows DEV_. Writing a DEV_&CC_ fixture here is how this arm first
    # failed - the pattern was right and the test data was invented.
    for device, compat in [(0x10F8, [r"PCI\VEN_10DE&CC_040300", r"PCI\VEN_10DE&CC_0403"]),
                           (0x22BD, [r"PCI\CC_040300", r"PCI\CC_0403"])]:
        got = merged(r"PCI\VEN_10DE&DEV_%04X&SUBSYS_000010DE&REV_A1\3&11583659&0&09" % device, compat)
        assert got["pci_device"] == device, got
        assert got["pci_class"] == 0x040300, got
        assert (got["pci_class"] >> 8) == 0x0403, got


@arm("a four-digit class code is widened to the Mac app's 24-bit field, and six digits win over four")
def _():
    assert classes([r"PCI\CC_0403"]) == {"pci_class": 0x040300}
    assert classes([r"PCI\CC_0C03"]) == {"pci_class": 0x0C0300}
    # both forms present, in either order: the specific one is kept
    assert classes([r"PCI\CC_0C0330", r"PCI\CC_0C03"]) == {"pci_class": 0x0C0330}
    assert classes([r"PCI\CC_0C03", r"PCI\CC_0C0330"]) == {"pci_class": 0x0C0330}


@arm("a USB keyboard interface gives class, subclass and protocol; a HID collection gives its usage")
def _():
    assert classes([r"USB\Class_03&SubClass_01&Prot_01"]) == {
        "usb_class": 3, "usb_subclass": 1, "usb_protocol": 1}
    assert classes([r"USB\Class_09"]) == {"usb_class": 9}          # a hub, no subclass stated
    assert classes(["HID_DEVICE_UP:000C_U:0001"]) == {"hid_usage_page": 0x0C, "hid_usage": 1}
    assert classes(["HID_DEVICE_SYSTEM_KEYBOARD", "HID_DEVICE"]) == {}   # named, not numbered: nothing


@arm("NEGATIVE CONTROL THAT MUST FIRE: a near-miss class string yields nothing, not a wrong number")
def _():
    # Each of these is one character away from a shape we accept. The patterns are anchored at both ends
    # for exactly this reason: a partial match would put a number in the map that is not the device's.
    for hostile in [r"PCI\VEN_10DE&CC_04030", r"PCI\CC_04030012", r"USB\Class_3&SubClass_01",
                    r"USB\Class_03&Something", "HID_DEVICE_UP:000C", "HID_DEVICE_UP:000C_U:1",
                    r"PCI\VEN_10DE&CC_SECRET", r"USB\Class_03\6&1a2b3c4d&0&2"]:
        got = classes([hostile])
        assert got == {}, (hostile, got)
    # and the arm proves itself: the real forms of the same strings DO produce numbers
    assert classes([r"PCI\VEN_10DE&CC_040300"]) == {"pci_class": 0x040300}
    assert classes([r"USB\Class_03&SubClass_01"]) == {"usb_class": 3, "usb_subclass": 1}
    assert classes(["HID_DEVICE_UP:000C_U:0001"]) != {}


@arm("NEGATIVE CONTROL THAT MUST FIRE: a DeviceID handed to the class reader yields nothing")
def _():
    # Collect() passes only CompatibleID lists to classes() and acpi_ids(); taking the last segment is
    # safe for exactly that reason. If a later change ever fed a DeviceID in, these are the strings whose
    # instance tails must still produce no field.
    for device_id in [r"USB\VID_046D&PID_C52B\6&1a2b3c4d&0&2",
                      r"HDAUDIO\FUNC_01&VEN_10EC&DEV_0256\4&1a2b3c4d&0&0001",
                      r"USBSTOR\DISK&VEN_KINGSTON&PROD_DATATRAVELER_3.0&REV_0000\E0D55EA574B315C108820075&0"]:
        assert classes([device_id]) == {}, device_id
        assert acpi_ids([device_id]) == [], device_id


@arm("NEGATIVE CONTROL: a friendly name, a MAC address or a path can never become a field")
def _():
    # These are the strings the allow-list exists to keep out. None of them is an identifier shape, so
    # every one must produce nothing. If this arm ever passes trivially because facts() started returning
    # a catch-all, the assertion on an empty dict below is what fails.
    # The fixtures are deliberately reserved-for-documentation values (RFC 5737 for the address, the
    # IANA documentation range for the MAC) and a made-up device name. A test that needs to prove a
    # real address cannot leak must not carry one to do it.
    for hostile in ["My Keyboard", "00:00:5E:00:53:01", r"PCI\VEN_10DE&DEV_2503&SERIAL_SECRET",
                    "C:\\Users\\someone", "192.0.2.10", "DESKTOP-ABCD1234"]:
        got = facts(hostile)
        assert "serial" not in " ".join(got.keys()).lower(), got
        for value in got.values():
            assert isinstance(value, int), (hostile, got)
    assert facts("My Keyboard") == {}
    assert facts("00:00:5E:00:53:01") == {}
    assert facts("192.0.2.10") == {}
    # the SERIAL_ case above still parses its legitimate VEN/DEV prefix, and nothing more
    assert facts(r"PCI\VEN_10DE&DEV_2503&SERIAL_SECRET") == {"pci_vendor": 0x10DE, "pci_device": 0x2503}


@arm("a device line is field-name sorted, so two maps of one PC are the same text and can be diffed")
def _():
    fields = merged(r"PCI\VEN_10DE&DEV_10F8&SUBSYS_000010DE&REV_A1",
                    [r"PCI\VEN_10DE&CC_040300"])
    text = line(fields, ["PNP0A08"])
    # 262912 is 0x040300 in the decimal the map writes; the literal here was 0x040500 at first and this
    # arm is what said so.
    assert text == ("device pci_class=262912 pci_device=4344 pci_revision=161 "
                    "pci_subsystem_device=0 pci_subsystem_vendor=4318 pci_vendor=4318 "
                    "acpi_ids=PNP0A08"), text
    # the same facts in a different dict order give the identical line
    shuffled = dict(reversed(list(fields.items())))
    assert line(shuffled, ["PNP0A08"]) == text


@arm("a class number never overwrites a hardware-ID number of the same name")
def _():
    # Collect() merges with setdefault for this reason: the hardware ID is the device's own statement.
    got = merged(r"PCI\VEN_10DE&DEV_10F8&REV_A1", [r"PCI\VEN_10DE&CC_040300"])
    assert got["pci_revision"] == 0xA1 and got["pci_class"] == 0x040300, got


@arm("the PCI class pattern accepts exactly Microsoft's documented CompatibleID forms, and no others")
def _():
    # "Identifiers for PCI Devices": the compatible IDs are PCI\VEN_v&CC_ccsspp, PCI\VEN_v&CC_ccss,
    # PCI\CC_ccsspp and PCI\CC_ccss. DEV_ appears in the HARDWARE ids, never in front of CC_.
    for good in [r"PCI\VEN_10DE&CC_040300", r"PCI\VEN_10DE&CC_0403", r"PCI\CC_040300", r"PCI\CC_0403"]:
        assert classes([good]) == {"pci_class": 0x040300}, good
    for not_a_class_id in [r"PCI\VEN_10DE&DEV_10F8&CC_040300", r"PCI\VEN_10DE&DEV_10F8&REV_A1",
                           r"PCI\VEN_10DE&DEV_10F8"]:
        assert classes([not_a_class_id]) == {}, not_a_class_id


def main():
    bad = 0
    for name, fn in ARMS:
        try:
            fn()
            print("  ok   " + name)
        except AssertionError as error:
            bad += 1
            print("  FAIL " + name + "\n       " + str(error))
    print("\n%d arm(s), %d failed" % (len(ARMS), bad))
    print("This checks the PARSE RULES only. It does not compile HardwareMap.cs (there is no .NET "
          "toolchain on the machine it was written on), does not call WMI, and proves nothing about "
          "which fields real hardware reports.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
