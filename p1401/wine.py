"""Is this process running under Wine?

Wine runs the app, but its WMI has no device database: every Win32_PnPEntity query fails (DISP_E_EXCEPTION; a scan under
Z:\\home\\... retried three times and gave up with "Windows could not read its device database"). The scan says so before
the Sniffer starts instead of blaming Windows. Wine's ntdll exports wine_get_version; its registry also carries
HKCU/HKLM\\Software\\Wine. Both are checked, either is enough."""
import platform

MESSAGE = ("1401 needs real Windows; Wine cannot read the hardware (its WMI has no device database). Start Windows on "
           "the PC you want macOS on and run 1401 there.")


def version(load_ntdll=None, open_key=None):
    """The Wine version string when this process runs under Wine, else None. load_ntdll/open_key are injectable."""
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
        if key is not None:
            return "registry"
    return None
