"""VirtualSMC and its sensor plugins built by NullMoth from source, put into the EFI in place of the release the engine
downloaded.

Why: SMCSuperIO (fan speeds from the board's Super I/O chip) does not know the ITE IT8696E and IT8698E on current boards,
and three of its ITE model checks used strcmp as if it returned true on a match, so every ITE chip took the
extended-register and alternate-PWM paths. vendor/smcsuperio/ holds the pinned upstream commits (acidanthera VirtualSMC,
Lilu, MacKernelSDK; BSD-3-Clause), the patch and build.sh; the package below is that build, hosted on NullMoth's mirror.

A plugin must match the VirtualSMC it loads into, so the swap is all or nothing: every kext of the set that the EFI holds is
replaced from the one package, or none is and the build keeps the downloaded release (with a notice). Any problem
(no network, a mismatching file, a kext missing from the package) leaves the EFI as the engine wrote it."""
import hashlib
import io
import os
import shutil
import tempfile
import zipfile

from . import mirror

PACKAGE = {
    "version": "1.3.9-nm29",
    "url": "https://nullmothsystems.com/mirror/7ec44e7e2651df42bb8864a8d6d3318512c84ee9f826f44e162bee96d088ece7",
    "sha256": "7ec44e7e2651df42bb8864a8d6d3318512c84ee9f826f44e162bee96d088ece7",
    "size": 155266,
}
KEXTS = ("VirtualSMC", "SMCProcessor", "SMCBatteryManager", "SMCLightSensor", "SMCSuperIO", "SMCDellSensors")
MAX_SIZE = 8 * 1024 * 1024


def _package_kexts(data, workdir):
    """Unpack the verified package into workdir; -> {name: path of name.kext}. Raises ValueError on anything unexpected."""
    if len(data) != PACKAGE["size"] or hashlib.sha256(data).hexdigest() != PACKAGE["sha256"]:
        raise ValueError("the package does not match its pinned SHA-256")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        if any(n.startswith("/") or ".." in n.split("/") for n in names):
            raise ValueError("the package holds a path outside itself")
        if sum(i.file_size for i in z.infolist()) > MAX_SIZE:
            raise ValueError("the package unpacks larger than expected")
        z.extractall(workdir)
    sums = {}
    with open(os.path.join(workdir, "SHA256SUMS"), encoding="utf-8") as fh:
        for line in fh:
            digest, _, name = line.strip().partition("  ")
            sums[name] = digest
    out = {}
    for k in KEXTS:
        kext = os.path.join(workdir, "Kexts", k + ".kext")
        exe = os.path.join(kext, "Contents", "MacOS", k)
        if not os.path.isfile(exe) or os.path.islink(kext):
            raise ValueError(f"the package has no {k}.kext")
        with open(exe, "rb") as fh:
            if hashlib.sha256(fh.read()).hexdigest() != sums.get(k + ".kext"):
                raise ValueError(f"{k}.kext does not match the package's SHA256SUMS")
        out[k] = kext
    return out


def replace(out_dir, notices, fetch=mirror.fetch):
    """Swap the VirtualSMC set in out_dir/EFI/OC/Kexts for NullMoth's build. -> the names replaced (empty: unchanged)."""
    kdir = os.path.join(out_dir, "EFI", "OC", "Kexts")
    present = [k for k in KEXTS if os.path.isdir(os.path.join(kdir, k + ".kext"))]
    if not present:
        return []
    try:
        data = fetch(PACKAGE["url"])
        with tempfile.TemporaryDirectory() as tmp:
            ours = _package_kexts(data, tmp)
            staged = os.path.join(kdir, ".nullmoth-virtualsmc")
            shutil.rmtree(staged, ignore_errors=True)
            os.makedirs(staged)
            for k in present:   # copy every replacement first, so a failure part-way leaves the downloaded set whole
                shutil.copytree(ours[k], os.path.join(staged, k + ".kext"), symlinks=True)
            for k in present:
                dst = os.path.join(kdir, k + ".kext")
                shutil.rmtree(dst)
                os.replace(os.path.join(staged, k + ".kext"), dst)
            shutil.rmtree(staged, ignore_errors=True)
    except Exception as e:  # noqa: BLE001 - sensors must never break a build
        notices.append(f"Sensors: kept the downloaded VirtualSMC release ({type(e).__name__}: {e}); fan speeds on ITE "
                       f"IT8696E/IT8698E boards are not read with it.")
        return []
    notices.append(f"Sensors: VirtualSMC {PACKAGE['version']} built by NullMoth from source (fan speeds on more Super I/O "
                   f"chips, ITE model checks fixed): {', '.join(present)}.")
    return present
