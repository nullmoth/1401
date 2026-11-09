"""Is this EFI's Mac identity something Apple's services will accept? (iMessage, FaceTime, App Store, iCloud sign-in)

Apple's services look at five things a PC does not have in firmware, so the EFI has to supply them: the serial number
(SystemSerialNumber), the board serial (MLB), the hardware UUID, the ROM (a 6-byte value that a real Mac fills with its
primary network address) and a working NVRAM, plus an en0 interface that is marked built-in (policy.py handles that
last one for PCI Ethernet). The public references are OpenCore's Configuration.pdf (PlatformInfo) and the OpenCore
post-install guide "Fixing iServices".

Everything here is a pure function over a parsed config.plist, so it runs on a build, on a user's hand-made EFI
(efidoctor) and in tests without the engine. Nothing here talks to Apple, generates a serial, or reads another
machine's identity: it only says whether the values in the EFI are the placeholders the build tools write when
serial generation failed, the sample values from OpenCore's own example config, or malformed.
"""
import re
import uuid

# What the engine writes when macserial could not run (engine.PLACEHOLDER_SERIALS) and what OpenCore's own sample
# configuration ships. A Mac with one of these is every other Mac with it: Apple counts accounts per serial.
PLACEHOLDER_SERIALS = {"A" + "0" * 10 + "9", "A" + "0" * 15 + "Z"}
SAMPLE_SERIALS = {"W00000000001", "W00000000000", "M0000000000001", "M00000000000000000", "CCCCCCCCCCCC"}
SAMPLE_ROMS = {bytes.fromhex("112233445566"), bytes(6), bytes([0xFF] * 6)}

SERIAL_LENGTHS = (11, 12)       # 11 for 2009-2010 style serials, 12 for every Mac the installers accept today
MLB_LENGTHS = (13, 17)          # 13 for older boards, 17 for current ones
ALNUM = re.compile(r"^[A-Z0-9]+$")


def rom_bytes(value):
    """The ROM as bytes, from the bytes a plist holds or from 'aa:bb:cc:dd:ee:ff' / 'aabbccddeeff' text. None if neither."""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, str):
        hexed = re.sub(r"[^0-9A-Fa-f]", "", value)
        if len(hexed) == 12 and len(re.sub(r"[0-9A-Fa-f:\-. ]", "", value)) == 0:
            return bytes.fromhex(hexed)
    return None


def is_unicast(rom):
    """A network address is unicast when the lowest bit of its first byte is 0. A multicast ROM is not a valid address."""
    return len(rom) == 6 and (rom[0] & 1) == 0


def rom_from_mac(mac):
    """The ROM for a NIC's address, as OpenCore's guide advises for iServices. None when the text is not a unicast MAC."""
    rom = rom_bytes(mac)
    if rom is None or len(rom) != 6 or rom in SAMPLE_ROMS or not is_unicast(rom):
        return None
    return rom


def unicast_rom(rom):
    """The same ROM with the multicast bit cleared. Everything else about the value is kept."""
    return bytes([rom[0] & 0xFE]) + bytes(rom[1:])


def check(cfg, has_pci_ethernet=None):
    """Findings about the identity in a parsed config.plist: a list of (level, code, text).

    level is "problem" (Apple's services will refuse or mis-count this Mac) or "note" (works, with a limit the user
    should know). has_pci_ethernet is True/False when the scan is known, None when it is not (a hand-made EFI)."""
    out = []
    plat = (cfg or {}).get("PlatformInfo") or {}
    gen = plat.get("Generic") or {}

    def add(level, code, text):
        out.append((level, code, text))

    serial = str(gen.get("SystemSerialNumber") or "")
    if not serial:
        add("problem", "serial-empty", "SystemSerialNumber is empty: iCloud, iMessage and the App Store cannot sign in.")
    elif serial in PLACEHOLDER_SERIALS or serial in SAMPLE_SERIALS:
        add("problem", "serial-placeholder", f"The serial number {serial} is a placeholder, shared by every Mac that uses "
            "it. Rebuild so a real one is generated, then sign in to Apple services.")
    elif len(serial) not in SERIAL_LENGTHS or not ALNUM.match(serial):
        add("problem", "serial-shape", f"The serial number {serial!r} is not the shape of an Apple serial (11 or 12 letters "
            "and digits).")

    mlb = str(gen.get("MLB") or "")
    if not mlb:
        add("problem", "mlb-empty", "MLB (the board serial) is empty: iMessage and FaceTime cannot register.")
    elif mlb in PLACEHOLDER_SERIALS or mlb in SAMPLE_SERIALS:
        add("problem", "mlb-placeholder", f"The board serial {mlb} is a placeholder; rebuild so a real one is generated.")
    elif len(mlb) not in MLB_LENGTHS or not ALNUM.match(mlb):
        add("problem", "mlb-shape", f"The board serial {mlb!r} is not the shape of an Apple board serial (13 or 17 letters "
            "and digits).")

    raw_uuid = str(gen.get("SystemUUID") or "")
    try:
        parsed = uuid.UUID(raw_uuid)
    except ValueError:
        parsed = None
    if parsed is None:
        add("problem", "uuid-shape", f"SystemUUID {raw_uuid!r} is not a UUID.")
    elif parsed.int == 0:
        add("problem", "uuid-zero", "SystemUUID is all zeros, the same for every PC that left it unset.")

    rom = rom_bytes(gen.get("ROM"))
    if rom is None or len(rom) != 6:
        add("problem", "rom-shape", "ROM must be 6 bytes (a network address).")
    elif rom in SAMPLE_ROMS:
        add("problem", "rom-placeholder", "ROM is an example value (all zeros, all ones or 112233445566), the same on "
            "every PC that left it unset. Use the PC's own Ethernet address.")
    elif not is_unicast(rom):
        add("problem", "rom-multicast", "ROM has the multicast bit set, so it is not a valid network address. "
            "A rebuild writes a unicast one; a kept identity can be corrected with efidoctor --fix.")

    for key in ("Automatic", "UpdateDataHub", "UpdateNVRAM", "UpdateSMBIOS"):
        if key in plat and plat.get(key) is not True:
            add("problem", "update-" + key.lower(), f"PlatformInfo.{key} is off, so macOS never sees the identity "
                "(iServices reads it from the data hub and NVRAM).")

    # NVRAM that cannot be written cannot keep the sign-in tokens either. The AMD guard turns writes off and policy.py
    # then adds emulated NVRAM; a config with writes off and no emulation loses the Apple ID session at every restart.
    quirks = (cfg or {}).get("Booter", {}).get("Quirks", {}) or {}
    nvram = (cfg or {}).get("NVRAM", {}) or {}
    if quirks.get("DisableVariableWrite") and not nvram.get("LegacyEnable"):
        add("problem", "nvram-readonly", "NVRAM writes are blocked and no emulated NVRAM is on: the Apple ID, iMessage "
            "and FaceTime sign-in is forgotten at every restart.")

    props = ((cfg or {}).get("DeviceProperties") or {}).get("Add") or {}
    marked = [p for p, v in props.items() if isinstance(v, dict) and v.get("built-in") == b"\x01"]
    if has_pci_ethernet is False:
        add("note", "no-pci-ethernet", "This PC has no PCI Ethernet controller. Apple counts a Mac's accounts by en0, and "
            "without a built-in Ethernet controller en0 is whichever adapter macOS found first. iMessage and FaceTime "
            "may still work; if sign-in is refused, plug in a PCI or onboard Ethernet controller, or check `ifconfig en0` "
            "after setup.")
    elif has_pci_ethernet and not marked:
        add("problem", "ethernet-not-built-in", "A PCI Ethernet controller is present but none is marked built-in, so it "
            "may not be en0.")
    return out


def format_findings(findings):
    return [("note: " if lvl == "note" else "") + text for lvl, _code, text in findings]
