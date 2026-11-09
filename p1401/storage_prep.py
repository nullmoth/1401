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

# Where the VMD / storage-mode switch is, by the maker named in the scan's board string. Each row cites the maker's own page
# where one was found (checked 2026-11-09); "reported" rows rest on user reports and say so in the text. Menu names move between
# BIOS versions, and the setting can be absent on a model (the text then points at the external-drive alternative).
BIOS_PATHS = (
    # ASUS: https://www.asus.com/support/faq/1048546/ and https://www.asus.com/me-en/support/faq/1044458/
    ("ASUS", "Press F7 for Advanced Mode, then Advanced > VMD setup menu > Enable VMD controller = Disabled. If the BIOS has no VMD "
             "option, ASUS says the model does not support the feature."),
    # MSI desktop: https://www.msi.com/support/technical_details/MB_OS_Inst_HDDSSD_Unrecog
    # MSI notebook: https://www.msi.com/support/technical_details/NB_Installation_Unrecognizable
    ("MICRO-STAR", "Desktop board: press Delete, F7 for Advanced mode, then Advanced > Integrated Peripherals > RAID Configuration "
                   "(Intel VMD) > Enable VMD controller = Disabled. Notebook: Advanced > Enable VMD controller = Disabled (MSI says the "
                   "option is hidden on some notebooks)."),
    ("MSI", "Desktop board: press Delete, F7 for Advanced mode, then Advanced > Integrated Peripherals > RAID Configuration "
            "(Intel VMD) > Enable VMD controller = Disabled. Notebook: Advanced > Enable VMD controller = Disabled."),
    # Gigabyte: https://download.gigabyte.com/FileList/Manual/mb_manual_intel700series-raid_e.pdf and
    # https://www.gigabyte.com/Support/FAQ/4054 (a BIOS update can change this setting)
    ("GIGABYTE", "Press Delete, then Settings > IO Ports > VMD setup menu > Enable VMD controller = Disabled (Intel 600/700-series "
                 "boards). A BIOS update can switch it back."),
    ("AORUS", "Press Delete, then Settings > IO Ports > VMD setup menu > Enable VMD controller = Disabled."),
    # ASRock: no manufacturer page found; generic Advanced > Storage Configuration is from the board manuals' layout, not checked
    ("ASROCK", "Press F2, then look under Advanced > Storage Configuration for VMD / SATA mode (AHCI). ASRock publishes the exact "
               "menu in each board's manual."),
    # Dell: Latitude 5320 service manual https://www.dell.com/support/manuals/en-lt/latitude-13-5320-2-in-1-laptop/latitude_5320_sm/storage
    # (options Disabled / AHCI/NVMe / RAID On, RAID On the default) and https://www.dell.com/support/kbdoc/en-us/000183948/
    ("DELL", "Press F2, then Storage > SATA/NVMe Operation = AHCI/NVMe, not RAID On (older models: System Configuration > SATA "
             "Operation). Dell ships many Latitudes with RAID On. A BIOS update can set it back to RAID On."),
    # HP: https://support.hp.com/vn-en/document/ish_9631042-9631101-16 (desktops: Storage > Storage Options > SATA Emulation = AHCI)
    ("HP", "Press F10 (desktops: Storage > Storage Options > SATA Emulation = AHCI). Notebooks: Advanced > System Options or "
           "Advanced > Configure Storage Controller, set to AHCI; reported by users, not in an HP page we could check. "
           "Some HP notebooks have no such option."),
    # Lenovo: no Lenovo page found for notebook storage mode; third-party UEFI guide and user reports: Config > Storage > Controller Mode
    # (Intel VMD on = RAID, off = AHCI on Legion). Per-model manuals: https://support.lenovo.com/us/en/manuals/um002089-hardware-maintenance-manual
    ("LENOVO", "Press F1 (ThinkPad) or F2 (IdeaPad, Legion), then Config > Storage > Controller Mode = AHCI (Legion: Intel VMD "
               "Controller = Disabled). This path is from user reports, not a Lenovo page; Lenovo lists each model's menu in its "
               "Hardware Maintenance Manual. Some IdeaCentre/IdeaPad models have no such option."),
    # Acer desktop: https://community.acer.com/tw/kb/articles/15968 (Del, Advanced > Integrated Peripherals, Ctrl+D shows VMD Controller;
    # off gives Onboard SATA Mode = AHCI Only). Notebooks: user reports (Main tab, Ctrl+S): https://community.acer.com/en/discussion/690325
    ("ACER", "Desktop: press Delete, then Advanced > Integrated Peripherals, press Ctrl+D to show VMD Controller, set it to Disabled "
             "(SATA mode becomes AHCI Only). Notebook: press F2, then on the Main tab press Ctrl+S to show VMD Controller (user reports; "
             "some models hide it or ask for a BIOS password)."),
    # Huawei: https://consumer.huawei.com/en/support/content/en-us15777885/ documents entering the BIOS with F2 and an Advanced page;
    # Huawei publishes no storage-mode setting for MateBooks (no page found).
    ("HUAWEI", "Press F2 to enter the BIOS (Huawei's own page). Huawei documents no storage or VMD setting for MateBooks; if the "
               "Advanced page has none, use the drive alternative (macOS on a USB SSD)."),
    ("HONOR", "Press F2 to enter the BIOS. Honor documents no storage or VMD setting; if the Advanced page has none, use the drive "
              "alternative (macOS on a USB SSD)."),
    # Mechrevo: no maker page found
    ("MECHREVO", "Mechrevo publishes no BIOS guide we could find. Press Delete or F2, look under Advanced for VMD or SATA mode; if "
                 "there is none, use the drive alternative (macOS on a USB SSD)."),
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
