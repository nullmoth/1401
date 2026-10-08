"""ABI check for p1401/fwres.py.

    python3 tests/abi_fwres_sdk.py --local out.c    header text copied from cfgmgr32.h / nvml.h; compile with
                                                    clang --target=x86_64-pc-windows-msvc -fsyntax-only out.c
    python  tests\\abi_fwres_sdk.py --sdk out.c       real Windows SDK <cfgmgr32.h>; compile on the CI runner with
                                                    cl /nologo /c /TC out.c   (NVML struct checked by the local form)

Every struct size and field offset the ctypes code uses, and every constant, is a _Static_assert; a mismatch is a
compile error."""
import ctypes
import os
import sys

sys.path.insert(0, os.getcwd())
from p1401 import fwres, job_guard  # noqa: E402

LOCAL_HEAD = r"""
typedef unsigned long DWORD; typedef unsigned long ULONG; typedef unsigned long long DWORDLONG; typedef unsigned long long ULONG64;
typedef unsigned short USHORT;
/* cfgmgr32.h (x64, NT_PROCESSOR_GROUPS, pshpack1.h) */
#pragma pack(push,1)
typedef struct Mem_Des_s { DWORD MD_Count; DWORD MD_Type; DWORDLONG MD_Alloc_Base; DWORDLONG MD_Alloc_End; DWORD MD_Flags; DWORD MD_Reserved; } MEM_DES;
typedef struct Mem_Large_Des_s { DWORD MLD_Count; DWORD MLD_Type; DWORDLONG MLD_Alloc_Base; DWORDLONG MLD_Alloc_End; DWORD MLD_Flags; DWORD MLD_Reserved; } MEM_LARGE_DES;
typedef struct IO_Des_s { DWORD IOD_Count; DWORD IOD_Type; DWORDLONG IOD_Alloc_Base; DWORDLONG IOD_Alloc_End; DWORD IOD_DesFlags; } IO_DES;
typedef struct IRQ_Des_64_s { DWORD IRQD_Count; DWORD IRQD_Type; USHORT IRQD_Flags; USHORT IRQD_Group; ULONG IRQD_Alloc_Num; ULONG64 IRQD_Affinity; } IRQ_DES_64;
typedef struct DMA_Des_s { DWORD DD_Count; DWORD DD_Type; DWORD DD_Flags; ULONG DD_Alloc_Chan; } DMA_DES;
typedef struct BusNumber_Des_s { DWORD BUSD_Count; DWORD BUSD_Type; DWORD BUSD_Flags; ULONG BUSD_Alloc_Base; ULONG BUSD_Alloc_End; } BUSNUMBER_DES;
#pragma pack(pop)
/* nvml.h */
typedef struct nvmlPciInfo_st { char busIdLegacy[16]; unsigned int domain; unsigned int bus; unsigned int device;
  unsigned int pciDeviceId; unsigned int pciSubSystemId; char busId[32]; } nvmlPciInfo_t;
#define ALLOC_LOG_CONF 0x00000002
#define ResType_All 0x00000000
#define CR_NO_MORE_LOG_CONF 0x0000000E
#define CR_NO_MORE_RES_DES 0x0000000F
#define CR_CALL_NOT_IMPLEMENTED 0x00000034
#define DIGCF_PRESENT 0x00000002
#define DIGCF_ALLCLASSES 0x00000004
#include <stddef.h>
"""
SDK_HEAD = """#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <setupapi.h>
#include <cfgmgr32.h>
#include <stddef.h>
"""
STRUCTS = [  # (C type, ctypes class, {ctypes field: C field})
    ("MEM_DES", fwres.MEM_DES, {"Count": "MD_Count", "Type": "MD_Type", "Alloc_Base": "MD_Alloc_Base", "Alloc_End": "MD_Alloc_End",
                                "Flags": "MD_Flags", "Reserved": "MD_Reserved"}),
    ("MEM_LARGE_DES", fwres.MEM_LARGE_DES, {"Count": "MLD_Count", "Type": "MLD_Type", "Alloc_Base": "MLD_Alloc_Base",
                                            "Alloc_End": "MLD_Alloc_End", "Flags": "MLD_Flags", "Reserved": "MLD_Reserved"}),
    ("IO_DES", fwres.IO_DES, {"Count": "IOD_Count", "Type": "IOD_Type", "Alloc_Base": "IOD_Alloc_Base", "Alloc_End": "IOD_Alloc_End",
                              "DesFlags": "IOD_DesFlags"}),
    ("IRQ_DES_64", fwres.IRQ_DES_64, {"Count": "IRQD_Count", "Type": "IRQD_Type", "Flags": "IRQD_Flags", "Alloc_Num": "IRQD_Alloc_Num",
                                      "Affinity": "IRQD_Affinity"}),
    ("DMA_DES", fwres.DMA_DES, {"Count": "DD_Count", "Type": "DD_Type", "Flags": "DD_Flags", "Alloc_Chan": "DD_Alloc_Chan"}),
    ("BUSNUMBER_DES", fwres.BUSNUMBER_DES, {"Count": "BUSD_Count", "Type": "BUSD_Type", "Flags": "BUSD_Flags",
                                            "Alloc_Base": "BUSD_Alloc_Base", "Alloc_End": "BUSD_Alloc_End"}),
]
LOCAL_ONLY = [("nvmlPciInfo_t", fwres.NvmlPciInfo, {f[0]: f[0] for f in fwres.NvmlPciInfo._fields_})]
CONSTS = [("ALLOC_LOG_CONF", fwres.ALLOC_LOG_CONF), ("ResType_All", fwres.RES_ALL), ("CR_NO_MORE_LOG_CONF", fwres.CR_NO_MORE_LOG_CONF),
          ("CR_NO_MORE_RES_DES", fwres.CR_NO_MORE_RES_DES), ("CR_CALL_NOT_IMPLEMENTED", fwres.CR_CALL_NOT_IMPLEMENTED),
          ("DIGCF_PRESENT", fwres.DIGCF_PRESENT), ("DIGCF_ALLCLASSES", fwres.DIGCF_ALLCLASSES)]


def generate(sdk):
    out = [SDK_HEAD if sdk else LOCAL_HEAD]
    for cname, py, names in STRUCTS + ([] if sdk else LOCAL_ONLY):
        out.append(f'_Static_assert(sizeof({cname}) == {ctypes.sizeof(py)}, "{cname} size");')
        for f in py._fields_:
            out.append(f'_Static_assert(offsetof({cname}, {names[f[0]]}) == {getattr(py, f[0]).offset}, "{cname}.{f[0]}");')
    if sdk:
        out.append('_Static_assert(sizeof(IRQ_DES) == sizeof(IRQ_DES_64), "IRQ_DES is the 64-bit form on x64");')
    if sdk:
        for cname, py in [('JOBOBJECT_BASIC_LIMIT_INFORMATION', job_guard.BasicLimits), ('IO_COUNTERS', job_guard.IoCounters),
                          ('JOBOBJECT_EXTENDED_LIMIT_INFORMATION', job_guard.ExtendedLimits)]:
            out.append(f'_Static_assert(sizeof({cname}) == {ctypes.sizeof(py)}, "{cname} size");')
            for name, _ in py._fields_:
                out.append(f'_Static_assert(offsetof({cname}, {name}) == {getattr(py,name).offset}, "{cname}.{name}");')
        out.append('_Static_assert(JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE == 0x2000, "job kill-on-close");')
        out.append('_Static_assert(JobObjectExtendedLimitInformation == 9, "job information class");')
    for c, v in CONSTS:
        out.append(f'_Static_assert(({c}) == ({v}), "{c}");')
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    open(sys.argv[2], "w").write(generate(sys.argv[1] == "--sdk"))
    print("wrote", sys.argv[2])
