"""Is this process running under Wine?

Wine runs the app, but its WMI has no device database: every Win32_PnPEntity query fails (DISP_E_EXCEPTION; a scan under
Z:\\home\\... retried three times and gave up with "Windows could not read its device database"). The scan says so before
the Sniffer starts instead of blaming Windows. Wine's ntdll exports wine_get_version; its registry also carries
HKCU/HKLM\\Software\\Wine. The export is enough by itself (real Windows' ntdll never has it). The registry key is not: other
software can leave a Software\\Wine key on a real PC, and 1401 #99 refused one that way. It counts only when Wine's Unix
root is visible as Z: too (Z:\\etc and Z:\\usr)."""
import os
import platform

MESSAGE = ("1401 needs real Windows; Wine cannot read the hardware (its WMI has no device database). Start Windows on "
           "the PC you want macOS on and run 1401 there.")


def _unix_root(isdir=os.path.isdir):
    return isdir("Z:\\etc") and isdir("Z:\\usr")


def version(load_ntdll=None, open_key=None, unix_root=None):
    """The Wine version string when this process runs under Wine, else None. load_ntdll/open_key/unix_root are injectable."""
    if platform.system() != "Windows" and load_ntdll is None and open_key is None:
        return None
    if load_ntdll is None:
        def load_ntdll():
            import ctypes  # noqa: PLC0415 - Windows only
            return ctypes.WinDLL("ntdll")
    if open_key is None:
        def open_key(root, path):
            import winreg  # noqa: PLC0415 - Windows only
            return winreg.OpenKey(getattr(winreg, root), path)
    try:
        ntdll = load_ntdll()
        fn = getattr(ntdll, "wine_get_version", None)
        if fn is not None:
            import ctypes  # noqa: PLC0415
            fn.restype = ctypes.c_char_p
            return (fn() or b"unknown").decode("ascii", "replace")
    except (OSError, AttributeError, TypeError):
        pass
    for root in ("HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE"):
        try:
            key = open_key(root, r"Software\Wine")
        except OSError:
            continue
        if key is not None and (unix_root or _unix_root)():
            return "registry"
    return None
