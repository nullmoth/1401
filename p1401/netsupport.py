"""Network-adapter support: what works in the installed system and in the installer.

Two jobs, both outside the upstream engine so upstream stays pinned and unpatched:

1. MediaTek Wi-Fi/Bluetooth. The upstream engine carries no MediaTek IDs and no MediaTek kext, so an MT7921/
   MT7922/MT7925 laptop gets an EFI with no wireless at all - the largest "Wi-Fi does not work" group in the user
   chat after Intel. register() adds the device IDs and two pinned kexts (SHA-256 verified on download): the
   SimpleMtkWlan Wi-Fi kext, which 1401 builds itself and hosts on its mirror (SimpleMtkWlan publishes no release),
   and the SimpleMtkBtFw Bluetooth kext from its GitHub release. apply_kexts() turns the Wi-Fi kext on only for the
   three IDs its Info.plist matches (MT7921/MT7922); other MediaTek Wi-Fi cards (RZ616, MT7925) have no driver and
   get the honest Ethernet/offline-installer notice. The installer is treated as offline-only either way, since an
   experimental Wi-Fi driver is not relied on during install.

2. A plain reading of what the machine can do for networking, so the app can tell the user - before they are
   stranded at the installer with no internet and no idea why - whether this build will have Wi-Fi, needs
   Ethernet, or should be written as a full offline installer. 34 users hit "the installer needs internet and my
   Wi-Fi does not work in it".

network_support() is pure (it takes the ID sets, not the engine) so it can be tested without the engine loaded.
"""
import json
import os

# The build leaves this beside the EFI so the USB writer knows, without re-scanning, that this machine has no
# network the macOS installer can use, and says so before it writes instead of letting the user find out at
# "no internet" in the installer.
NETWORK_MARKER = "installer-network.json"

# A warning, not a stop. 2.0.0 stopped the write here and asked for BaseSystem.dmg in the Recovery folder, but that
# file is the same recovery image the writer downloads, and it still fetches macOS over the network during the
# install, so the advice could not help; the window also had no way past the stop. 26 write logs in one morning.
OFFLINE_INSTALLER_MESSAGE = (
    "This PC has no network adapter that works in the macOS installer. The stick is written anyway, but the "
    "installer downloads macOS from Apple: before you install, connect a supported Ethernet or Wi-Fi adapter, "
    "such as a USB Ethernet adapter sold for Macs."
)

# MediaTek device IDs, "VENDOR-DEVICE" upper-case to match the probe and upstream pci_data.
# Wi-Fi is PCIe under MediaTek's own vendor 14C3; Bluetooth is a USB function, mostly under 0E8D with the usual
# OEM re-brands (Azurewave 13D3, Foxconn 0489). Source: the mt76 driver id tables and the MT7921/7922/7925
# datasheets; the cards users name in chat are MT7921 and MT7922.
MEDIATEK_WIFI_IDS = [
    "14C3-0608",  # MT7921
    "14C3-7961",  # MT7921
    "14C3-0616",  # MT7922
    "14C3-7922",  # MT7922
    "14C3-0717",  # MT7925 (Wi-Fi 7)
    "14C3-7925",  # MT7925
]
MEDIATEK_BT_IDS = [
    "0E8D-7961", "0E8D-0608",  # MT7921
    "0E8D-0616", "0E8D-7922",  # MT7922
    "0E8D-0717", "0E8D-7925",  # MT7925
    "13D3-3563",               # Azurewave MT7921
    "0489-E0C8", "0489-E0CD", "0489-E0E2",  # Foxconn MT7921/MT7922
    # OEM Bluetooth re-brands the probe actually finds in the field and that SimpleMtkBtFw's Info.plist matches, so
    # the kext was never enabled for them before: 13D3-3585 is the most common MediaTek BT id in the scans.
    "13D3-3585", "13D3-3567", "13D3-3568", "13D3-3614",  # Azurewave MT7922/MT7925
    "0489-E0F6",                                          # Foxconn MT7922
    "04CA-3802",                                          # Lite-On MT7921
]

MTK_WIFI_KEXT = "SimpleMtkWlan"
MTK_BT_KEXT = "SimpleMtkBtFw"

# The three device IDs SimpleMtkWlan's Info.plist actually matches (IOPCIPrimaryMatch 0x7961/0x0608/0x7922, vendor
# 14c3). Only these get the Wi-Fi kext; the other MediaTek Wi-Fi IDs above (RZ616 0616, MT7925 0717/7925) have no
# driver that matches them and get the honest "no macOS Wi-Fi - use Ethernet/USB or the offline installer" path.
MEDIATEK_WIFI_KEXT_IDS = ["14C3-7961", "14C3-0608", "14C3-7922"]

# SimpleMtkWlan publishes no release, so 1401 builds it itself from a pinned commit against acidanthera's
# MacKernelSDK (the kext's own project configuration; that SDK supplies the version-stable kernel headers, including
# IONetworkController::outputStart, which Apple dropped from the public macOS SDK headers). The built kext and the
# matching GPL-2.0 source are hosted on NullMoth's own content-addressed mirror and pinned here by URL + SHA-256,
# which gathering_files verifies on download (a changed or substituted file is refused and the build fails). Built on
# the macOS 15 SDK; see tools/build_mtkwlan.sh and p1401/mirror.json. Licences (checked live with `gh api .../license`):
# SimpleMtkWlan GPL-2.0, SimpleMtkBtFw GPL-3.0 - both redistributable.
MTK_WIFI_COMMIT = "37ba676ad18273b7e622ec6db45afc25db238109"
MTK_WIFI_MKSDK_COMMIT = "3f750085caa17ec3a7880f11c11bf4f48cd6a164"
MTK_WIFI_SHA256 = "da0ef98222f7d29a6e3cdde91185348b7fe8abdf5c324c5e2349295996ee18f9"
MTK_WIFI_SIZE = 1822103
MTK_WIFI_URL = "https://nullmothsystems.com/mirror/" + MTK_WIFI_SHA256
MTK_WIFI_SRC_SHA256 = "3109381a2db4a9d77053bbc0fe86079c7f45382be8e8c4378012c07be5cd49fa"
MTK_WIFI_SRC_SIZE = 3074903
MTK_WIFI_SRC_URL = "https://nullmothsystems.com/mirror/" + MTK_WIFI_SRC_SHA256

MTK_BT_ASSET_ID = 433233966
MTK_BT_URL = "https://github.com/laobamac/SimpleMtkBtFw/releases/download/1.0.0/SimpleMtkBtFw-1.0.0-RELEASE.zip"
MTK_BT_SHA256 = "b6afbe453db5827e7e2c8cdd045374f4fa6760f63e6ae26a3f322aa75dc84954"


def _devices(hardware_report, section):
    """Device IDs present in one section of the report/customization ("Network" or "Bluetooth")."""
    out = []
    for props in (hardware_report.get(section) or {}).values():
        if isinstance(props, dict) and props.get("Device ID"):
            out.append(props["Device ID"])
    return out


def network_support(hardware_report, wifi_native, wifi_experimental, bluetooth_known, ethernet_known,
                     wifi_unsupported=()):
    """What this machine can do for networking, from the device IDs the probe found.

    The ID sets are passed in (built from pci_data by the caller, or by a test) so this stays pure.
    wifi_unsupported = Wi-Fi cards we recognise but have no driver for (present, but no macOS Wi-Fi).
    Returns a dict with:
      wifi:     "native" | "experimental" | "unsupported" | "none"  (none = no Wi-Fi card at all)
      ethernet: True if a supported wired NIC is present
      offline_recommended: True when nothing here will give the macOS *installer* internet
      notice:   one line for the user, or "" when everything is covered
    """
    wifi_native, wifi_experimental = set(wifi_native), set(wifi_experimental)
    bluetooth_known, ethernet_known, wifi_unsupported = set(bluetooth_known), set(ethernet_known), set(wifi_unsupported)
    net = _devices(hardware_report, "Network")
    wifi_ids = [d for d in net if d in wifi_native or d in wifi_experimental or d in wifi_unsupported]
    eth = any(d in ethernet_known for d in net)

    if not wifi_ids:
        wifi = "none"
    elif any(d in wifi_native for d in wifi_ids):
        wifi = "native"
    elif any(d in wifi_experimental for d in wifi_ids):
        wifi = "experimental"
    else:
        wifi = "unsupported"

    # The installer has internet only if the build gives it a working NIC. Ethernet always works there; native
    # Wi-Fi works there too. An experimental Wi-Fi driver may not be in time for the installer and is not relied
    # on. So: recommend the offline (full-installer) path unless there is Ethernet or native Wi-Fi.
    installer_online = eth or wifi == "native"
    offline_recommended = not installer_online

    if installer_online:
        notice = ""
    elif wifi == "experimental":
        notice = ("No Ethernet and no natively-supported Wi-Fi: this build adds an experimental MediaTek Wi-Fi "
                  "driver, but it may not work inside the macOS installer. Write a full offline installer, or "
                  "plug in Ethernet, so the installer can reach the internet.")
    elif wifi == "none" and not net:
        notice = ("No network adapter was detected. The macOS installer needs the internet: write a full offline "
                  "installer, or add a supported Ethernet or Wi-Fi adapter.")
    else:
        notice = ("No Ethernet and no Wi-Fi that works in the macOS installer. Write a full offline installer, or "
                  "plug in Ethernet, so the installer can reach the internet.")

    return {"wifi": wifi, "ethernet": eth, "offline_recommended": offline_recommended, "notice": notice}


def register():
    """Add MediaTek IDs and the two MediaTek kexts to the loaded engine's datasets. Idempotent, so repeated
    builds in one process do not duplicate entries. Importable only after the engine is on sys.path."""
    from Scripts.datasets import pci_data  # noqa: PLC0415 - importable once the engine is loaded
    from Scripts.datasets import kext_data  # noqa: PLC0415

    pci_data.MediaTekWiFiIDs = list(MEDIATEK_WIFI_IDS)
    pci_data.MediaTekBluetoothIDs = list(MEDIATEK_BT_IDS)
    # The engine's Wi-Fi pre-pass and compatibility checks look cards up in these aggregate lists.
    for i in MEDIATEK_WIFI_IDS:
        if i not in pci_data.WirelessCardIDs:
            pci_data.WirelessCardIDs.append(i)
    for i in MEDIATEK_BT_IDS:
        if i not in pci_data.BluetoothIDs:
            pci_data.BluetoothIDs.append(i)

    KextInfo = kext_data.KextInfo
    # Each kext is pinned to an exact file and SHA-256, so the build fetches a known binary (never "latest"):
    # SimpleMtkWlan from NullMoth's mirror (we build it), SimpleMtkBtFw from its own GitHub release.
    new = [
        KextInfo(name=MTK_WIFI_KEXT,
                 description="MediaTek Wi-Fi (MT7921/MT7922) - experimental",
                 category="Wi-Fi", conflict_group_id="MediaTekWiFi",
                 download_info={"id": MTK_WIFI_SIZE, "url": MTK_WIFI_URL, "sha256": MTK_WIFI_SHA256}),
        KextInfo(name=MTK_BT_KEXT,
                 description="MediaTek Bluetooth firmware (MT7921/MT7922/MT7925)",
                 category="Bluetooth", requires_kexts=["BlueToolFixup"],
                 download_info={"id": MTK_BT_ASSET_ID, "url": MTK_BT_URL, "sha256": MTK_BT_SHA256}),
    ]
    for k in new:
        if k.name not in kext_data.kext_index_by_name:
            kext_data.kexts.append(k)
            kext_data.kext_index_by_name[k.name] = len(kext_data.kexts) - 1


def apply_kexts(ocpe, customization, macos_version, notices, experimental=False):
    """After the engine has chosen its kexts, turn on the MediaTek kexts if the machine has a MediaTek radio.
    Fail-safe: any problem is reported as a notice, never raised, so it cannot turn a good build into an error.

    The Wi-Fi kext is experimental and unproven, so it is only added when the user opted in (experimental=True);
    otherwise the build says the driver exists and how to ask for it. Bluetooth is not gated: SimpleMtkBtFw is a
    firmware uploader for a USB radio and cannot cost the machine its display or its network."""
    try:
        from Scripts.datasets import kext_data  # noqa: PLC0415
        km = ocpe.k
        net = _devices(customization, "Network")
        bt = _devices(customization, "Bluetooth")
        try:
            from . import community  # noqa: PLC0415
            tahoe_native = next(d for d in community.DRIVERS if d["name"] == "AirportMtkWlan")
            deferred = bool(community.build_for(tahoe_native, macos_version)) and any(d in tahoe_native["ids"] for d in net)
        except ImportError:     # loaded on its own (the opt-in test's copies): no community table to defer to
            deferred = False
        if deferred:
            pass    # macOS 26: community.py adds AirportMtkWlan (native Wi-Fi menu) for these cards and says so
        elif any(d in MEDIATEK_WIFI_KEXT_IDS for d in net):
            idx = kext_data.kext_index_by_name.get(MTK_WIFI_KEXT)
            if idx is None:
                pass
            elif not experimental:
                notices.append("MediaTek Wi-Fi: this card (MT7921/MT7922) has an experimental driver, SimpleMtkWlan, "
                               "which is NOT included in this build. It can be unstable and may not work inside the "
                               "macOS installer. Use Ethernet for the install; to try the driver anyway, turn on "
                               "\"Include experimental drivers\" and build again.")
            else:
                km.check_kext(idx, macos_version)
                notices.append("MediaTek Wi-Fi: added the experimental SimpleMtkWlan driver (MT7921/MT7922) because "
                               "experimental drivers are turned on. It may be unstable and may not work inside the "
                               "macOS installer - have Ethernet ready for the install.")
        elif any(d in MEDIATEK_WIFI_IDS for d in net):
            # A MediaTek Wi-Fi card SimpleMtkWlan does not match (RZ616 0616, MT7925 0717/7925): no driver to install.
            notices.append("MediaTek Wi-Fi: this card (RZ616 / MT7925 class) has no macOS driver. Use Ethernet or a "
                           "USB Wi-Fi adapter, or write a full offline installer.")
        if any(d in MEDIATEK_BT_IDS for d in bt):
            idx = kext_data.kext_index_by_name.get(MTK_BT_KEXT)
            if idx is not None:
                km.check_kext(idx, macos_version)
                notices.append("MediaTek Bluetooth: added SimpleMtkBtFw.")
    except Exception as e:  # noqa: BLE001 - a networking add-on must never break the whole build
        notices.append(f"MediaTek network support could not be applied: {type(e).__name__}: {e}")


def support_from_pci(customization, notices):
    """Run network_support() against the engine's real ID tables and append its notice. Returns the dict."""
    from Scripts.datasets import pci_data  # noqa: PLC0415
    native = set(pci_data.WirelessCardIDs) - set(MEDIATEK_WIFI_IDS)
    unsupported = set(MEDIATEK_WIFI_IDS) - set(MEDIATEK_WIFI_KEXT_IDS)  # RZ616/MT7925: recognised, no driver
    status = network_support(customization, native, MEDIATEK_WIFI_KEXT_IDS, pci_data.BluetoothIDs,
                             pci_data.EthernetIDs, unsupported)
    if status["notice"]:
        notices.append(status["notice"])
    return status


# MediaTek Bluetooth IDs SimpleMtkBtFw 1.0.0's Info.plist does not list although the cards behind them are the chips it
# drives: 1401 enabled the kext for them and Bluetooth stayed off (#336, RZ616 0e8d:0616; works once the ID is listed).
# The kext reads the chip at run time, so its personalities differ only in idVendor/idProduct: each missing ID gets a
# copy of its family's personality, on this PC's own EFI, never in a file NullMoth distributes.
MTK_BT_FAMILY = {"0E8D-7961": "MT7921", "0E8D-0608": "MT7921", "0E8D-0616": "MT7922A", "0E8D-7922": "MT7922A"}


def add_missing_bt_ids(out_dir, customization, notices):
    """Adds a personality to EFI/OC/Kexts/SimpleMtkBtFw.kext for each MediaTek Bluetooth ID present here that the
    kext does not match. Fail-safe: any problem is a notice and the kext is left as it was."""
    import plistlib  # noqa: PLC0415
    present = [d.upper() for d in _devices(customization, "Bluetooth")]
    wanted = [d for d in present if d in MTK_BT_FAMILY]
    path = os.path.join(out_dir, "EFI", "OC", "Kexts", MTK_BT_KEXT + ".kext", "Contents", "Info.plist")
    if not wanted or not os.path.isfile(path):
        return []
    try:
        with open(path, "rb") as fh:
            info = plistlib.load(fh)
        pers = info.get("IOKitPersonalities") or {}
        have = {(v.get("idVendor"), v.get("idProduct")) for v in pers.values() if isinstance(v, dict)}
        added = []
        for dev in wanted:
            vid, pid = (int(x, 16) for x in dev.split("-"))
            if (vid, pid) in have:
                continue
            fam = MTK_BT_FAMILY[dev]
            template = next((v for k, v in sorted(pers.items()) if k.startswith(f"SimpleMtkBtFw_{fam}_") and "idProduct" in v), None)
            if template is None:
                notices.append(f"Bluetooth: {dev} needs a {fam} entry in SimpleMtkBtFw and the kext has none to copy; it stays off.")
                continue
            entry = dict(template); entry["idVendor"], entry["idProduct"] = vid, pid
            pers[f"SimpleMtkBtFw_{fam}_{dev.lower().replace('-', '_')}"] = entry
            have.add((vid, pid)); added.append(dev)
        if added:
            info["IOKitPersonalities"] = pers
            tmp = path + ".tmp"
            with open(tmp, "wb") as fh:
                plistlib.dump(info, fh)
            os.replace(tmp, path)
            notices.append("Bluetooth: SimpleMtkBtFw now also matches " + ", ".join(added) + " (this PC's MediaTek card).")
        return added
    except (OSError, ValueError, plistlib.InvalidFileException) as e:
        notices.append(f"Bluetooth: could not add this PC's MediaTek Bluetooth ID to SimpleMtkBtFw ({e}); it may stay off.")
        return []

def write_marker(build_dir, status):
    """Record the network-support status beside the EFI for the writer. Fail-safe: a write that cannot happen just
    means the writer falls back to its old behaviour, never a failed build."""
    try:
        with open(os.path.join(build_dir, NETWORK_MARKER), "w") as fh:
            json.dump({"offline_recommended": bool(status.get("offline_recommended")),
                       "wifi": status.get("wifi"), "ethernet": bool(status.get("ethernet"))}, fh)
    except OSError:
        pass


def needs_local_image(build_dir):
    """True only when the build left a marker saying this machine has no installer network. A missing or unreadable
    marker returns False, so an older build or a read error never blocks the writer."""
    try:
        with open(os.path.join(build_dir, NETWORK_MARKER)) as fh:
            return bool(json.load(fh).get("offline_recommended"))
    except (OSError, ValueError):
        return False
