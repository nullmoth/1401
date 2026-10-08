/* nm_cpuinfo: read-only CPU facts for the 1401 scan worker.
 *
 * One fixed operation, no arguments: execute an allow-listed set of documented CPUID leaves (and XGETBV only when the
 * CPU reports XSAVE and the OS reports OSXSAVE), then visit each active logical processor on one owned helper thread
 * to read its own topology leaves, restoring that thread's previous affinity afterwards. Output is bounded JSON on
 * stdout. No MSR, port I/O or MMIO; no driver; no serial-number leaf (CPUID leaf 3 is refused by the allow-list); no
 * host, user or path is read. The logic lives in nm_cpuinfo_core.c and talks to the hardware only through `nm_backend`,
 * so the same code runs against fixtures in tests.
 *
 * Primary sources (exact versions reviewed for this collector):
 *   Intel 64 and IA-32 SDM Vol. 2A, CPUID; Intel Architecture Instruction Set Extensions Programming Reference 319433-062
 *     (leaf 1AH: CORE_TYPE in EAX[31:24], 20H Intel Atom, 40H Intel Core, leaf present only if EAX != 0;
 *     leaf 1 ECX[26] XSAVE, ECX[27] OSXSAVE; leaf 3 is the Pentium III processor serial number)
 *   Intel 64 Architecture Processor Topology Enumeration 337015 rev 2.0 (leaf 1FH supersedes 0BH; a leaf exists if
 *     CPUID.(leaf,0):EBX != 0; ECX[15:8] domain type 1 LP, 2 Core, 3 Module, 4 Tile, 5 Die, 6 DieGrp; EAX[4:0] shift;
 *     EDX x2APIC ID)
 *   AMD CPUID Specification 25481 (Fn8000_001E valid only when Fn8000_0001_ECX[22] TopologyExtensions = 1;
 *     Fn8000_0008_ECX raw bits; modern AMD topology is not decoded from archived documentation)
 *   Microsoft: __cpuidex (<intrin.h>), _xgetbv, GetLogicalProcessorInformationEx(RelationGroup), GROUP_RELATIONSHIP,
 *     PROCESSOR_GROUP_INFO, SetThreadGroupAffinity / GetThreadGroupAffinity.
 */
#ifndef NM_CPUINFO_H
#define NM_CPUINFO_H
#include <stddef.h>
#include <stdint.h>

#define NM_MAX_LP 512            /* logical processors visited at most */
#define NM_MAX_GROUPS 32
#define NM_MAX_TOPO_SUBLEAF 8    /* 1FH/0BH subleaves walked at most (6 domain types exist) */
#define NM_MAX_LEAF7_SUBLEAF 2
#define NM_OUT_CAP (1u << 20)    /* JSON bytes at most (the worker reads up to 2 MiB) */
#define NM_DEFAULT_BUDGET_MS 3000u

typedef struct { uint32_t a, b, c, d; } nm_regs;
typedef struct { uint16_t group; uint64_t mask; } nm_affinity;
typedef struct { uint16_t group; uint8_t active; uint64_t mask; } nm_group;

typedef struct nm_backend {
    void *ctx;
    void (*cpuid)(void *ctx, uint32_t leaf, uint32_t sub, nm_regs *out);
    int (*xgetbv)(void *ctx, uint32_t index, uint64_t *out);          /* 0 = ok */
    int (*groups)(void *ctx, nm_group *out, int max);                 /* active groups, -1 = failed */
    int (*get_affinity)(void *ctx, nm_affinity *out);                 /* 0 = ok */
    int (*set_affinity)(void *ctx, const nm_affinity *aff);           /* 0 = ok */
    uint64_t (*now_ms)(void *ctx);
    int (*current_processor)(void *ctx, nm_affinity *out); /* exact current group/single-bit mask, 0 = observed */
} nm_backend;

typedef struct { char *buf; size_t cap, len; int truncated; } nm_out;

/* Leaves the helper may execute. Everything else, leaf 3 included, is refused before the backend is called. */
int nm_leaf_allowed(uint32_t leaf);
/* Runs the fixed operation; returns 0 when the JSON in `o` is complete (it may still hold per-field statuses). */
int nm_collect(const nm_backend *b, nm_out *o, uint32_t budget_ms);
/* The helper accepts no arguments: 0 when argc == 1. */
int nm_args_ok(int argc);
#endif
