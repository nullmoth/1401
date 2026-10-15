"""Network-adapter support: what works in the installed system and in the installer.

Two jobs, both outside the upstream engine so upstream stays pinned and unpatched:

1. MediaTek Wi-Fi/Bluetooth. The upstream engine carries no MediaTek IDs and no MediaTek kext, so an MT7921/
   MT7922/MT7925 laptop gets an EFI with no wireless at all - the largest "Wi-Fi does not work" group in the user
   chat after Intel. register() adds the device IDs and, for Bluetooth, the laobamac/SimpleMtkBtFw kext (a pinned
   release asset, SHA-256 verified on download); apply_kexts() turns it on when the machine has a MediaTek radio.
   MediaTek Wi-Fi has no prebuilt driver to ship (SimpleMtkWlan publishes no release), so a MediaTek Wi-Fi card is
   only detected - the user is pointed at the experimental project and the installer is treated as offline-only.

2. A plain reading of what the machine can do for networking, so the app can tell the user - before they are
   stranded at the installer with no internet and no idea why - whether this build will have Wi-Fi, needs
   Ethernet, or should be written as a full offline installer. 34 users hit "the installer needs internet and my
   Wi-Fi does not work in it".

network_support() is pure (it takes the ID sets, not the engine) so it can be tested without the engine loaded.
"""
import json
import os

# The build leaves this beside the EFI so the USB writer knows, without re-scanning, that this machine has no
# network the macOS installer can use - the writer then defaults to the offline (local-image) path instead of
# silently writing an online-only recovery stick that strands the user at "no internet" in the installer.
NETWORK_MARKER = "installer-network.json"

OFFLINE_INSTALLER_MESSAGE = (
    "This PC has no network adapter that works in the macOS installer, so an online recovery stick cannot finish "
    "the install. Put a macOS recovery image (BaseSystem.dmg and BaseSystem.chunklist, made with macrecovery on "
    "any computer) into the Recovery folder next to the app and press Next again, or connect a supported Ethernet "
    "or Wi-Fi adapter. To write the online recovery stick anyway, re-run with --allow-online."
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

# SimpleMtkWlan ships NO release and NO tag (verified live 2026-10-14, `gh api repos/laobamac/SimpleMtkWlan/releases`
# returns []), so there is no prebuilt kext to fetch; auto-installing it would fail every MediaTek-Wi-Fi build. A
# MediaTek Wi-Fi card is therefore detected and the user is pointed at the project, and the installer-internet
# classifier already treats such a card as experimental/offline. SimpleMtkBtFw does ship a built kext: pin the exact
# 1.0.0 RELEASE asset and verify its SHA-256 on download (gathering_files passes download_info["sha256"] to the
# fetcher, so a mirror or a changed asset is rejected). Licences, checked live with `gh api repos/.../license`:
# SimpleMtkWlan GPL-2.0, SimpleMtkBtFw GPL-3.0 - both redistributable, and the kext is fetched from upstream at build
# time, not bundled.
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


def network_support(hardware_report, wifi_native, wifi_experimental, bluetooth_known, ethernet_known):
    """What this machine can do for networking, from the device IDs the probe found.

    The ID sets are passed in (built from pci_data by the caller, or by a test) so this stays pure.
    Returns a dict with:
      wifi:     "native" | "experimental" | "unsupported" | "none"  (none = no Wi-Fi card at all)
      ethernet: True if a supported wired NIC is present
      offline_recommended: True when nothing here will give the macOS *installer* internet
      notice:   one line for the user, or "" when everything is covered
    """
    wifi_native, wifi_experimental = set(wifi_native), set(wifi_experimental)
    bluetooth_known, ethernet_known = set(bluetooth_known), set(ethernet_known)
    net = _devices(hardware_report, "Network")
    wifi_ids = [d for d in net if d in wifi_native or d in wifi_experimental]
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
    # Only SimpleMtkBtFw is auto-installed; SimpleMtkWlan has no prebuilt release (see the note above). The exact
    # asset and its SHA-256 are pinned so the build fetches a known binary, not whatever "latest" becomes.
    new = [
        KextInfo(name=MTK_BT_KEXT,
                 description="MediaTek Bluetooth firmware (MT7921/MT7922/MT7925)",
                 category="Bluetooth", requires_kexts=["BlueToolFixup"],
                 download_info={"id": MTK_BT_ASSET_ID, "url": MTK_BT_URL, "sha256": MTK_BT_SHA256}),
    ]
    for k in new:
        if k.name not in kext_data.kext_index_by_name:
            kext_data.kexts.append(k)
            kext_data.kext_index_by_name[k.name] = len(kext_data.kexts) - 1


def apply_kexts(ocpe, customization, macos_version, notices):
    """After the engine has chosen its kexts, turn on the MediaTek kexts if the machine has a MediaTek radio.
    Fail-safe: any problem is reported as a notice, never raised, so it cannot turn a good build into an error."""
    try:
        from Scripts.datasets import kext_data  # noqa: PLC0415
        km = ocpe.k
        net = _devices(customization, "Network")
        bt = _devices(customization, "Bluetooth")
        if any(d in MEDIATEK_WIFI_IDS for d in net):
            # No prebuilt SimpleMtkWlan release exists, so nothing is auto-installed; name the project and rely on
            # the classifier having already flagged the installer as offline-only for this machine.
            notices.append("MediaTek Wi-Fi: no macOS driver is installed automatically - the only project is "
                           "experimental (github.com/laobamac/SimpleMtkWlan). Use Ethernet for the install.")
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
    status = network_support(customization, native, MEDIATEK_WIFI_IDS, pci_data.BluetoothIDs, pci_data.EthernetIDs)
    if status["notice"]:
        notices.append(status["notice"])
    return status


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
