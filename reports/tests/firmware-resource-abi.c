#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <setupapi.h>
#include <cfgmgr32.h>
#include <stddef.h>

_Static_assert(sizeof(MEM_DES) == 32, "MEM_DES size");
_Static_assert(offsetof(MEM_DES, MD_Count) == 0, "MEM_DES.Count");
_Static_assert(offsetof(MEM_DES, MD_Type) == 4, "MEM_DES.Type");
_Static_assert(offsetof(MEM_DES, MD_Alloc_Base) == 8, "MEM_DES.Alloc_Base");
_Static_assert(offsetof(MEM_DES, MD_Alloc_End) == 16, "MEM_DES.Alloc_End");
_Static_assert(offsetof(MEM_DES, MD_Flags) == 24, "MEM_DES.Flags");
_Static_assert(offsetof(MEM_DES, MD_Reserved) == 28, "MEM_DES.Reserved");
_Static_assert(sizeof(MEM_LARGE_DES) == 32, "MEM_LARGE_DES size");
_Static_assert(offsetof(MEM_LARGE_DES, MLD_Count) == 0, "MEM_LARGE_DES.Count");
_Static_assert(offsetof(MEM_LARGE_DES, MLD_Type) == 4, "MEM_LARGE_DES.Type");
_Static_assert(offsetof(MEM_LARGE_DES, MLD_Alloc_Base) == 8, "MEM_LARGE_DES.Alloc_Base");
_Static_assert(offsetof(MEM_LARGE_DES, MLD_Alloc_End) == 16, "MEM_LARGE_DES.Alloc_End");
_Static_assert(offsetof(MEM_LARGE_DES, MLD_Flags) == 24, "MEM_LARGE_DES.Flags");
_Static_assert(offsetof(MEM_LARGE_DES, MLD_Reserved) == 28, "MEM_LARGE_DES.Reserved");
_Static_assert(sizeof(IO_DES) == 28, "IO_DES size");
_Static_assert(offsetof(IO_DES, IOD_Count) == 0, "IO_DES.Count");
_Static_assert(offsetof(IO_DES, IOD_Type) == 4, "IO_DES.Type");
_Static_assert(offsetof(IO_DES, IOD_Alloc_Base) == 8, "IO_DES.Alloc_Base");
_Static_assert(offsetof(IO_DES, IOD_Alloc_End) == 16, "IO_DES.Alloc_End");
_Static_assert(offsetof(IO_DES, IOD_DesFlags) == 24, "IO_DES.DesFlags");
_Static_assert(sizeof(IRQ_DES_64) == 24, "IRQ_DES_64 size");
_Static_assert(offsetof(IRQ_DES_64, IRQD_Count) == 0, "IRQ_DES_64.Count");
_Static_assert(offsetof(IRQ_DES_64, IRQD_Type) == 4, "IRQ_DES_64.Type");
_Static_assert(offsetof(IRQ_DES_64, IRQD_Flags) == 8, "IRQ_DES_64.Flags");
_Static_assert(offsetof(IRQ_DES_64, IRQD_Alloc_Num) == 12, "IRQ_DES_64.Alloc_Num");
_Static_assert(offsetof(IRQ_DES_64, IRQD_Affinity) == 16, "IRQ_DES_64.Affinity");
_Static_assert(sizeof(DMA_DES) == 16, "DMA_DES size");
_Static_assert(offsetof(DMA_DES, DD_Count) == 0, "DMA_DES.Count");
_Static_assert(offsetof(DMA_DES, DD_Type) == 4, "DMA_DES.Type");
_Static_assert(offsetof(DMA_DES, DD_Flags) == 8, "DMA_DES.Flags");
_Static_assert(offsetof(DMA_DES, DD_Alloc_Chan) == 12, "DMA_DES.Alloc_Chan");
_Static_assert(sizeof(BUSNUMBER_DES) == 20, "BUSNUMBER_DES size");
_Static_assert(offsetof(BUSNUMBER_DES, BUSD_Count) == 0, "BUSNUMBER_DES.Count");
_Static_assert(offsetof(BUSNUMBER_DES, BUSD_Type) == 4, "BUSNUMBER_DES.Type");
_Static_assert(offsetof(BUSNUMBER_DES, BUSD_Flags) == 8, "BUSNUMBER_DES.Flags");
_Static_assert(offsetof(BUSNUMBER_DES, BUSD_Alloc_Base) == 12, "BUSNUMBER_DES.Alloc_Base");
_Static_assert(offsetof(BUSNUMBER_DES, BUSD_Alloc_End) == 16, "BUSNUMBER_DES.Alloc_End");
_Static_assert(sizeof(IRQ_DES) == sizeof(IRQ_DES_64), "IRQ_DES is the 64-bit form on x64");
_Static_assert(sizeof(JOBOBJECT_BASIC_LIMIT_INFORMATION) == 64, "JOBOBJECT_BASIC_LIMIT_INFORMATION size");
_Static_assert(offsetof(JOBOBJECT_BASIC_LIMIT_INFORMATION, PerProcessUserTimeLimit) == 0, "JOBOBJECT_BASIC_LIMIT_INFORMATION.PerProcessUserTimeLimit");
_Static_assert(offsetof(JOBOBJECT_BASIC_LIMIT_INFORMATION, PerJobUserTimeLimit) == 8, "JOBOBJECT_BASIC_LIMIT_INFORMATION.PerJobUserTimeLimit");
_Static_assert(offsetof(JOBOBJECT_BASIC_LIMIT_INFORMATION, LimitFlags) == 16, "JOBOBJECT_BASIC_LIMIT_INFORMATION.LimitFlags");
_Static_assert(offsetof(JOBOBJECT_BASIC_LIMIT_INFORMATION, MinimumWorkingSetSize) == 24, "JOBOBJECT_BASIC_LIMIT_INFORMATION.MinimumWorkingSetSize");
_Static_assert(offsetof(JOBOBJECT_BASIC_LIMIT_INFORMATION, MaximumWorkingSetSize) == 32, "JOBOBJECT_BASIC_LIMIT_INFORMATION.MaximumWorkingSetSize");
_Static_assert(offsetof(JOBOBJECT_BASIC_LIMIT_INFORMATION, ActiveProcessLimit) == 40, "JOBOBJECT_BASIC_LIMIT_INFORMATION.ActiveProcessLimit");
_Static_assert(offsetof(JOBOBJECT_BASIC_LIMIT_INFORMATION, Affinity) == 48, "JOBOBJECT_BASIC_LIMIT_INFORMATION.Affinity");
_Static_assert(offsetof(JOBOBJECT_BASIC_LIMIT_INFORMATION, PriorityClass) == 56, "JOBOBJECT_BASIC_LIMIT_INFORMATION.PriorityClass");
_Static_assert(offsetof(JOBOBJECT_BASIC_LIMIT_INFORMATION, SchedulingClass) == 60, "JOBOBJECT_BASIC_LIMIT_INFORMATION.SchedulingClass");
_Static_assert(sizeof(IO_COUNTERS) == 48, "IO_COUNTERS size");
_Static_assert(offsetof(IO_COUNTERS, ReadOperationCount) == 0, "IO_COUNTERS.ReadOperationCount");
_Static_assert(offsetof(IO_COUNTERS, WriteOperationCount) == 8, "IO_COUNTERS.WriteOperationCount");
_Static_assert(offsetof(IO_COUNTERS, OtherOperationCount) == 16, "IO_COUNTERS.OtherOperationCount");
_Static_assert(offsetof(IO_COUNTERS, ReadTransferCount) == 24, "IO_COUNTERS.ReadTransferCount");
_Static_assert(offsetof(IO_COUNTERS, WriteTransferCount) == 32, "IO_COUNTERS.WriteTransferCount");
_Static_assert(offsetof(IO_COUNTERS, OtherTransferCount) == 40, "IO_COUNTERS.OtherTransferCount");
_Static_assert(sizeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION) == 144, "JOBOBJECT_EXTENDED_LIMIT_INFORMATION size");
_Static_assert(offsetof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION, BasicLimitInformation) == 0, "JOBOBJECT_EXTENDED_LIMIT_INFORMATION.BasicLimitInformation");
_Static_assert(offsetof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION, IoInfo) == 64, "JOBOBJECT_EXTENDED_LIMIT_INFORMATION.IoInfo");
_Static_assert(offsetof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION, ProcessMemoryLimit) == 112, "JOBOBJECT_EXTENDED_LIMIT_INFORMATION.ProcessMemoryLimit");
_Static_assert(offsetof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JobMemoryLimit) == 120, "JOBOBJECT_EXTENDED_LIMIT_INFORMATION.JobMemoryLimit");
_Static_assert(offsetof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION, PeakProcessMemoryUsed) == 128, "JOBOBJECT_EXTENDED_LIMIT_INFORMATION.PeakProcessMemoryUsed");
_Static_assert(offsetof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION, PeakJobMemoryUsed) == 136, "JOBOBJECT_EXTENDED_LIMIT_INFORMATION.PeakJobMemoryUsed");
_Static_assert(JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE == 0x2000, "job kill-on-close");
_Static_assert(JobObjectExtendedLimitInformation == 9, "job information class");
_Static_assert((ALLOC_LOG_CONF) == (2), "ALLOC_LOG_CONF");
_Static_assert((ResType_All) == (0), "ResType_All");
_Static_assert((CR_NO_MORE_LOG_CONF) == (14), "CR_NO_MORE_LOG_CONF");
_Static_assert((CR_NO_MORE_RES_DES) == (15), "CR_NO_MORE_RES_DES");
_Static_assert((CR_CALL_NOT_IMPLEMENTED) == (52), "CR_CALL_NOT_IMPLEMENTED");
_Static_assert((DIGCF_PRESENT) == (2), "DIGCF_PRESENT");
_Static_assert((DIGCF_ALLCLASSES) == (4), "DIGCF_ALLCLASSES");

int main(void) {return 0;}
