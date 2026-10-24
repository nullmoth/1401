"""Community drivers 1401 adds for hardware the engine has no driver for.

Each entry is one released file from its author, pinned by URL, size and SHA-256 (the engine refuses any other bytes),
under a licence that lets 1401 use it (p1401/licenses.json; tests/test_licenses.py checks every URL here). An entry is
added only when the scan shows a device its Info.plist actually matches, and only for the macOS versions its author
built it for. Device IDs the engine already drives are left to the engine, so nothing that works today is replaced.

Two kinds of gate, the same split netsupport.py uses:
- experimental=True: the driver can cost the machine its network, its power behaviour or its boot (a Wi-Fi driver, a
  power plugin, a firmware memory-map change). Added only when the user turns on "Include experimental drivers";
  otherwise the build names the driver and how to ask for it.
- experimental=False: firmware loaders and codeless kexts that only bind a device nothing else drives (Bluetooth
  firmware, an I2C controller ID for VoodooI2C, a keyboard interface). They cannot cost the display or the network.

kexts go through the engine's own download (kext_data.KextInfo with download_info); UEFI drivers are fetched here,
checked the same way, and written into EFI/OC/Drivers after the engine has built the EFI."""
import hashlib
import io
import os
import plistlib
import zipfile

SEQUOIA, TAHOE = 24, 25

DRIVERS = [
    {   # Realtek Wi-Fi 6/6E/7 (RTW89) and the RTW88 cards the engine has no driver for, native Wi-Fi menu
        "name": "AirportRTW", "repo": "souissiak1-maker/AirportRTW", "section": "Network", "experimental": True,
        "ids": ["10EC-8852", "10EC-A85A", "10EC-B852", "10EC-B85B", "10EC-B851", "10EC-B520", "10EC-C852",
                "10EC-8922", "10EC-892B", "10EC-C82F", "10EC-B821", "10EC-D723"],
        "requires": ["AMFIPass"],
        "builds": {
            SEQUOIA: ("https://github.com/souissiak1-maker/AirportRTW/releases/download/V2.1.0/AirportRTW-Sequoia-Release.zip",
                      20187077, "1e6b5daf388968d5af42a26b51b71a1b1019bd9229efe08474d3d4f26931d1b7"),
            TAHOE: ("https://github.com/souissiak1-maker/AirportRTW/releases/download/V2.1.0/AirportRTW-Tahoe-Release.zip",
                    20187579, "3c5b6a31d23d088826614d54267bdc9f33137b1e8a67df9b38a94ef558ea6ed1"),
        },
        "what": "Realtek Wi-Fi (AirportRTW 2.1.0, native Wi-Fi menu)",
    },
    {   # MediaTek MT7921 / MT7922 / RZ616 on Tahoe: the native Wi-Fi menu (Sequoia keeps netsupport.py's build)
        "name": "AirportMtkWlan", "repo": "flxxxxddd/SimpleMtkWlan", "section": "Network", "experimental": True,
        "ids": ["14C3-7961", "14C3-0608", "14C3-7922", "14C3-0616"],
        "conflicts": ["SimpleMtkWlan"],
        "builds": {
            TAHOE: ("https://github.com/flxxxxddd/SimpleMtkWlan/releases/download/v1.5.0/AirportMtkWlan-Tahoe-1.5.0-RELEASE.zip",
                    1848113, "3b3f354f88d2ff3a3987d7adbeeb3a96b7929a22909115fab602fbaa6b22dcc0"),
        },
        "what": "MediaTek Wi-Fi (AirportMtkWlan 1.5.0, native Wi-Fi menu)",
    },
    {   # Qualcomm WCN7850 / FastConnect 7800 (NCM865) Wi-Fi; built for Tahoe (MinKernel 25)
        "name": "AirportWCN7850", "repo": "razvanccr/AirportWCN7850", "section": "Network", "experimental": True,
        "ids": ["17CB-1107"],
        "builds": {
            TAHOE: ("https://github.com/razvanccr/AirportWCN7850/releases/download/v0.0.2/AirportWCN7850-0.0.2.zip",
                    3868966, "0a91635873f60243b5e8730577a29e5ccc3531b135f1dff27d1f3c69075f9e08"),
        },
        "what": "Qualcomm WCN7850 Wi-Fi (AirportWCN7850 0.0.2, native Wi-Fi menu, 802.11ac)",
    },
    {   # Qualcomm WCN7850 Bluetooth: firmware loader, macOS's own Bluetooth stack drives it afterwards
        "name": "BluetoothWCN7850", "repo": "razvanccr/BluetoothWCN7850", "section": "Bluetooth", "experimental": False,
        "ids": ["0489-E0F3", "0489-E0FC", "0489-E100", "0489-E103", "0489-E10A", "0489-E10D", "0489-E11B", "0489-E11C",
                "0489-E11F", "0489-E141", "0489-E14A", "0489-E14B", "0489-E14D", "0CF3-E700", "13D3-3623", "13D3-3624",
                "2C7C-0130", "2C7C-0131", "2C7C-0132"],
        "requires": ["BlueToolFixup"],
        "builds": {
            v: ("https://github.com/razvanccr/BluetoothWCN7850/releases/download/v1.0.0/BluetoothWCN7850-1.0.0.zip",
                229271, "acc9c4352525163050ee7e537f5bb42bd7c03cda5b0ecabd5e9db875a1eb90bd") for v in (SEQUOIA, TAHOE)
        },
        "what": "Qualcomm WCN7850 Bluetooth (BluetoothWCN7850 1.0.0)",
    },
    {   # AMD laptops whose xHCI controllers have one MSI vector: input lags seconds behind without it
        "name": "XhciNudge", "repo": "MonkaKokosowa/XhciNudge", "section": "USB Controllers", "experimental": True,
        "ids": ["1022-161D", "1022-161E", "1022-15D6", "1022-15D7"],
        "builds": {
            v: ("https://github.com/MonkaKokosowa/XhciNudge/releases/download/1.0/XhciNudge-1.0.0.zip",
                8304, "271659aec947aa2d01300eadb514b138909e6322305163ddcab653403251bd1f") for v in (SEQUOIA, TAHOE)
        },
        "what": "AMD USB input lag fix (XhciNudge 1.0.0)",
    },
    {   # same controllers: USB storage drops once macOS hands out RAM below ~159 MB; costs ~155 MB of RAM
        "name": "KernReserveLow.efi", "repo": "MonkaKokosowa/KernReserveLow", "section": "USB Controllers",
        "experimental": True, "efi": True,
        "ids": ["1022-161D", "1022-161E", "1022-15D6", "1022-15D7"],
        "builds": {
            v: ("https://github.com/MonkaKokosowa/KernReserveLow/releases/download/1.0/KernReserveLow-1.0.0-RELEASE.zip",
                22299, "a8c100b5218e33f48e30f9c7320c3965fb2e856eb081ec2c6383c9d3bd76b082") for v in (SEQUOIA, TAHOE)
        },
        "what": "AMD USB storage disconnect fix (KernReserveLow 1.0.0, reserves ~155 MB of low RAM)",
    },
    {   # Lenovo firmware that loads Microsoft's cloud-recovery driver: random vm_page_validate_no_references panics
        "name": "LegionCbmrFix.efi", "repo": "watchthelight-labs/LegionCbmrFix", "section": None, "vendor": "LENOVO",
        "experimental": True, "efi": True,
        "builds": {
            v: ("https://github.com/watchthelight-labs/LegionCbmrFix/releases/download/1.0.0/LegionCbmrFix-1.0.0.zip",
                961, "52f7217896ca72c74a2527f5e5943939dda99a3b46bba4651bc05cd135255ec9") for v in (SEQUOIA, TAHOE)
        },
        "what": "Lenovo cloud-recovery panic fix (LegionCbmrFix 1.0.0)",
    },
    {   # Arrow Lake-HX / 800-series PCH I2C controllers, so VoodooI2C drives the touchpad (codeless)
        "name": "LegionI2CArrowLake", "repo": "watchthelight-labs/LegionI2CArrowLake", "section": None,
        "experimental": False, "ids": ["8086-7F4C", "8086-7F4D", "8086-7F4E", "8086-7F4F"],
        "requires": ["VoodooI2C"], "only_with": "VoodooI2C",
        "builds": {
            v: ("https://github.com/watchthelight-labs/LegionI2CArrowLake/releases/download/1.1.0/LegionI2CArrowLake-1.1.0.zip",
                2341, "41cae11bbd5e12a6a9949bb5a3320fca6ee74b3fceaa2ae728a28070b55ef6ea") for v in (SEQUOIA, TAHOE)
        },
        "what": "Arrow Lake I2C touchpad controller (LegionI2CArrowLake 1.1.0)",
    },
    {   # ITE 8258 USB keyboard (048D:C195): without it the internal keyboard enumerates but does not type (codeless)
        "name": "LegionITEKbdFix", "repo": "watchthelight-labs/LegionITEKbdFix", "section": None, "experimental": False,
        "ids": ["048D-C195"],
        "builds": {
            v: ("https://github.com/watchthelight-labs/LegionITEKbdFix/releases/download/1.0.0/LegionITEKbdFix-1.0.0.zip",
                2147, "3624df9a1b5da807213761cbc5cb9b5b54398bd7c12adf2116f2a73911af8645") for v in (SEQUOIA, TAHOE)
        },
        "what": "ITE 8258 laptop keyboard (LegionITEKbdFix 1.0.0)",
    },
    {   # Arrow Lake (Core Ultra 200HX): real clocks and power limits on Tahoe; does nothing on any other CPU
        "name": "LegionCpuPower", "repo": "watchthelight-labs/LegionCpuPower", "section": None, "codename": "Arrow Lake",
        "experimental": True, "requires": ["Lilu"],
        "builds": {
            TAHOE: ("https://github.com/watchthelight-labs/LegionCpuPower/releases/download/0.3.3/LegionCpuPower-0.3.3.zip",
                    75086, "441a25bd349395954208c60e6577494987f5f4f4aede4a8a20681d28302bc813"),
        },
        "what": "Arrow Lake CPU clocks and power (LegionCpuPower 0.3.3)",
    },
]


def _darwin(macos_version):
    """25 from "25.0.0" or (25, 0, 0)."""
    try:
        if isinstance(macos_version, (tuple, list)):
            return int(macos_version[0])
        return int(str(macos_version).split(".")[0])
    except (ValueError, IndexError):
        return 0


def build_for(driver, macos_version):
    """(url, size, sha256) of the file built for this macOS, or None when the author built none for it."""
    return driver["builds"].get(_darwin(macos_version))


def _ids(report, section=None):
    """Every "Device ID" in one report section, or in all of them. Upper-case "VVVV-DDDD", as the scan writes them."""
    out = set()
    for name, devices in (report or {}).items():
        if section and name != section or not isinstance(devices, dict):
            continue
        for props in devices.values():
            if isinstance(props, dict) and isinstance(props.get("Device ID"), str):
                out.add(props["Device ID"].upper())
    return out


def matches(driver, report):
    """True when the scanned machine has hardware this driver is for."""
    if driver.get("ids") and not (_ids(report, driver.get("section")) & set(driver["ids"])):
        return False
    if driver.get("vendor") and not str((report.get("Motherboard") or {}).get("Name", "")).upper().startswith(driver["vendor"]):
        return False
    if driver.get("codename") and driver["codename"].lower() not in str((report.get("CPU") or {}).get("Codename", "")).lower():
        return False
    return True


def register():
    """Add the kext entries to the loaded engine's kext list. Idempotent."""
    from Scripts.datasets import kext_data  # noqa: PLC0415 - importable once the engine is loaded
    for d in DRIVERS:
        if d.get("efi") or d["name"] in kext_data.kext_index_by_name:
            continue
        cat = {"Network": "Wi-Fi", "Bluetooth": "Bluetooth"}.get(d.get("section"), "Extras")
        url, size, sha = d["builds"][max(d["builds"])]          # apply_kexts re-pins it to the build for this macOS
        kext_data.kexts.append(kext_data.KextInfo(name=d["name"], description=d["what"], category=cat,
                                                  requires_kexts=list(d.get("requires", [])),
                                                  download_info={"id": size, "url": url, "sha256": sha}))
        kext_data.kext_index_by_name[d["name"]] = len(kext_data.kexts) - 1


def chosen(report, macos_version, experimental, engine_kexts=()):
    """-> (drivers to add, notices). engine_kexts: names the engine already checked, for only_with and conflicts."""
    add, notices = [], []
    for d in DRIVERS:
        if not matches(d, report):
            continue
        if d.get("only_with") and d["only_with"] not in engine_kexts:
            continue
        if not build_for(d, macos_version):
            notices.append(f"{d['what']}: matches this machine but has no build for this macOS version; not added.")
            continue
        if d["experimental"] and not experimental:
            notices.append(f"{d['what']}: a community driver exists for this hardware and is NOT in this build. "
                           "It is unproven on most machines. To try it, turn on \"Include experimental drivers\" "
                           "and build again.")
            continue
        add.append(d)
        notices.append(f"{d['what']}: added" + (" (experimental: keep Ethernet or the previous EFI ready)."
                                                if d["experimental"] else "."))
    return add, notices


def apply_kexts(ocpe, customization, macos_version, notices, experimental=False):
    """After the engine has chosen its kexts: check the matching community kexts, pinned to this macOS's build.
    Fail-safe like netsupport.apply_kexts: a problem becomes a notice, never an error."""
    try:
        from Scripts.datasets import kext_data  # noqa: PLC0415
        km = ocpe.k
        checked = {k.name for k in km.kexts if k.checked}
        add, said = chosen(customization, macos_version, experimental, checked)
        notices.extend(said)
        for d in add:
            if d.get("efi"):
                continue                                        # written by apply_efi_drivers after the build
            idx = kext_data.kext_index_by_name.get(d["name"])
            if idx is None:
                continue
            url, size, sha = build_for(d, macos_version)
            km.kexts[idx].download_info = {"id": size, "url": url, "sha256": sha}
            for other in d.get("conflicts", []):
                j = kext_data.kext_index_by_name.get(other)
                if j is not None and km.kexts[j].checked:
                    km.kexts[j].checked = False
                    notices.append(f"{other} left out: {d['name']} drives the same card.")
            km.check_kext(idx, macos_version)
    except Exception as e:  # noqa: BLE001 - an add-on must never break the whole build
        notices.append(f"Community drivers could not be applied: {type(e).__name__}: {e}")


def _efi_from_zip(body, name):
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        hits = [n for n in z.namelist() if n.rsplit("/", 1)[-1] == name and "__MACOSX" not in n]
        if len(hits) != 1:
            raise ValueError(f"{name}: {len(hits)} copies in the archive")
        return z.read(hits[0])


def apply_efi_drivers(config_path, customization, macos_version, notices, fetch, experimental=False):
    """Write the matching community UEFI drivers into EFI/OC/Drivers and enable them in config.plist.
    fetch(url) -> bytes (the engine's downloader, with the mirror behind it); the archive must have the pinned size
    and SHA-256 or nothing is written."""
    try:
        add, _ = chosen(customization, macos_version, experimental)
        add = [d for d in add if d.get("efi")]
        if not add:
            return []
        with open(config_path, "rb") as fh:
            cfg = plistlib.load(fh)
        drivers = cfg.setdefault("UEFI", {}).setdefault("Drivers", [])
        ddir = os.path.join(os.path.dirname(config_path), "Drivers")
        written = []
        for d in add:
            url, size, sha = build_for(d, macos_version)
            body = fetch(url)
            if len(body) != size or hashlib.sha256(body).hexdigest() != sha:
                notices.append(f"{d['what']}: the download did not match its pinned SHA-256; not added.")
                continue
            efi = _efi_from_zip(body, d["name"])
            with open(os.path.join(ddir, d["name"] + ".tmp"), "wb") as fh:
                fh.write(efi)
            os.replace(os.path.join(ddir, d["name"] + ".tmp"), os.path.join(ddir, d["name"]))
            if not any(isinstance(e, dict) and e.get("Path") == d["name"] for e in drivers):
                entry = {"Arguments": "", "Comment": d["what"], "Enabled": True, "LoadEarly": False, "Path": d["name"]}
                # OpenCore 1.0.4 added HideVerbose to every driver entry and ocvalidate reports an entry without it;
                # older OpenCore rejects the unknown key, so it follows the keys this config's own entries carry.
                if any(isinstance(e, dict) and "HideVerbose" in e for e in drivers):
                    entry["HideVerbose"] = False
                drivers.append(entry)
            written.append(d["name"])
        if written:
            with open(config_path + ".tmp", "wb") as fh:
                plistlib.dump(cfg, fh)
            os.replace(config_path + ".tmp", config_path)
        return written
    except Exception as e:  # noqa: BLE001
        notices.append(f"Community UEFI drivers could not be added: {type(e).__name__}: {e}")
        return []
