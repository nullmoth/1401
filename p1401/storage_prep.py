"""Storage the PC hides from macOS (Intel VMD / RAID mode, or drives macOS cannot use), and the plan that gets past it.

macOS cannot see a drive that sits behind Intel VMD. The fix is a firmware switch, and the switch is what breaks Windows:
with VMD off, Windows boots from a controller whose driver it did not start at boot and stops with INACCESSIBLE_BOOT_DEVICE.
So the plan has three parts, all produced here and none of them applied without the user pressing the button:

  1. prepare   restore point, BitLocker suspended for two restarts, the inbox AHCI and NVMe drivers set to start at boot, and
               a one-time Safe Mode boot (the documented method for a RAID/VMD to AHCI change);
  2. firmware  the BIOS menu path for this board's maker, shown before the user restarts;
  3. finish    after the first Safe Mode boot: leave Safe Mode, resume BitLocker. Windows now boots normally.

`undo` puts every value back from the saved state. The EFI does not depend on this step (it carries no storage setting),
so the build is planned either way; the plan rides in the build result as `storage_plan`.

When VMD cannot be turned off (the BIOS hides the option) or every drive is one macOS cannot use, the plan is the other
one: install macOS on a drive that is not behind VMD, such as a USB SSD. Nothing on the internal drive changes.
"""
import json
import os
import subprocess
import sys

SERVICES = ("storahci", "stornvme")
REG = r"HKLM\SYSTEM\CurrentControlSet\Services"

# Where the VMD / storage-mode switch usually is, by the maker named in the scan's board string. Menu names move between
# BIOS versions, so every line says "usually" and the plan also carries the generic wording.
BIOS_PATHS = (
    ("ASUS", "Press F7 for Advanced Mode, then Advanced > VMD setup menu > Enable VMD controller = Disabled (some boards: "
             "Advanced > PCH Storage Configuration, or Boot > Intel Rapid Storage Technology)."),
    ("MICRO-STAR", "Press Delete, then Settings > Advanced > VMD setup menu > Enable VMD controller = Disabled (some boards: "
                   "Settings > Advanced > Integrated Peripherals > SATA Mode = AHCI)."),
    ("MSI", "Press Delete, then Settings > Advanced > VMD setup menu > Enable VMD controller = Disabled."),
    ("GIGABYTE", "Press Delete, then Settings > IO Ports > Intel(R) VMD technology (or Advanced > VMD setup menu) = Disabled; "
                 "on some boards Settings > IO Ports > SATA Configuration > SATA Mode Selection = AHCI."),
    ("ASROCK", "Press F2, then Advanced > Storage Configuration > VMD / RAID mode = Disabled, SATA Mode = AHCI."),
    ("DELL", "Press F2, then Storage > SATA/NVMe Operation (or Storage Controller) = AHCI/NVMe, not RAID On."),
    ("HP", "Press F10, then Advanced > System Options (or Advanced > Configure Storage Controller) > Storage Controller = AHCI."),
    ("LENOVO", "Press F1 (ThinkPad) or F2 (IdeaPad/Legion), then Config > Storage > Controller Mode = AHCI "
               "(older models: Devices > ATA Drive Setup > SATA Controller Mode Option = AHCI)."),
    ("ACER", "Press F2, then Main > SATA Mode = AHCI. If the option is not shown, press Ctrl+S on the Main page to reveal it."),
    ("HUAWEI", "Press F2, then look for Storage > SATA / NVMe mode = AHCI. Huawei and Honor models often hide it: see the "
               "drive alternative."),
    ("HONOR", "Press F2, then look for Storage > SATA / NVMe mode = AHCI. Honor models often hide it: see the drive alternative."),
    ("MECHREVO", "Press Delete or F2, then Advanced > VMD setup menu or SATA Mode = AHCI. Many Mechrevo models hide it: see the "
                 "drive alternative."),
)
GENERIC_PATH = ("Open the BIOS (Delete, F2 or F10 while the PC starts), find the storage settings (often Advanced > Storage, "
                "SATA Configuration or VMD setup), and set Intel VMD / Volume Management Device to Disabled, or the storage "
                "mode to AHCI.")


def bios_path(board_name):
    """-> the menu path text for this board's maker."""
    name = str(board_name or "").upper()
    for maker, text in BIOS_PATHS:
        if maker in name:
            return text
    return GENERIC_PATH


def vmd_controllers(report):
    """Controllers in the scan that are Intel VMD or RAID mode (the engine's own VMD ID list plus the names Windows gives them)."""
    out = []
    for name, props in (report.get("Storage Controllers") or {}).items():
        if not isinstance(props, dict):
            continue
        upper = name.upper()
        if any(t in upper for t in ("VOLUME MANAGEMENT", "VMD", "RAID", "RST ")):
            out.append(f"{name} ({props.get('Device ID', 'no ID')})")
    return out


def prepare_commands(drive="C:"):
    """Command lines for the Windows side, in order. Each is a list for subprocess; none uses a shell."""
    ps = ["powershell", "-NoProfile", "-NonInteractive", "-Command"]
    cmds = [
        ("restore point", ps + [f"Enable-ComputerRestore -Drive '{drive}\\'; Checkpoint-Computer -Description "
                                "'1401 before storage mode change' -RestorePointType MODIFY_SETTINGS"], False),
        ("BitLocker: suspend for two restarts", ["manage-bde", "-protectors", "-disable", drive, "-RebootCount", "2"], False),
    ]
    for svc in SERVICES:
        cmds.append((f"start {svc} at boot", ["reg", "add", f"{REG}\\{svc}", "/v", "Start", "/t", "REG_DWORD", "/d", "0", "/f"], True))
    cmds.append(("one-time Safe Mode boot", ["bcdedit", "/set", "{current}", "safeboot", "minimal"], True))
    return cmds


def finish_commands(drive="C:"):
    return [("leave Safe Mode", ["bcdedit", "/deletevalue", "{current}", "safeboot"], True),
            ("BitLocker: resume", ["manage-bde", "-protectors", "-enable", drive], False)]


def undo_commands(saved, drive="C:"):
    """Put the drivers' start types back from the values saved before prepare, then finish."""
    cmds = []
    for svc, value in (saved or {}).items():
        if value is None:
            cmds.append((f"remove the start value of {svc}", ["reg", "delete", f"{REG}\\{svc}", "/v", "Start", "/f"], False))
        else:
            cmds.append((f"restore {svc} start type", ["reg", "add", f"{REG}\\{svc}", "/v", "Start", "/t", "REG_DWORD", "/d",
                                                         str(value), "/f"], True))
    return cmds + finish_commands(drive)


def read_start(svc, runner=subprocess.run):
    """Current Start value of a service, or None when the value does not exist."""
    p = runner(["reg", "query", f"{REG}\\{svc}", "/v", "Start"], capture_output=True, text=True)
    if p.returncode != 0:
        return None
    for line in p.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "Start":
            try:
                return int(parts[2], 0)
            except ValueError:
                return None
    return None


def run(action, state_path, runner=subprocess.run, drive="C:", platform=None):
    """Apply prepare / finish / undo. -> list of (step, ok, message). Windows only; a required step that fails stops the run
    and, for prepare, the earlier changes are undone so the PC is not left half-prepared."""
    if (platform or sys.platform) != "win32":
        raise RuntimeError("the Windows storage preparation runs only on Windows")
    log = []

    def go(steps):
        for label, cmd, required in steps:
            p = runner(cmd, capture_output=True, text=True)
            ok = p.returncode == 0
            log.append((label, ok, (p.stderr or p.stdout or "").strip()[:300]))
            if not ok and required:
                return False
        return True

    if action == "prepare":
        saved = {svc: read_start(svc, runner) for svc in SERVICES}
        _write_state(state_path, {"saved": saved, "drive": drive})
        if not go(prepare_commands(drive)):
            go(undo_commands(saved, drive))
            log.append(("rolled back", True, "a required step failed; the earlier changes were undone"))
            return log
    elif action == "finish":
        go(finish_commands(drive))
    elif action == "undo":
        state = _read_state(state_path)
        go(undo_commands(state.get("saved"), state.get("drive", drive)))
    else:
        raise ValueError(f"unknown action {action!r}")
    return log


def _write_state(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f)
    os.replace(tmp, path)


def _read_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def plan(report, kind, controllers=()):
    """-> the storage plan for a scan.

    kind 'vmd-off': switch VMD off, with the Windows preparation (the default when a VMD controller holds the drives).
    kind 'external-drive': install macOS on a drive macOS can see (chosen when the user asks for it, when the BIOS has no VMD
    option, or when no internal drive is usable and VMD is not the reason)."""
    board = (report.get("Motherboard") or {}).get("Name", "")
    if kind == "vmd-off":
        steps = [
            "Back up important files, and save the BitLocker recovery key if the drive is encrypted.",
            "Run Prepare Windows (p1401 storage-prep prepare): it makes a restore point, pauses BitLocker, sets the standard AHCI "
            "and NVMe drivers to start at boot and arranges one Safe Mode start. Nothing changes until you run it; "
            "p1401 storage-prep undo puts every value back.",
            "Restart into the BIOS and switch Intel VMD off: " + bios_path(board),
            "Save and exit. Windows starts in Safe Mode once; run Finish (p1401 storage-prep finish, or bcdedit /deletevalue "
            "{current} safeboot) and restart. Windows then boots normally on the standard driver.",
            "Run Check this PC again. The new scan sees the drive as a normal NVMe/SATA disk and the build continues.",
            "If the BIOS has no VMD option, use the drive alternative instead: install macOS on a USB SSD.",
        ]
    else:
        steps = ["Plug in the drive macOS will live on (a USB SSD, or an internal SATA/NVMe SSD that is not behind VMD).",
                 "Install macOS on it from the 1401 stick. The internal drive and Windows are not touched.",
                 "Keep the stick or the SSD's own EFI as the startup device."]
    return {"kind": kind, "controllers": list(controllers), "board": board,
            "bios_path": bios_path(board) if kind == "vmd-off" else "", "steps": steps, "undoable": kind == "vmd-off"}
