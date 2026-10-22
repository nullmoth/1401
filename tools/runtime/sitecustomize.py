import warnings
warnings.filterwarnings("ignore", category=SyntaxWarning)

# Report NM-AC6JR3W7: "DLL load failed while importing win32api: The specified procedure could not be found".
# Another pywin32 on the PC (a system-wide pywintypes DLL, or one on PATH) was loaded instead of ours. Load ours by
# full path first: Windows then reuses the module already loaded under that name. The DLL names carry the Python
# version (pywintypes313.dll), so they are built from the running interpreter, not written in.
import os as _os, sys as _sys
if _sys.platform == "win32":
    _d = _os.path.join(_sys.prefix, "Lib", "site-packages", "pywin32_system32")
    if _os.path.isdir(_d):
        try:
            _os.add_dll_directory(_d)
            _os.environ["PATH"] = _d + _os.pathsep + _os.environ.get("PATH", "")
            import ctypes as _ct
            _v = "%d%d" % _sys.version_info[:2]
            for _n in ("pywintypes%s.dll" % _v, "pythoncom%s.dll" % _v):
                _p = _os.path.join(_d, _n)
                if _os.path.isfile(_p):
                    _ct.WinDLL(_p)
        except OSError as _e:
            print("1401: could not preload pywin32 from", _d, "-", _e, file=_sys.stderr)
