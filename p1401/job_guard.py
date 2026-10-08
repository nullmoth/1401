"""Owned Windows worker containment; the non-inheritable job handle lives until worker exit.

Microsoft Job Objects: child processes inherit membership; KILL_ON_JOB_CLOSE terminates the entire associated tree.
No breakaway flags are enabled. Failure to establish containment blocks subprocess-backed diagnostics.
"""
import ctypes
import sys

DWORD, SIZE, HANDLE = ctypes.c_uint32, ctypes.c_size_t, ctypes.c_void_p


class BasicLimits(ctypes.Structure):
    _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                ('LimitFlags', DWORD), ('MinimumWorkingSetSize', SIZE), ('MaximumWorkingSetSize', SIZE),
                ('ActiveProcessLimit', DWORD), ('Affinity', SIZE), ('PriorityClass', DWORD), ('SchedulingClass', DWORD)]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in ('ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
                'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [('BasicLimitInformation', BasicLimits), ('IoInfo', IoCounters), ('ProcessMemoryLimit', SIZE),
                ('JobMemoryLimit', SIZE), ('PeakProcessMemoryUsed', SIZE), ('PeakJobMemoryUsed', SIZE)]


_job, _kernel = None, None


def initialize():
    """Call only from a dedicated disposable hardware worker, never the UI or imported-report builder."""
    global _job, _kernel
    if _job is not None: return True
    if sys.platform != 'win32': return False
    kernel = ctypes.WinDLL('kernel32.dll', use_last_error=True, winmode=0x800)
    bindings = [('CreateJobObjectW', HANDLE, [ctypes.c_void_p, ctypes.c_wchar_p]),
                ('SetInformationJobObject', ctypes.c_int32, [HANDLE, ctypes.c_int32, ctypes.c_void_p, DWORD]),
                ('GetCurrentProcess', HANDLE, []), ('AssignProcessToJobObject', ctypes.c_int32, [HANDLE, HANDLE]),
                ('IsProcessInJob', ctypes.c_int32, [HANDLE, HANDLE, ctypes.POINTER(ctypes.c_int32)]),
                ('CloseHandle', ctypes.c_int32, [HANDLE]),
                ('GetHandleInformation', ctypes.c_int32, [HANDLE, ctypes.POINTER(DWORD)])]
    for name, result, args in bindings:
        fn = getattr(kernel, name); fn.restype, fn.argtypes = result, args
    handle = kernel.CreateJobObjectW(None, None)  # null SECURITY_ATTRIBUTES: handle cannot be inherited
    if not handle: return False
    flags = DWORD()
    if not kernel.GetHandleInformation(handle, ctypes.byref(flags)) or flags.value & 1:
        kernel.CloseHandle(handle); return False
    limits = ExtendedLimits(); limits.BasicLimitInformation.LimitFlags = 0x2000
    if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        kernel.CloseHandle(handle); return False
    if not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        kernel.CloseHandle(handle); return False
    # Do not close an assigned kill-on-close job from its own member; closing it would terminate this worker.
    _job, _kernel = handle, kernel
    return contains(kernel.GetCurrentProcess())


def contains(process_handle):
    if _job is None or _kernel is None: return False
    value = ctypes.c_int32()
    return bool(_kernel.IsProcessInJob(int(process_handle), _job, ctypes.byref(value)) and value.value)


def ready():
    return _job is not None and contains(_kernel.GetCurrentProcess())
