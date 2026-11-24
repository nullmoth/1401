"""OpenCore's binary drivers (acidanthera/OcBinaryData) are optional when GitHub cannot deliver them.

The engine downloads OcBinaryData's master.zip beside OpenCore for HfsPlus.efi, apfs_aligned.efi and the picker
images, and stopped the whole build when that one download failed. 1401 3.0 logs: 92 builds in two days stopped
there on networks where GitHub's downloads time out. NullMoth cannot carry that archive on its mirror (its drivers are
not ours to host), so 1401 builds without it when it cannot be fetched:

- HfsPlus.efi / HfsPlusLegacy.efi become OpenHfsPlus.efi, the open HFS+ driver that ships inside the verified
  OpenCore release itself (validate.restore_release_components places its bytes from that zip);
- apfs_aligned.efi has no open replacement, so a build that needs it (macOS 26) stops with a message that names the
  network as the cause;
- the picker images are only cosmetic and stay out.

The OpenCore download is then not recorded as complete, so the next build tries OcBinaryData again."""
import os
import plistlib
import zipfile

URL = "https://github.com/acidanthera/OcBinaryData/archive/refs/heads/master.zip"
HFS = ("HfsPlus.efi", "HfsPlusLegacy.efi")
OPEN_HFS = "OpenHfsPlus.efi"
APFS = "apfs_aligned.efi"
_state = {"missing": False}


class NeedsOcBinaryData(RuntimeError):
    pass


def reset():
    _state["missing"] = False


def missing():
    return _state["missing"]


def _empty_archive(path):
    """What extract_zip_file expects: a zip holding the OcBinaryData-master folder, here with nothing in it."""
    tmp = path + ".1401-empty"
    with zipfile.ZipFile(tmp, "w") as archive:
        archive.writestr("OcBinaryData-master/", b"")
    os.replace(tmp, path)


def install(fetcher_cls, gathering_cls):
    """Wrap the fetcher's download for OcBinaryData only, and the engine's download history for OpenCore only."""
    if getattr(fetcher_cls, "_1401_ocbinarydata", False):
        return
    download = fetcher_cls.download_and_save_file

    def download_and_save_file(self, resource_url, destination_path, sha256_hash=None):
        if resource_url != URL:
            return download(self, resource_url, destination_path, sha256_hash)
        try:
            ok = download(self, resource_url, destination_path, sha256_hash)
            error = None
        except Exception as e:  # noqa: BLE001 - the engine's own failure path is a False return or a raise
            ok, error = False, e
        if ok:
            return True
        _state["missing"] = True
        why = f" ({type(error).__name__}: {error})" if error else ""
        print(f"OcBinaryData could not be downloaded from GitHub{why}. Building without it: the HFS+ driver comes from "
              "the OpenCore release itself (OpenHfsPlus.efi) and the boot picker uses its built-in look.")
        _empty_archive(destination_path)
        return True
    fetcher_cls.download_and_save_file = download_and_save_file

    save = gathering_cls._save_download_history

    def _save_download_history(self, history, product_name, *a, **kw):
        if _state["missing"] and "OpenCore" in str(product_name):
            return None
        return save(self, history, product_name, *a, **kw)
    gathering_cls._save_download_history = _save_download_history
    fetcher_cls._1401_ocbinarydata = True


def apply(config_path, notices):
    """Point the config at the drivers this build actually has. Returns policy-change records."""
    if not _state["missing"]:
        return []
    with open(config_path, "rb") as fh:
        cfg = plistlib.load(fh)
    drivers = cfg.get("UEFI", {}).get("Drivers", [])
    if any(d.get("Enabled") and d.get("Path") == APFS for d in drivers):
        raise NeedsOcBinaryData(
            "This macOS needs Apple's APFS driver from OcBinaryData (apfs_aligned.efi), and this network blocks the "
            "download from GitHub. 1401 cannot carry that file itself. Turn on a VPN, or a proxy set in Windows "
            "(Settings > Network & internet > Proxy - 1401 uses it), then build again.")
    changes = []
    have_open = any(d.get("Path") == OPEN_HFS for d in drivers)
    kept = []
    for d in drivers:
        if d.get("Path") in HFS:
            before = d["Path"]
            if have_open:
                changes.append({"rule": "ocbinarydata-missing", "before": before, "after": "(removed)",
                                "why": "OcBinaryData could not be downloaded; OpenHfsPlus.efi is already listed"})
                continue
            d["Path"] = OPEN_HFS
            have_open = True
            changes.append({"rule": "ocbinarydata-missing", "before": before, "after": OPEN_HFS,
                            "why": "OcBinaryData could not be downloaded; the open HFS+ driver ships with OpenCore"})
        kept.append(d)
    cfg["UEFI"]["Drivers"] = kept
    tmp = config_path + ".1401-tmp"
    with open(tmp, "wb") as fh:
        plistlib.dump(cfg, fh)
    os.replace(tmp, config_path)
    notices.append("GitHub did not deliver OcBinaryData, so this EFI uses OpenCore's own HFS+ driver "
                   "(OpenHfsPlus.efi) and the built-in boot picker look.")
    return changes
